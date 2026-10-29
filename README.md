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
Silogtran ──(job 3 veces/día, GitHub Actions)──▶ Supabase (tabla liquidaciones) ◀──(lee)── QlikSense
```

1. El job inicia sesión en Silogtran (login por formulario + centro de costo), pasa el **AWS WAF** con un
   Chromium headless, genera el informe en CSV y lo escribe en Supabase.
2. Trabaja **por mes calendario**: en una transacción **inserta o actualiza** cada fila por `id` y borra
   las que ya no vienen en el informe, **salvo las que tienen corte** (esas nunca se borran).
   `cod_corte` y `fecha_corte` nunca los modifica el sync.
3. **Cortes de liquidación:** la persona de liquidaciones pulsa **"Cerrar corte"** (extensión de Chrome) y
   las liquidaciones nuevas quedan marcadas con el siguiente `cod_corte`. Ver [Cortes](#cortes-de-liquidación).
4. QlikSense se conecta **directo** a Postgres (usuario de solo lectura) y consulta la tabla. No hay que
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
- **`cod_corte` / `fecha_corte`**: corte al que pertenece la liquidación y cuándo se cerró. Vacíos en las
  liquidaciones anteriores a los cortes o aún no incluidas en uno. Una vez asignados **no cambian nunca**,
  aunque la liquidación se anule (solo cambia `estado_liquidacion`).

Columnas (orden del informe): `liqman_codigo`, `liqman_fechacreacion`, `transferencia_codigo`,
`comegr_codigo`, `vale_codigo`, `banco_nombre`, `beneficiario(_documento)`, `poseedor(_documento)`,
`vehiculo_placa`, `manifiesto_codigo`, `ruta`, `cliente_remesa_codigo`, fechas y montos del manifiesto,
tres bloques de anticipos (`anticipo_*`, `segundo_anticipo_*`, `tercer_anticipo_*`), `valor_total_anticipos`,
valores de la liquidación, cartera, `liqman_valortotal`, `saldo_final`, `liqman_observacion`,
`liquidacion_centro_costo`, `usuario_creacion`, `estado_liquidacion`, `estatus_sap`, `envio_correo`,
`fecha_envio_correo`, y al final `fecha_extraccion`, `cod_corte`, `fecha_corte`. La lista exacta con
tipos: `schema.sql`.

---

## Puesta en marcha

### 1. Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com) (plan gratis) y guarda la **Database Password**.
2. **SQL Editor** → ejecuta [`schema.sql`](schema.sql) (crea `liquidaciones` y `sync_estado`).
   Si la base ya existía, ejecuta en cambio [`migracion_cortes.sql`](migracion_cortes.sql). Si te avisa
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

Y en la pestaña **Variables** (no son secretos) para los cortes:

| Variable | Valor |
|---|---|
| `CORTE_INICIAL` | número del primer corte (ej. `1`) |
| `CORTES_DESDE` | fecha `yyyy-MM-dd` desde la que cuentan los cortes (las liquidaciones anteriores quedan sin corte) |

### 3. Carga inicial del histórico (una vez)

**Actions → "Sync por rango (backfill / histórico)" → Run workflow**, con `fecha_inicial` (ej.
`2024-01-01`) y `fecha_final` vacío (= hoy). Procesa mes por mes.

### 4. El disparo del sync

El workflow **"Sync reciente"** (mes en curso + mes anterior) se dispara **3 veces al día** (6 a.m.,
2 p.m. y 6 p.m. Colombia) desde un **cron externo** (cron-job.org) que llama a `workflow_dispatch`. Se configura
como se explica más abajo. No se usa el schedule nativo de GitHub (impreciso).

---

## Cortes de liquidación

La persona de liquidaciones trabaja por **cortes**: hace un grupo de liquidaciones en Silogtran y, al
terminar, pulsa **"▶ Cerrar corte"** en la extensión de Chrome. Las liquidaciones nuevas quedan marcadas
con un `cod_corte` que se autoincrementa en cada corte.

```
8–10 a.m. liquida → play 10:00 → corte N   (las de 8–10)
10–12     liquida → play 12:15 → corte N+1 (solo las nuevas)
6 a.m. / 2 p.m. / 6 p.m. → cron normal: actualiza datos, NUNCA asigna ni cambia cortes
```

Cómo funciona (workflow **"Cerrar corte de liquidación"**, `corte.yml`, `MODE=corte`):

1. Sincroniza mes anterior + mes en curso (igual que el cron) para traer lo último de Silogtran.
2. Toma las filas **sin corte** con `liqman_fechacreacion >= CORTES_DESDE` y les asigna el siguiente número:
   `max(último corte + 1, CORTE_INICIAL)`. Así nunca se repite un número; subir `CORTE_INICIAL` hace saltar
   la numeración.
3. Si no hay liquidaciones nuevas **no crea corte** ni gasta número.
4. Todo queda en la misma tabla `liquidaciones` (`cod_corte` y `fecha_corte`); no hay tablas extra. El
   resultado (número y cantidad) queda en la corrida de Actions y lo muestra la extensión.

Garantías:
- El corte es **por liquidación**: todos sus manifiestos llevan el mismo; un manifiesto agregado después
  **hereda** el corte de su liquidación.
- `cod_corte` **nunca cambia ni se borra**: el sync solo actualiza los demás campos (estado, montos, SAP…)
  y no borra filas con corte.
- Comparte la fila (`concurrency`) con los crons: si coincide con uno, espera a que termine.

### Extensión de Chrome (`extension-corte/`)

Instalación (una vez, en el equipo de la persona de liquidaciones):

1. **Token:** GitHub → Settings → Developer settings → **Fine-grained tokens** → New token, solo el repo
   `api-liquidacion`, permiso **Actions: Read and write**.
2. Chrome → `chrome://extensions` → activar **Modo de desarrollador** → **Cargar descomprimida** → elegir
   la carpeta `extension-corte`.
