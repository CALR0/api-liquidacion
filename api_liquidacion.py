"""API de solo lectura que expone el Informe General de Liquidación de Manifiesto de Silogtran.

Se consulta por rango de fechas (fecha de creación de la liquidación) y devuelve las mismas
columnas del informe, una fila por manifiesto, con tipos consistentes:
    - montos como enteros (vacío -> 0)
    - códigos, documentos y textos como texto (vacío -> null)
    - fechas como texto yyyy-MM-dd (fecha_envio_correo: yyyy-MM-dd HH:mm:ss)
Cada fila trae además "id" = liqman_codigo-manifiesto_codigo, útil como llave para almacenar.

Endpoints (todos con header  Authorization: Bearer <API_KEY>, salvo /health):
    GET /v1/liquidaciones?fechaInicial=yyyy-MM-dd&fechaFinal=yyyy-MM-dd[&offset=0&limit=1000]
    GET /v1/esquema       columnas, tipos y descripción
    GET /health           estado del servicio (sin token)

Rangos: se descargan meses completos (caché por mes) y se recortan al rango pedido.
Toda la configuración va en variables de entorno o en un archivo .env (ver .env.example).
"""

import csv
import gzip
import hmac
import io
import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests


def _cargar_env(path):
    """Carga KEY=VALUE de un archivo .env sin pisar variables ya definidas en el entorno."""
    if not path.is_file():
        return
    for linea in path.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


_cargar_env(Path(__file__).with_name(".env"))


def _env_int(nombre, defecto):
    return int(os.environ.get(nombre, "") or defecto)


BASE_URL = os.environ.get("SILOGTRAN_URL", "https://construproyec.colombiasoftware.net").rstrip("/")
USUARIO = os.environ.get("SILOGTRAN_USUARIO", "")
CLAVE = os.environ.get("SILOGTRAN_CLAVE", "")
CENTROCOSTO = os.environ.get("SILOGTRAN_CENTROCOSTO", "")
API_KEY = os.environ.get("API_KEY", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)

