# Liquidaciones Silogtran → Supabase → QlikSense

Sincroniza el **Informe General de Liquidación de Manifiesto** de Silogtran hacia una base de datos
**Supabase (Postgres)**, para que **QlikSense (u otro BI) lea la tabla** directamente. No hay un servidor
prendido: un **job programado** (GitHub Actions) corre cada cierto tiempo, actualiza la base y termina.

> Antes esto era una API REST en Render que respondía en vivo; se dejó de usar porque el plan gratis de
> Render limita las horas de servicio. El código de esa API sigue en el repo (`api_liquidacion.py`) y el
> job **lo reutiliza** (cliente de Silogtran y esquema), pero el consumo hoy es contra Supabase.

---

## Qué hace

```
Silogtran ──(job cada 20 min, GitHub Actions)──▶ Supabase (tabla liquidaciones) ◀──(lee)── QlikSense
```

1. El job inicia sesión en Silogtran (login por formulario + centro de costo), pasa el **AWS WAF** con un
   Chromium headless, genera el informe en CSV y lo escribe en Supabase.
2. Trabaja **por mes calendario** con **reemplazo del mes**: en una transacción borra las filas de ese mes
   e inserta las frescas, así quedan reflejados cambios **y** borrados (no solo altas).
3. QlikSense se conecta **directo** a Postgres (usuario de solo lectura) y consulta la tabla. No hay que
   construir ni mantener ninguna API.

---

## Los datos

Tabla **`public.liquidaciones`**: una fila por manifiesto, con las mismas columnas del informe de
Silogtran. Llave **`id` = `liqman_codigo-manifiesto_codigo`**. La estructura completa está en
[`schema.sql`](schema.sql).

Reglas importantes (para que coincida con Silogtran):

- **Códigos y documentos: texto** (conservan ceros a la izquierda). Léelos como texto en el BI.
- **Montos: enteros**; si vienen vacíos en Silogtran, aquí son `0`.
- **`liqman_valortotal`** y **`saldo_final`** traen el valor en **una sola fila** por liquidación (en las
  demás filas de esa liquidación van en `0`): sumar la columna da el total **sin duplicar**.
- **`envio_correo` / `fecha_envio_correo`** están **vacíos cuando la liquidación aún no se envió**
  (pendiente): es lo mismo que muestra Silogtran, no es un dato perdido.
- `fecha_extraccion`: cuándo se actualizó cada fila (útil para cargas incrementales).

Columnas (orden del informe): `liqman_codigo`, `liqman_fechacreacion`, `transferencia_codigo`,
`comegr_codigo`, `vale_codigo`, `banco_nombre`, `beneficiario(_documento)`, `poseedor(_documento)`,
`vehiculo_placa`, `manifiesto_codigo`, `ruta`, `cliente_remesa_codigo`, fechas y montos del manifiesto,
tres bloques de anticipos (`anticipo_*`, `segundo_anticipo_*`, `tercer_anticipo_*`), `valor_total_anticipos`,
valores de la liquidación, cartera, `liqman_valortotal`, `saldo_final`, `liqman_observacion`,
`liquidacion_centro_costo`, `usuario_creacion`, `estado_liquidacion`, `estatus_sap`, `envio_correo`,
`fecha_envio_correo`. La lista exacta con tipos: `schema.sql`.

---

## Puesta en marcha

### 1. Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com) (plan gratis) y guarda la **Database Password**.
2. **SQL Editor** → ejecuta [`schema.sql`](schema.sql) (crea `liquidaciones` y `sync_estado`). Si te avisa
   de RLS, actívalo (es lo correcto; el job escribe como admin y no se ve afectado).
3. **Project Settings → Database → Connect → "Session pooler"**: copia la cadena, pon la contraseña y
   agrega `?sslmode=require`. Esa es tu `SUPABASE_DB_URL` (formato `postgres.<ref>` por el pooler, IPv4).

### 2. GitHub (Secrets)

En el repo → **Settings → Secrets and variables → Actions**:

| Secret | Valor |
|---|---|
| `SILOGTRAN_USUARIO` | usuario de Silogtran (una cuenta dedicada, solo lectura del informe) |
| `SILOGTRAN_CLAVE` | su contraseña |
| `SILOGTRAN_CENTROCOSTO` | centro de costo (ej. `1-1`; omítelo si solo hay uno) |
| `SUPABASE_DB_URL` | la cadena del paso 1 |
| `SILOGTRAN_URL` | opcional (por defecto construproyec) |

### 3. Carga inicial del histórico (una vez)

**Actions → "Sync por rango (backfill / histórico)" → Run workflow**, con `fecha_inicial` (ej.
`2024-01-01`) y `fecha_final` vacío (= hoy). Procesa mes por mes.

### 4. El cron queda corriendo solo

El workflow **"Sync reciente"** se ejecuta cada 20 min (mes actual + anterior). No hay que hacer nada más.

---

## Cómo lo consume QlikSense

No hay API: Supabase es la capa de exposición. QlikSense se conecta **directo a Postgres** con un usuario
de **solo lectura**. Ficha lista para entregar al equipo: [`CONEXION_QLIKSENSE.md`](CONEXION_QLIKSENSE.md).

Crear el usuario (una vez, en Supabase → SQL Editor):

```sql
create role qlik_ro login password 'UNA_CLAVE_FUERTE';
grant usage on schema public to qlik_ro;
grant select on public.liquidaciones to qlik_ro;
create policy qlik_lectura on public.liquidaciones for select to qlik_ro using (true);  -- si hay RLS
```