3. **Supabase → SQL Editor:** ejecutar [`exportar_corte.sql`](exportar_corte.sql) reemplazando
   `REEMPLACE_POR_UNA_CLAVE_LARGA` por una clave larga y aleatoria (la **clave de exportación**). Crea la
   función que entrega solo las filas de un corte y activa RLS en `liquidaciones` (sin afectar a QlikSense).
4. Clic en el ícono de la extensión → **⚙** (arriba a la derecha; la primera vez se abre sola) → **Guardar** con:
   - **Token de GitHub** (solo el `github_pat_…`, sin `Bearer`).
   - **URL del proyecto** de Supabase (`https://xxxx.supabase.co`) y su **clave pública** (anon / publishable;
     nunca la `service_role` / secret).
   - La **clave de exportación** del paso 3.

Todo ocurre en la ventanita de la extensión, en la misma ventana del navegador: no abre pestañas ni páginas.

Uso: clic en el ícono → **▶ Cerrar corte** → confirmar. En 1–3 minutos muestra, por ejemplo,
*"✅ Corte 15: 12 liquidaciones (30 filas)"*. Hay que dejar abierta la ventanita mientras procesa; si se
cierra, el corte igual se completa y al abrirla de nuevo se descarga con el mismo botón (último corte).

**Descargar el corte:** la ventanita tiene un solo botón de descarga, sin campos para escribir. Tras
procesar, apunta al corte recién creado (**"⬇ Descargar corte N (Excel)"**); si no se ha procesado uno en
esa sesión, baja el **último corte** que haya en Supabase. Descarga `liquidaciones_silogtran_N.xlsx`: una hoja con las columnas del
informe más `cod_corte` y `fecha_corte` (sin `id` ni `fecha_extraccion`), encabezado con color, fila fija,
filtros, montos con separador de miles y códigos como texto (conservan ceros a la izquierda). Los datos
salen de Supabase con la función `exportar_corte`: con la clave pública sola no se puede leer la tabla,
y con la clave de exportación solo se obtiene un corte a la vez.
Si ya habías ejecutado `exportar_corte.sql`, vuelve a ejecutarlo (con tu clave) para actualizar la función. Nada pasa por GitHub (el repo es público).

El token y las claves se guardan solo en ese Chrome (no en el código; el repo es público). Si se pierde o filtra,
revócalo en GitHub y genera otro.

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

El workflow **"Sync reciente"** es el que mantiene los datos al día: en cada corrida vuelve a sincronizar
el **mes en curso + el mes anterior**. (El histórico casi no cambia; se recarga a mano con el backfill.)

### Disparo del sync: cron externo → GitHub

El disparo lo hace **exclusivamente** un servicio de cron externo (p. ej. **cron-job.org**, gratis) que
llama a la API de GitHub y ejecuta el workflow (`workflow_dispatch`). No se usa el `schedule` nativo de
GitHub porque es impreciso (se retrasa o se salta corridas).

1. **Token:** GitHub → Settings → Developer settings → **Fine-grained tokens** → New token. Acceso solo
   al repo `api-liquidacion`, permiso **Actions: Read and write**. Copia el token.
2. **cron-job.org:** crea una cuenta y un *cronjob* con:
   - **URL:** `https://api.github.com/repos/CALR0/api-liquidacion/actions/workflows/sync-reciente.yml/dispatches`
   - **Método:** `POST`
   - **Headers:**
     - `Authorization: Bearer <TU_TOKEN>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `User-Agent: cron-job`
   - **Body:** `{"ref":"main"}`
   - **Horario:** 6:00 a.m., 2:00 p.m. y 6:00 p.m. — crontab `0 6,14,18 * * *` con timezone
     **America/Bogota** (o `0 11,19,23 * * *` si el job está en UTC).
   - Respuesta esperada de GitHub: **204** (sin cuerpo) = disparo aceptado.
3. En la pestaña **Actions** verás la corrida casi de inmediato cada vez que cron-job.org dispare.

Nota: el token es secreto; úsalo solo en cron-job.org. Si se filtra, revócalo y genera otro (al ser
fine-grained y solo de Actions, el alcance es mínimo).

También puedes dispararlo a mano con **Run workflow** en la pestaña Actions.

---

## Estructura del repo

```
sync.py              Job de sincronización: rango por modo → Silogtran → Supabase (reemplaza cada mes)
api_liquidacion.py   Módulo reutilizado por el job: cliente de Silogtran (login+WAF+informe), esquema,
                     normalización. También puede correr como API REST local (modo anterior, opcional).
schema.sql           DDL de Supabase (liquidaciones + sync_estado)
migracion_cortes.sql Agrega cod_corte/fecha_corte a una base que ya existía
exportar_corte.sql   Función exportar_corte (descarga de un corte desde la extensión) + RLS
extension-corte/     Extensión de Chrome con el botón "Cerrar corte"
esquema / normalizar Dentro de api_liquidacion.py: columnas, tipos y limpieza del CSV
requirements.txt     requests, playwright, psycopg2-binary
.env.example         Variables de entorno (Silogtran, Supabase, WAF, modo sync)
CONEXION_QLIKSENSE.md Ficha de conexión para el equipo de QlikSense
.github/workflows/
  sync-reciente.yml  solo workflow_dispatch (lo dispara el cron externo 3 veces/día)
  sync-backfill.yml  manual, por rango de fechas (histórico)
  corte.yml          lo dispara el botón "Cerrar corte" (asigna cod_corte a las liquidaciones nuevas)
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