KEEPALIVE_MINUTOS = float(os.environ.get("KEEPALIVE_MINUTOS", "") or 10)
MAX_DIAS_RANGO = _env_int("MAX_DIAS_RANGO", 366)
DIAS_RECIENTES = _env_int("DIAS_RECIENTES", 7)
CACHE_MINUTOS_RECIENTE = _env_int("CACHE_MINUTOS_RECIENTE", 15)
CACHE_MINUTOS_HISTORICO = _env_int("CACHE_MINUTOS_HISTORICO", 15)
CACHE_MAX_BLOQUES = _env_int("CACHE_MAX_BLOQUES", 100)
LIMITE_DEFECTO = _env_int("LIMITE_DEFECTO", 1000)
LIMITE_MAXIMO = _env_int("LIMITE_MAXIMO", 10000)
REINTENTOS = _env_int("REINTENTOS", 3)
TIMEOUT_SILOGTRAN_SEG = _env_int("TIMEOUT_SILOGTRAN_SEG", 300)
MAX_PETICIONES_MINUTO = _env_int("MAX_PETICIONES_MINUTO", 20)
# Autoping: llama a su propia URL pública para que el hosting gratuito no la duerma.
# Render define RENDER_EXTERNAL_URL automáticamente; AUTOPING_URL permite indicarla a mano.
AUTOPING_URL = (os.environ.get("AUTOPING_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
AUTOPING_MINUTOS = float(os.environ.get("AUTOPING_MINUTOS", "") or 10)
# Cada cuántos minutos se refresca en segundo plano el mes en curso (0 = desactivado)
PRECARGA_MINUTOS = float(os.environ.get("PRECARGA_MINUTOS", "") or 10)
# Protección del usuario de Silogtran contra bloqueo por intentos de ingreso:
# tras un login fallido no se vuelve a intentar hasta pasados LOGIN_ESPERA_MINUTOS (se duplica con
# cada fallo seguido, hasta 4 h), y nunca se hacen más de LOGIN_MAX_POR_HORA logins por hora.
LOGIN_ESPERA_MINUTOS = _env_int("LOGIN_ESPERA_MINUTOS", 15)
LOGIN_MAX_POR_HORA = _env_int("LOGIN_MAX_POR_HORA", 3)

ZONA = timezone(timedelta(hours=-5))  # Colombia, sin horario de verano
LOGIN_URL = f"{BASE_URL}/index.php?page=LoginPage"
PAGE_URL = f"{BASE_URL}/index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111"
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PARAMETROS = {"fechaInicial", "fechaFinal", "offset", "limit"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api_liquidacion")


def ahora():
    return datetime.now(ZONA)


# ---------------------------------------------------------------------------
# Esquema del informe
# ---------------------------------------------------------------------------

_SOLO_UNA_FILA = ("Valor de la liquidación: viene solo en una fila por liquidación (en las demás "
                  "filas de la misma liquidación es 0); sumar sin duplicar.")
_LISTA = "Puede traer varios valores separados por coma."

# (columna, tipo, descripción). El orden es el del informe de Silogtran.
ESQUEMA = [
    ("liqman_codigo", "texto", "Código de la liquidación"),
    ("liqman_fechacreacion", "fecha", "Fecha de creación de la liquidación (es la que filtra el rango)"),
    ("transferencia_codigo", "texto", ""),
    ("comegr_codigo", "texto", "Comprobante de egreso"),
    ("vale_codigo", "texto", ""),
    ("banco_nombre", "texto", ""),
    ("beneficiario", "texto", ""),
    ("beneficiario_documento", "texto", ""),
    ("poseedor", "texto", ""),
    ("poseedor_documento", "texto", ""),
    ("vehiculo_placa", "texto", ""),
    ("manifiesto_codigo", "texto", ""),
    ("ruta", "texto", "Origen - destino"),
    ("cliente_remesa_codigo", "texto", "Cliente - remesa. " + _LISTA),
    ("manifiesto_fecha_creacion", "fecha", ""),
    ("manifiesto_fecha_cumplido", "fecha", ""),
    ("flete_real_despacho", "entero", ""),
    ("descuento_cumplido_manifiesto", "entero", ""),
    ("valores_adicionales_cumplido_manifiesto", "entero", ""),
    ("impuesto_manifiesto_retefuente", "entero", ""),
    ("impuesto_manifiesto_reteica", "entero", ""),
    ("descuento_fopat", "entero", ""),
    ("anticipo_codigo", "texto", _LISTA),
    ("anticipo_fecha_creacion", "texto", "Fecha(s) yyyy-MM-dd. " + _LISTA),
    ("anticipo_tipo_pago", "texto", ""),
    ("anticipo_valor_confirmado", "entero", ""),
    ("segundo_anticipo_codigo", "texto", _LISTA),
    ("segundo_anticipo_fecha_creacion", "texto", "Fecha(s) yyyy-MM-dd. " + _LISTA),
    ("segundo_anticipo_tipo_pago", "texto", ""),
    ("segundo_anticipo_valor_confirmado", "entero", ""),
    ("tercer_anticipo_codigo", "texto", _LISTA),
    ("tercer_anticipo_fecha_creacion", "texto", "Fecha(s) yyyy-MM-dd. " + _LISTA),
    ("tercer_anticipo_tipo_pago", "texto", ""),
    ("tercer_anticipo_valor_confirmado", "entero", ""),
    ("valor_total_anticipos", "entero", ""),
    ("manifiesto_valor_a_cancelar", "entero", ""),
    ("descuento_liquidacion_manifiesto", "entero", ""),
    ("valores_adicionales_liquidacion_cumplido_manifiesto", "entero", ""),
    ("liqman_valortotal", "entero", _SOLO_UNA_FILA),
    ("valor_cartera_trasportador_manifiesto_anulado", "entero", ""),
    ("codigo_manifiesto_cartera_trasportador_manifiesto_anulado", "texto", ""),
    ("valor_cartera_trasportador_descuento_cumplido", "entero", ""),
    ("codigo_manifiesto_cartera_trasportador_descuento_cumplido", "texto", ""),
    ("valor_cartera_transportador_contabilidad_sap", "entero", ""),
    ("saldo_final", "entero", _SOLO_UNA_FILA),
    ("liqman_observacion", "texto", ""),
    ("liquidacion_centro_costo", "texto", ""),
    ("usuario_creacion", "texto", ""),
    ("estado_liquidacion", "texto", ""),
    ("estatus_sap", "texto", ""),
    ("envio_correo", "texto", "SI / NO"),
    ("fecha_envio_correo", "fecha_hora", "yyyy-MM-dd HH:mm:ss"),
]
COLUMNAS = [c for c, _, _ in ESQUEMA]
NUMERICAS = {c for c, t, _ in ESQUEMA if t == "entero"}
ESQUEMA_JSON = {
    "version": "v1",
    "llave": "id",
    "columnas": [{"nombre": "id", "tipo": "texto", "descripcion": "liqman_codigo-manifiesto_codigo (único por fila)"}]
                + [{"nombre": c, "tipo": t, "descripcion": d} for c, t, d in ESQUEMA],
}


class SilogtranError(Exception):
    pass


class CredencialesError(SilogtranError):
    """Error que no se arregla reintentando (usuario/clave/centro de costo)."""


class EstructuraError(SilogtranError):
    """El informe de Silogtran cambió sus columnas."""


class SesionEnPausa(SilogtranError):
    """Inicio de sesión suspendido temporalmente para no bloquear el usuario de Silogtran."""

    def __init__(self, hasta):
        self.hasta = hasta
        super().__init__(f"Inicio de sesión en Silogtran en pausa hasta {hasta.isoformat(timespec='seconds')}")


def normalizar(filas_csv):
    """Convierte las filas del CSV al esquema fijo de la API."""
    if not filas_csv:
        return []
    encabezado = {k for k in filas_csv[0] if k}
    faltan = [c for c in COLUMNAS if c not in encabezado]
    if faltan:
        raise EstructuraError(f"El informe de Silogtran ya no trae las columnas: {faltan}")
    extra = encabezado - set(COLUMNAS)
    if extra:
        log.warning("El informe trae columnas nuevas que la API ignora: %s", sorted(extra))

    salida = []
    for f in filas_csv:
        fila = {"id": None}
        for c in COLUMNAS:
            v = (f.get(c) or "").strip()
            if c in NUMERICAS:
                try:
                    fila[c] = int(float(v)) if v else 0
                except ValueError:
                    log.warning("Valor no numérico en %s: %r", c, v)
                    fila[c] = 0
            else:
                fila[c] = v or None
        fila["id"] = f"{fila['liqman_codigo']}-{fila['manifiesto_codigo']}"
        salida.append(fila)
    return salida


# ---------------------------------------------------------------------------
# Cliente de Silogtran (sesión automática)
# ---------------------------------------------------------------------------

def _hidden(html, name):
    for tag in re.findall(r"<input[^>]*>", html, re.I):
        if f'name="{name}"' in tag:
            m = re.search(r'value="([^"]*)"', tag)
            return m.group(1) if m else ""
    return None


def _campos_ocultos(html):
    campos = {}
    for tag in re.findall(r"<input[^>]*>", html, re.I):
        if re.search(r'type="hidden"', tag, re.I):
            n = re.search(r'name="([^"]+)"', tag)
            v = re.search(r'value="([^"]*)"', tag)
            if n:
                campos[n.group(1)] = unescape(v.group(1)) if v else ""
    return campos


def _opciones(html, name):
    m = re.search(rf'<select[^>]*name="{re.escape(name)}"[^>]*>([\s\S]*?)</select>', html, re.I)
    return [unescape(v) for v in re.findall(r'<option[^>]*value="([^"]*)"', m.group(1))] if m else []


class SilogtranClient:
    """Mantiene una sesión de Silogtran: la crea, la mantiene viva y la renueva cuando vence.
    La cookie vive solo en memoria (nunca se escribe en disco ni en logs).
    Solo lectura: únicamente inicia sesión y genera el informe."""

    def __init__(self, usuario, clave):
        self._usuario = usuario
        self._clave = clave
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (api-liquidacion)"
        self.lock = threading.Lock()  # PRADO maneja estado por sesión: una operación a la vez
        self.ultima_ok = None
        self.fallos_login = 0
        self.pausa_hasta = None   # mientras esté vigente no se intenta iniciar sesión
        self.logins = deque()     # momentos de los últimos logins (límite por hora)

    def __repr__(self):
        return "SilogtranClient(<credenciales ocultas>)"

    def _login(self):
        log.info("Iniciando sesión en Silogtran")
        self.session.cookies.clear()
        html = self.session.get(LOGIN_URL, timeout=60).text
        data = {
            "PRADO_PAGESTATE": _hidden(html, "PRADO_PAGESTATE") or "",
            "PRADO_POSTBACK_TARGET": "ctl0$MainModule$BtnIngresar",
            "PRADO_POSTBACK_PARAMETER": "",
            "ctl0$MainModule$usuario_codigo": "",
            "ctl0$MainModule$usuario_clave": "",
            "ctl0$MainModule$Usuario": self._usuario,
            "ctl0$MainModule$Clave": self._clave,
            "ctl0$MainModule$BtnIngresar": "Ingresar",
            "ctl0$MainModule$IDLockHidden_ctl0_MainModule_BtnIngresar": "true",
        }
        html = self.session.post(LOGIN_URL, data=data, timeout=60).text

        # Paso 2: Silogtran pide elegir el centro de costo antes de entrar
        opciones = _opciones(html, "ctl0$MainModule$centrocosto")
        if opciones:
            validas = [v for v in opciones if v != "PLACEHOLDER"]
            centro = CENTROCOSTO or (validas[0] if len(validas) == 1 else "")
            if centro not in validas:
                raise CredencialesError(
                    f"Defina SILOGTRAN_CENTROCOSTO con uno de: {', '.join(validas) or '(ninguno)'}")
            data = _campos_ocultos(html)
            data.update({
                "PRADO_POSTBACK_TARGET": "ctl0$MainModule$BtnContinuar",
                "PRADO_POSTBACK_PARAMETER": "",
                "ctl0$MainModule$centrocosto": centro,
                "ctl0$MainModule$BtnContinuar": "Continuar",
            })
            self.session.post(LOGIN_URL, data=data, timeout=60)

    def _cargar_formulario(self):
        """Devuelve el HTML del informe o None si la sesión no es válida."""
        r = self.session.get(PAGE_URL, timeout=60)
        if "LoginPage" in r.url or _hidden(r.text, "ctl0$MainModule$factura_fechainicial") is None:
            return None
        return r.text

    def _login_controlado(self):
        """Único punto de entrada al login. Un solo intento a la vez (lo garantiza self.lock),
        pausa creciente tras cada fallo y tope de logins por hora: así la API nunca bombardea
        Silogtran con intentos aunque lleguen muchas consultas o la sesión se caiga en bucle."""
        t = ahora()
        if self.pausa_hasta and t < self.pausa_hasta:
            raise SesionEnPausa(self.pausa_hasta)
        while self.logins and t - self.logins[0] >= timedelta(hours=1):
            self.logins.popleft()
        if len(self.logins) >= LOGIN_MAX_POR_HORA:
            self.pausa_hasta = self.logins[0] + timedelta(hours=1)
            log.error("Se alcanzó el máximo de %s inicios de sesión por hora; la sesión se cae seguido "
                      "(¿otra persona usa el mismo usuario?). Pausa hasta %s",
                      LOGIN_MAX_POR_HORA, self.pausa_hasta.isoformat(timespec="seconds"))
            raise SesionEnPausa(self.pausa_hasta)
        self.logins.append(t)
        try:
            self._login()
            html = self._cargar_formulario()
            if html is None:
                raise CredencialesError("No se pudo iniciar sesión en Silogtran: revise usuario/clave "
                                        "o si el usuario está inactivo")
        except Exception as e:
            self.fallos_login += 1
            espera = min(LOGIN_ESPERA_MINUTOS * 2 ** (self.fallos_login - 1), 240)
            self.pausa_hasta = t + timedelta(minutes=espera)
            log.error("Inicio de sesión fallido (%s seguido(s)): %s. No se reintentará hasta %s",
                      self.fallos_login, e if isinstance(e, CredencialesError) else type(e).__name__,
                      self.pausa_hasta.isoformat(timespec="seconds"))
            raise CredencialesError(str(e)) if not isinstance(e, CredencialesError) else e
        self.fallos_login, self.pausa_hasta = 0, None
        log.info("Sesión iniciada en Silogtran (%s login(s) en la última hora)", len(self.logins))
        return html

    def _formulario_con_sesion(self):
        """Reutiliza la sesión vigente; solo inicia sesión si Silogtran la dio por vencida."""
        html = self._cargar_formulario()
        return html if html is not None else self._login_controlado()

    def keepalive(self):
        """Toca el formulario para que la sesión no venza por inactividad. Nunca inicia sesión:
        si la sesión ya no existe, la siguiente consulta (o la precarga) la abrirá de forma controlada."""
        with self.lock:
            if self._cargar_formulario() is None:
                log.info("Keepalive: la sesión no está activa; se abrirá en la próxima consulta")

    def iniciar(self):
        with self.lock:
            self._formulario_con_sesion()

    def estado(self):
        en_pausa = bool(self.pausa_hasta and ahora() < self.pausa_hasta)
        return {
            "login_en_pausa_hasta": self.pausa_hasta.isoformat(timespec="seconds") if en_pausa else None,
            "logins_ultima_hora": sum(1 for x in self.logins if ahora() - x < timedelta(hours=1)),
        }

    def consultar(self, fecha_inicial, fecha_final):
        """Genera el informe en CSV para el rango y devuelve las filas crudas."""
        with self.lock:
            html = self._formulario_con_sesion()
            data = {
                "PRADO_PAGESTATE": _hidden(html, "PRADO_PAGESTATE") or "",
                "PRADO_POSTBACK_TARGET": "ctl0$MainModule$ctl3",
                "PRADO_POSTBACK_PARAMETER": "",
                "ctl0$MainModule$factura_fechainicial": fecha_inicial,
                "ctl0$MainModule$factura_fechafinal": fecha_final,
                "ctl0$MainModule$factura_tipoimpresion": "CSV",
                "ctl0$MainModule$beneficiario_codigo": "",
                "ctl0$MainModule$beneficiario_codigo$IDHidden": "",
                "ctl0$MainModule$usuario_codigo": "",
                "ctl0$MainModule$usuario_codigo$IDHidden": "",
                "ctl0$MainModule$IDLockHidden_ctl0_MainModule_ctl3": "true",
                "ctl0$MainModule$grabar_uuid": _hidden(html, "ctl0$MainModule$grabar_uuid") or "",
                "ctl0$MainModule$ctl3": "Generar",
            }
            r = self.session.post(PAGE_URL, data=data, timeout=TIMEOUT_SILOGTRAN_SEG)
            if "LoginPage" in r.url:  # la sesión se cayó en medio de la consulta: no es "sin datos"
                raise SilogtranError("La sesión de Silogtran se cerró durante la consulta")
            resp = r.text
            m = re.search(r"window\.open\('\.\./(reportes/[^']+)'\)", resp)
            if not m:
                self.ultima_ok = ahora()
                return []  # Silogtran no genera archivo cuando no hay datos
            raw = self.session.get(f"{BASE_URL}/{m.group(1)}", timeout=TIMEOUT_SILOGTRAN_SEG).content
            self.ultima_ok = ahora()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _bucle_keepalive(client):
    while True:
        time.sleep(KEEPALIVE_MINUTOS * 60)
        try:
            client.keepalive()
        except Exception as e:  # el siguiente intento o la siguiente consulta reintentan
            log.warning("Keepalive falló: %s", type(e).__name__)


def _bucle_autoping(url):
    """Petición periódica a la URL pública (pasa por el proxy del hosting y cuenta como tráfico)."""
    while True:
        time.sleep(AUTOPING_MINUTOS * 60)
        try:
            requests.get(f"{url}/health", timeout=30)
        except requests.RequestException as e:
            log.warning("Autoping falló: %s", type(e).__name__)


# ---------------------------------------------------------------------------
# Caché por bloques de fechas
# ---------------------------------------------------------------------------

def bloques(fi, ff):
    """Meses calendario completos que cubren [fi, ff]. Siempre se descarga y guarda el mes
    entero, así cualquier día o rango dentro de un mes ya consultado sale de la caché."""
    res, a = [], fi.replace(day=1)
    while a <= ff:
        siguiente_mes = (a + timedelta(days=32)).replace(day=1)
        res.append((a, siguiente_mes - timedelta(days=1)))
        a = siguiente_mes
    return res


class Repositorio:
    """Obtiene filas por rango usando caché por bloque, reintentos y respaldo con datos
    anteriores si Silogtran falla."""

    def __init__(self, client):
        self.client = client
        self.cache = {}  # (inicio, fin) -> (momento, filas)
        self.lock = threading.Lock()

    def _ttl(self, fin):
        reciente = fin >= ahora().date() - timedelta(days=DIAS_RECIENTES)
        return timedelta(minutes=CACHE_MINUTOS_RECIENTE if reciente else CACHE_MINUTOS_HISTORICO)

    def _descargar(self, a, b):
        ultimo = None
        for intento in range(1, REINTENTOS + 1):
            try:
                return normalizar(self.client.consultar(a.isoformat(), b.isoformat()))
            except (CredencialesError, EstructuraError, SesionEnPausa):
                raise  # reintentar no lo arregla y solo sumaría intentos de login
            except (SilogtranError, requests.RequestException) as e:
                ultimo = e
                log.warning("Silogtran falló (intento %s/%s, %s a %s): %s",
                            intento, REINTENTOS, a, b, type(e).__name__)
                if intento < REINTENTOS:
                    time.sleep(2 ** intento)
        raise SilogtranError(f"Silogtran no respondió tras {REINTENTOS} intentos") from ultimo

    def _guardar(self, a, b, datos):
        momento = ahora()
        self.cache[(a, b)] = (momento, datos)
        while len(self.cache) > CACHE_MAX_BLOQUES:
            del self.cache[min(self.cache, key=lambda k: self.cache[k][0])]
        return momento

    def refrescar(self, a, b):
        """Descarga el bloque aunque siga vigente en caché (precarga del mes en curso)."""
        with self.lock:
            self._guardar(a, b, self._descargar(a, b))

    def obtener(self, fi, ff):
        filas, momentos = [], []
        desde_cache, desactualizado = True, False
        desde, hasta = fi.isoformat(), ff.isoformat()
        for a, b in bloques(fi, ff):
            with self.lock:  # una descarga a la vez; peticiones iguales simultáneas esperan y usan la caché
                entrada = self.cache.get((a, b))
                if entrada and ahora() - entrada[0] < self._ttl(b):
                    momento, datos = entrada
                else:
                    desde_cache = False
                    try:
                        datos = self._descargar(a, b)
                        momento = self._guardar(a, b, datos)
                    except SilogtranError as e:
                        if not entrada or isinstance(e, EstructuraError):
                            raise
                        log.warning("Se entregan datos anteriores para %s a %s", a, b)
                        momento, datos = entrada
                        desactualizado = True
            # El bloque es el mes completo: se recorta al rango pedido (mismo criterio de Silogtran)
            filas.extend(f for f in datos if desde <= (f["liqman_fechacreacion"] or "") <= hasta)
            momentos.append(momento)
        return filas, min(momentos), desde_cache, desactualizado


def _bucle_precarga(repo):
    """Mantiene el mes en curso siempre en caché, para que las consultas recientes no esperen a Silogtran."""
    while True:
        a, b = bloques(ahora().date(), ahora().date())[0]
        try:
            repo.refrescar(a, b)
        except Exception as e:
            log.warning("Precarga falló: %s", type(e).__name__)
        time.sleep(PRECARGA_MINUTOS * 60)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, por_minuto):
        self.por_minuto = por_minuto
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def permitir(self, ip):
        t = time.monotonic()
        with self.lock:
            q = self.hits[ip]
            while q and t - q[0] > 60:
                q.popleft()
            if len(q) >= self.por_minuto:
                return False
            q.append(t)
            return True


CLIENT = None
REPO = None
LIMITER = RateLimiter(MAX_PETICIONES_MINUTO)


class Handler(BaseHTTPRequestHandler):
    server_version = "api-liquidacion"
    sys_version = ""

    def log_request(self, code="-", size="-"):
        # Solo la ruta (sin query string) para no dejar parámetros en los logs; /health no se registra
        if urlparse(self.path).path == "/health":
            return
        ms = int((time.monotonic() - getattr(self, "_t0", time.monotonic())) * 1000)
        log.info("%s %s %s %s %sms", self.client_ip(), self.command, urlparse(self.path).path, code, ms)

    def log_message(self, fmt, *args):
        pass  # los errores de protocolo no se registran (podrían incluir la ruta con parámetros)

    def client_ip(self):
        # Detrás del proxy del hosting la IP real viene en X-Forwarded-For
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def _json(self, status, body, headers=None):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if "gzip" in self.headers.get("Accept-Encoding", "") and len(payload) > 1024:
            payload = gzip.compress(payload, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status, codigo, mensaje, headers=None):
        self._json(status, {"error": {"codigo": codigo, "mensaje": mensaje}}, headers)

    def _autorizado(self):
        esquema, _, token = self.headers.get("Authorization", "").partition(" ")
        return esquema.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), API_KEY.encode())

    def do_GET(self):
        self._t0 = time.monotonic()
        url = urlparse(self.path)
        if url.path == "/health":
            return self._json(200, {
                "ok": True,
                "ultima_consulta_silogtran_ok": CLIENT.ultima_ok.isoformat() if CLIENT.ultima_ok else None,
                "bloques_en_cache": len(REPO.cache),
                **CLIENT.estado(),
            })
        if url.path not in ("/v1/liquidaciones", "/v1/esquema"):
            return self._error(404, "no_encontrado", "Rutas: /v1/liquidaciones, /v1/esquema, /health")
        if not self._autorizado():
            return self._error(401, "no_autorizado", "Token inválido o ausente (Authorization: Bearer <API_KEY>)",
                               {"WWW-Authenticate": 'Bearer realm="api-liquidacion"'})
        if not LIMITER.permitir(self.client_ip()):
            return self._error(429, "demasiadas_peticiones", f"Máximo {MAX_PETICIONES_MINUTO} consultas por minuto")
        if url.path == "/v1/esquema":
            return self._json(200, ESQUEMA_JSON)
        self._liquidaciones(url)

    def _liquidaciones(self, url):
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        otros = sorted(set(q) - PARAMETROS)
        if otros:
            return self._error(400, "parametro_invalido",
                               f"Parámetros no soportados: {otros}. Use: {sorted(PARAMETROS)}")
        try:
            if not (FECHA_RE.match(q.get("fechaInicial", "")) and FECHA_RE.match(q.get("fechaFinal", ""))):
                raise ValueError
            fi, ff = date.fromisoformat(q["fechaInicial"]), date.fromisoformat(q["fechaFinal"])
        except ValueError:
            return self._error(400, "fecha_invalida", "fechaInicial y fechaFinal son obligatorias (yyyy-MM-dd)")
        if ff < fi:
            return self._error(400, "rango_invalido", "fechaFinal debe ser mayor o igual a fechaInicial")
        if (ff - fi).days + 1 > MAX_DIAS_RANGO:
            return self._error(400, "rango_invalido", f"El rango máximo es de {MAX_DIAS_RANGO} días")
        try:
            offset = int(q.get("offset", 0))
            limit = int(q.get("limit", LIMITE_DEFECTO))
            if offset < 0 or not 1 <= limit <= LIMITE_MAXIMO:
                raise ValueError
        except ValueError:
            return self._error(400, "paginacion_invalida", f"offset >= 0 y limit entre 1 y {LIMITE_MAXIMO}")

        try:
            filas, extraccion, desde_cache, desactualizado = REPO.obtener(fi, ff)
        except SesionEnPausa as e:
            espera = max(60, int((e.hasta - ahora()).total_seconds()))
            return self._error(503, "silogtran_sesion_en_pausa",
                               "El inicio de sesión en Silogtran está en pausa para proteger el usuario; "
                               "intente más tarde", {"Retry-After": str(espera)})
        except CredencialesError as e:
            return self._error(502, "silogtran_sesion", "No se pudo iniciar sesión en Silogtran")
        except EstructuraError as e:
            log.error("%s", e)
            return self._error(502, "silogtran_estructura", str(e))
        except (SilogtranError, requests.RequestException) as e:
            log.error("Error con Silogtran: %s", e)
            return self._error(503, "silogtran_no_disponible", "Silogtran no respondió; intente más tarde",
                               {"Retry-After": "120"})

        pagina = filas[offset:offset + limit]
        siguiente = None
        if offset + limit < len(filas):
            siguiente = "/v1/liquidaciones?" + urlencode({
                "fechaInicial": fi.isoformat(), "fechaFinal": ff.isoformat(),
                "offset": offset + limit, "limit": limit})
        self._json(200, {
            "meta": {
                "fechaInicial": fi.isoformat(),
                "fechaFinal": ff.isoformat(),
                "total": len(filas),
                "offset": offset,
                "limit": limit,
                "devueltos": len(pagina),
                "siguiente": siguiente,
                "fecha_extraccion": extraccion.isoformat(timespec="seconds"),
                "desde_cache": desde_cache,
                "desactualizado": desactualizado,
            },
            "datos": pagina,
        })


