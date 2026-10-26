"""Job de sincronización: Silogtran -> Supabase (Postgres). Reutiliza api_liquidacion.py.

Alternativa a tener la API prendida 24/7 (que consume las horas gratis de Render): corre cada cierto
tiempo (cron de GitHub Actions), vuelca el informe en una tabla de Supabase y termina. QlikSense (u
otro BI) lee esa tabla en vez de llamar a la API en vivo.

Importa de api_liquidacion el cliente de Silogtran, la normalización y el esquema (no duplica nada).
Por cada mes del rango hace "reemplazo del mes" en una transacción (borra las filas del mes e inserta
las frescas), así quedan reflejados cambios y borrados.

Modos (variable de entorno MODE o 1er argumento):
  reciente  -> mes anterior + mes en curso (para el cron frecuente)  [por defecto]
  rango     -> usa SYNC_FECHA_INICIAL / SYNC_FECHA_FINAL (backfill histórico o refresco amplio)

Requiere SUPABASE_DB_URL (cadena del pooler de Supabase en modo sesión). Las credenciales de Silogtran
y el WAF se configuran igual que para la API (ver .env.example).
"""
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

from api_liquidacion import (COLUMNAS, CredencialesError, EstructuraError, SilogtranClient,
                             SilogtranError, USUARIO, CLAVE, normalizar)

log = logging.getLogger("liquidacion-sync")

COLUMNAS_TABLA = ["id"] + COLUMNAS + ["fecha_extraccion"]
DB_URL = os.environ.get("SUPABASE_DB_URL", "")
LOGIN_BACKOFF_MIN = int(os.environ.get("LOGIN_BACKOFF_MIN", "") or 30)
ZONA = timezone(timedelta(hours=-5))  # Colombia


# --- fechas / meses --------------------------------------------------------
def _fin_de_mes(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def meses(fi, ff):
    """(primer_dia, ultimo_dia) de cada mes calendario que toca [fi, ff]."""
    bloques, a = [], fi.replace(day=1)
    while a <= ff:
        bloques.append((a, _fin_de_mes(a)))
        a = (a + timedelta(days=32)).replace(day=1)
    return bloques


def rango_por_modo():
    modo = (os.environ.get("MODE") or (sys.argv[1] if len(sys.argv) > 1 else "") or "reciente").lower()
    hoy = datetime.now(ZONA).date()
    if modo == "rango":
        fi = os.environ.get("SYNC_FECHA_INICIAL", "")
        ff = os.environ.get("SYNC_FECHA_FINAL", "") or hoy.isoformat()
        if not fi:
            raise SystemExit("MODE=rango requiere SYNC_FECHA_INICIAL (y opcional SYNC_FECHA_FINAL)")
        return modo, date.fromisoformat(fi), date.fromisoformat(ff)
    primero_mes = hoy.replace(day=1)
    mes_anterior = (primero_mes - timedelta(days=1)).replace(day=1)
    return "reciente", mes_anterior, hoy


# --- base de datos ---------------------------------------------------------
def conectar():
    if not DB_URL:
        raise SystemExit("Falta SUPABASE_DB_URL (cadena de conexión Postgres de Supabase)")
    return psycopg2.connect(DB_URL, connect_timeout=30)


def freno_activo(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT bloqueado_hasta FROM sync_estado WHERE clave='login'")
        row = cur.fetchone()
    if row and row[0] and row[0] > datetime.now(timezone.utc):
        log.warning("Login en pausa hasta %s (fallo previo); se omite esta corrida", row[0].isoformat())
        return True
    return False


def marcar_login_ok(conn):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO sync_estado(clave, fallos, bloqueado_hasta, actualizado)
                       VALUES('login', 0, NULL, now())
                       ON CONFLICT(clave) DO UPDATE SET fallos=0, bloqueado_hasta=NULL, actualizado=now()""")
    conn.commit()


def marcar_login_fallo(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT fallos FROM sync_estado WHERE clave='login'")
        row = cur.fetchone()
        fallos = (row[0] if row else 0) + 1
        espera_min = min(LOGIN_BACKOFF_MIN * 4 ** (fallos - 1), 1440)  # tope 24 h
        hasta = datetime.now(timezone.utc) + timedelta(minutes=espera_min)
        cur.execute("""INSERT INTO sync_estado(clave, fallos, bloqueado_hasta, actualizado)
                       VALUES('login', %s, %s, now())
                       ON CONFLICT(clave) DO UPDATE SET fallos=%s, bloqueado_hasta=%s, actualizado=now()""",
                    (fallos, hasta, fallos, hasta))
    conn.commit()
    log.error("Login fallido (%s seguido(s)); en pausa hasta %s", fallos, hasta.isoformat())


def reemplazar_mes(conn, mes_ini, mes_fin, filas, extraccion):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM liquidaciones WHERE liqman_fechacreacion BETWEEN %s AND %s",
                    (mes_ini, mes_fin))
        if filas:
            valores = [tuple((extraccion if c == "fecha_extraccion" else f.get(c)) for c in COLUMNAS_TABLA)
                       for f in filas]
            cols = ", ".join(COLUMNAS_TABLA)
            execute_values(cur, f"INSERT INTO liquidaciones ({cols}) VALUES %s", valores)
    conn.commit()


# --- main ------------------------------------------------------------------
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not USUARIO or not CLAVE:
        raise SystemExit("Faltan SILOGTRAN_USUARIO / SILOGTRAN_CLAVE")
    modo, fi, ff = rango_por_modo()
    if ff < fi:
        raise SystemExit("La fecha final es menor que la inicial")

    conn = conectar()
    try:
        if freno_activo(conn):
            return  # salir 0: protección del usuario, no es error
        cliente = SilogtranClient(USUARIO, CLAVE)
        extraccion = datetime.now(timezone.utc)
        total, bloques = 0, meses(fi, ff)
        try:
            for mes_ini, mes_fin in bloques:
                filas = normalizar(cliente.consultar(mes_ini.isoformat(), mes_fin.isoformat()))
                reemplazar_mes(conn, mes_ini, mes_fin, filas, extraccion)
                total += len(filas)
                log.info("Mes %s: %s filas", mes_ini.strftime("%Y-%m"), len(filas))
            marcar_login_ok(conn)
            log.info("Sync OK (modo=%s, %s a %s): %s filas en %s mes(es)", modo, fi, ff, total, len(bloques))
        except CredencialesError as e:
            marcar_login_fallo(conn)
            raise SystemExit(f"No se pudo iniciar sesión en Silogtran: {e}")
        except EstructuraError as e:
            raise SystemExit(f"El informe de Silogtran cambió de columnas: {e}")
        except Exception as e:
            # transitorio (red/Silogtran/sesión): no toca el freno de login; el próximo cron reintenta
            raise SystemExit(f"Fallo en la consulta a Silogtran: {type(e).__name__}: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