Luego el equipo usa el **conector PostgreSQL** de Qlik: host del *Session pooler*, puerto `5432`, base
`postgres`, usuario `qlik_ro.<ref>`, SSL `require`. Ejemplos:

```sql
select * from public.liquidaciones;
select * from public.liquidaciones
where liqman_fechacreacion between '2026-01-01' and '2026-01-31';
```

Para cargas incrementales, filtra por `liqman_fechacreacion` o `fecha_extraccion`.

---

## Cada cuánto se actualiza (el cron)

- GitHub Actions corre **"Sync reciente"** cada 20 min automáticamente (lo validas en la pestaña
  **Actions**). La programación puede retrasarse unos minutos si GitHub está cargado.
- Ajusta la frecuencia en la línea `cron:` de `.github/workflows/sync-reciente.yml`.
- **Minutos:** en repos **públicos** Actions es ilimitado (este repo lo es). En privados son 2000 min/mes,
  y ahí conviene bajar a cada hora (`0 * * * *`).
- El histórico casi no cambia: se re-sincroniza a mano con el workflow de backfill cuando haga falta.

---

## Estructura del repo

```
sync.py              Job de sincronización: rango por modo → Silogtran → Supabase (reemplaza cada mes)
api_liquidacion.py   Módulo reutilizado por el job: cliente de Silogtran (login+WAF+informe), esquema,
                     normalización. También puede correr como API REST local (modo anterior, opcional).
schema.sql           DDL de Supabase (tabla liquidaciones + sync_estado)
esquema / normalizar Dentro de api_liquidacion.py: columnas, tipos y limpieza del CSV
requirements.txt     requests, playwright, psycopg2-binary
.env.example         Variables de entorno (Silogtran, Supabase, WAF, modo sync)
CONEXION_QLIKSENSE.md Ficha de conexión para el equipo de QlikSense
.github/workflows/
  sync-reciente.yml  cron cada 20 min (mes actual + anterior)
  sync-backfill.yml  manual, por rango de fechas (histórico)
Dockerfile           Solo para correr el modo API REST en contenedor (anterior, opcional)
```

---

## Ejecutar en local

```bash
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env     # completa SILOGTRAN_* y SUPABASE_DB_URL
python sync.py             # MODE=reciente (mes actual + anterior)
# backfill:  set MODE=rango & set SYNC_FECHA_INICIAL=2025-01-01 & python sync.py
```

Para pasar el AWS WAF en local (Windows), apunta `WAF_CHROME_PATH` a tu Chrome, p. ej.
`C:\Program Files\Google\Chrome\Application\chrome.exe` (en GitHub Actions/Linux no hace falta).

---

## Cómo se construyó la integración con Silogtran

Silogtran **no tiene API** para sus informes. Está hecho en **PRADO** (framework PHP): cada pantalla se
arma en el servidor y los botones reenvían el formulario completo ("postback", con el estado en el campo
oculto `PRADO_PAGESTATE`). Además está detrás de **AWS WAF**, que a una petición de servidor le responde
con un *challenge* en JavaScript.

El job se comporta como un navegador:

1. **Login** (`index.php?page=LoginPage`): GET para leer `PRADO_PAGESTATE`, POST con
   `ctl0$MainModule$Usuario/$Clave/$BtnIngresar`, y luego el paso de **centro de costo** (`BtnContinuar`).
2. **AWS WAF**: cuando llega `x-amzn-waf-action: challenge`, un **Chromium headless** (Playwright) carga la
   página, obtiene la cookie `aws-waf-token` y se reintenta. El token queda en la sesión, así el navegador
   solo se abre al iniciar sesión. Lo ideal a futuro: que Colombia Software **autorice la IP** y no haga
   falta navegador.
3. **Informe** (`Despacho.Liquidacionmanifiesto.InformeGeneral_111`): POST del formulario con el rango de
   fechas y `tipoimpresion=CSV`; la respuesta trae un `window.open('../reportes/…')` con el CSV, que se
   descarga y se parsea.

> Este mismo patrón (login PRADO + AWS WAF con Chromium) se usa también en otros proyectos de Silogtran;
> está documentado como skill reutilizable.

---

## Seguridad y límites

- **Sin secretos en el código**: credenciales y `SUPABASE_DB_URL` van en `.env` (local, ignorado por git)
  o en GitHub Secrets. El repo es público; no hay claves adentro.
- **Usuario de QlikSense de solo lectura** (`qlik_ro`): solo puede `select` sobre `liquidaciones`; probado
  que un intento de escritura se rechaza. No se comparte el usuario admin ni la `service_role key`.
- **Protección del usuario de Silogtran**: si un login falla, el job guarda en `sync_estado` una pausa
  creciente (30 min → 2 h → 8 h → 24 h) y las corridas siguientes se saltan, para no bloquear la cuenta.
- **Límites del plan gratis de Supabase**: base 500 MB (de sobra; son decenas de MB), egress 5 GB/mes
  (fino con cargas incrementales), y se pausa tras ~1 semana sin actividad (no pasa: el job escribe seguido).
  Ya **no** hay límite de "horas de servicio" como en Render.

---

## Apéndice: modo API REST (anterior)

`api_liquidacion.py` todavía puede correr como API REST (`python api_liquidacion.py`, `http://localhost:8000`)
con endpoints `/v1/liquidaciones`, `/v1/esquema` y `/health`, protegidos con `Authorization: Bearer <API_KEY>`.
Fue el enfoque anterior (desplegado en Render). Hoy el consumo es vía Supabase; este modo queda como
referencia o para pruebas locales.

---

Todos los derechos reservados.