def main():
    global CLIENT, REPO
    faltan = [k for k, v in {"SILOGTRAN_USUARIO": USUARIO, "SILOGTRAN_CLAVE": CLAVE}.items() if not v]
    if faltan:
        raise SystemExit(f"Faltan variables: {', '.join(faltan)} (ver .env.example)")
    if len(API_KEY) < 24:
        raise SystemExit("API_KEY debe tener al menos 24 caracteres. Genere una con:\n"
                         '  python -c "import secrets; print(secrets.token_urlsafe(32))"')

    CLIENT = SilogtranClient(USUARIO, CLAVE)
    REPO = Repositorio(CLIENT)
    def _login_inicial():
        try:
            CLIENT.iniciar()  # un único login al arrancar (controlado)
        except Exception as e:
            log.warning("No se pudo iniciar sesión al arrancar: %s", type(e).__name__)
    # En segundo plano: el puerto abre de inmediato aunque Silogtran tarde en responder
    threading.Thread(target=_login_inicial, daemon=True).start()
    if KEEPALIVE_MINUTOS > 0:
        threading.Thread(target=_bucle_keepalive, args=(CLIENT,), daemon=True).start()
    if AUTOPING_URL and AUTOPING_MINUTOS > 0:
        log.info("Autoping activo cada %s min", AUTOPING_MINUTOS)
        threading.Thread(target=_bucle_autoping, args=(AUTOPING_URL,), daemon=True).start()
    if PRECARGA_MINUTOS > 0:
        log.info("Precarga del mes en curso cada %s min", PRECARGA_MINUTOS)
        threading.Thread(target=_bucle_precarga, args=(REPO,), daemon=True).start()

    log.info("API escuchando en http://%s:%s/v1/liquidaciones", HOST, PORT)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
