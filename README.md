# API de Liquidación de Manifiestos — v1

API REST de **solo lectura** que expone el *Informe General de Liquidación de Manifiesto* de
Silogtran (Despacho → Liquidación Manifiesto → Informe General).

La construimos para que los equipos que necesitan esta información (tableros en Qlik Sense,
bodegas de datos, conciliaciones, otros sistemas) la consuman de forma automática, sin entrar a
Silogtran ni descargar archivos a mano. La API entrega exactamente lo que trae el informe,
una fila por manifiesto, con un esquema y tipos estables. Cómo agrupar, filtrar o almacenar
los datos lo decide cada consumidor.

> **Estado:** pendiente de despliegue. Las URL de este documento usan `<URL_BASE>` como
> marcador; cuando la API quede publicada se reemplaza por la dirección definitiva.

---

## Contenido
1. [Resumen rápido](#1-resumen-rápido)
2. [Autenticación](#2-autenticación)
3. [Endpoints](#3-endpoints)
4. [Consultar liquidaciones](#4-consultar-liquidaciones)
5. [Columnas](#5-columnas)
6. [Reglas de los datos](#6-reglas-de-los-datos)
7. [Validaciones y errores](#7-validaciones-y-errores)
8. [Frescura de los datos y caché](#8-frescura-de-los-datos-y-caché)
9. [Ejemplos de consumo](#9-ejemplos-de-consumo)
10. [Recomendaciones para almacenar](#10-recomendaciones-para-almacenar)
11. [Operación y configuración](#11-operación-y-configuración)
12. [Seguridad](#12-seguridad)
13. [Verificación contra Silogtran](#13-verificación-contra-silogtran)

---

## 1. Resumen rápido

| | |
|---|---|
| Tipo | REST, JSON, solo lectura (`GET`) |
| Autenticación | `Authorization: Bearer <token>` |
| Filtro | Rango de fechas de creación de la liquidación |
| Granularidad | Una fila por manifiesto liquidado |
| Llave única | `id` = `liqman_codigo-manifiesto_codigo` |
| Paginación | `offset` / `limit` + enlace `siguiente` |
| Compresión | gzip (si el cliente envía `Accept-Encoding: gzip`) |
| Rango máximo por consulta | 366 días |

```
GET <URL_BASE>/v1/liquidaciones?fechaInicial=2026-10-01&fechaFinal=2026-10-14
Authorization: Bearer <token>
```

---

## 2. Autenticación

Todas las rutas, excepto `/health`, exigen un token en el header:

```
Authorization: Bearer <token>
```

- El token es fijo y lo entrega el administrador de la API por un canal privado.
- Sin token, o con un token incorrecto, la respuesta es `401`.
- El token no va en la URL ni en parámetros: solo en el header.
- En Postman: pestaña **Authorization** → tipo **Bearer Token** → pegar el token.

---

## 3. Endpoints

| Método | Ruta | Token | Descripción |
|---|---|---|---|
| `GET` | `/v1/liquidaciones` | Sí | Datos del informe para un rango de fechas (paginado) |
| `GET` | `/v1/esquema` | Sí | Lista de columnas con su tipo y descripción |
| `GET` | `/health` | No | Estado del servicio, para monitoreo |

La versión va en la ruta (`/v1`). Si en el futuro cambia la estructura de la respuesta, se
publica como `/v2` y `/v1` sigue funcionando igual.

---

## 4. Consultar liquidaciones

### Parámetros

| Parámetro | Obligatorio | Formato | Descripción |
|---|---|---|---|
| `fechaInicial` | Sí | `yyyy-MM-dd` | Fecha de creación de la liquidación, desde (incluida) |
| `fechaFinal` | Sí | `yyyy-MM-dd` | Fecha de creación de la liquidación, hasta (incluida) |
| `offset` | No | entero ≥ 0 | Fila desde la que se devuelve. Por defecto `0` |
| `limit` | No | entero 1–10000 | Filas por página. Por defecto `1000` |

No hay más filtros a propósito: la API entrega el rango completo y el consumidor filtra en su
lado. Cualquier otro parámetro devuelve `400`.

### Respuesta

```json
{
  "meta": {
    "fechaInicial": "2026-10-02",
    "fechaFinal": "2026-10-02",
    "total": 254,
    "offset": 0,
    "limit": 100,
    "devueltos": 100,
    "siguiente": "/v1/liquidaciones?fechaInicial=2026-10-02&fechaFinal=2026-10-02&offset=100&limit=100",
    "fecha_extraccion": "2026-10-14T15:42:14-05:00",
    "desde_cache": false,
    "desactualizado": false
  },
  "datos": [
    {
      "id": "0101007855-0101221789",
      "liqman_codigo": "0101007855",
      "liqman_fechacreacion": "2026-10-02",
      "transferencia_codigo": null,
      "comegr_codigo": "0101182684",
      "banco_nombre": "BANCOLOMBIA TERCEROS",
      "vehiculo_placa": "SUK246",
      "manifiesto_codigo": "0101221789",
      "ruta": "BUENAVENTURA - COTA",
      "flete_real_despacho": 4500000,
      "manifiesto_valor_a_cancelar": 1269000,
      "liqman_valortotal": 1269000,
      "saldo_final": 1269000,
      "estado_liquidacion": "PENDIENTE",
      "...": "resto de columnas (ver sección 5)"
    }
  ]
}
```

| Campo de `meta` | Descripción |
|---|---|
| `total` | Filas totales del rango (todas las páginas) |
| `offset`, `limit`, `devueltos` | Posición y tamaño de la página actual |
| `siguiente` | Ruta de la página siguiente; `null` en la última |
| `fecha_extraccion` | Momento en que los datos se leyeron de Silogtran (hora Colombia) |
| `desde_cache` | `true` si toda la respuesta salió de la caché de la API |
| `desactualizado` | `true` si Silogtran no respondió y se entregaron los últimos datos guardados |

**Para traer todo el rango:** pedir la primera página y seguir `siguiente` hasta que sea `null`.

---

## 5. Columnas

`GET /v1/esquema` devuelve esta misma lista en JSON. Las columnas conservan los nombres del
informe de Silogtran y siempre salen en este orden.

**Tipos:** `texto` (string o `null`), `entero` (número, nunca `null`), `fecha` (`yyyy-MM-dd`),
`fecha_hora` (`yyyy-MM-dd HH:mm:ss`).

### Identificación

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | texto | Llave única de la fila: `liqman_codigo-manifiesto_codigo`. La agrega la API |
| `liqman_codigo` | texto | Código de la liquidación |
| `liqman_fechacreacion` | fecha | Fecha de creación de la liquidación. **Es la fecha que filtra el rango** |
| `manifiesto_codigo` | texto | Código del manifiesto liquidado |

### Pago

| Columna | Tipo | Descripción |
|---|---|---|
| `transferencia_codigo` | texto | Código de la transferencia, si el pago se hizo por transferencia |
| `comegr_codigo` | texto | Comprobante de egreso de la liquidación |
| `vale_codigo` | texto | Código del vale, si aplica |
| `banco_nombre` | texto | Banco / cuenta de pago |
| `beneficiario` | texto | Nombre del beneficiario del pago |
| `beneficiario_documento` | texto | Documento (cédula/NIT) del beneficiario |

### Vehículo, manifiesto y remesas

| Columna | Tipo | Descripción |
|---|---|---|
| `poseedor` | texto | Nombre del poseedor del vehículo |
| `poseedor_documento` | texto | Documento del poseedor |
| `vehiculo_placa` | texto | Placa del vehículo |
| `ruta` | texto | `ORIGEN - DESTINO` |
| `cliente_remesa_codigo` | texto | `CLIENTE - REMESA`. Si el manifiesto tiene varias remesas vienen separadas por coma |
| `manifiesto_fecha_creacion` | fecha | Fecha de creación del manifiesto |
| `manifiesto_fecha_cumplido` | fecha | Fecha de cumplido del manifiesto |

### Valores del manifiesto

| Columna | Tipo | Descripción |
|---|---|---|
| `flete_real_despacho` | entero | Flete del despacho |
| `descuento_cumplido_manifiesto` | entero | Descuentos aplicados en el cumplido |
| `valores_adicionales_cumplido_manifiesto` | entero | Valores adicionales reconocidos en el cumplido |
| `impuesto_manifiesto_retefuente` | entero | Retención en la fuente |
| `impuesto_manifiesto_reteica` | entero | ReteICA |
| `descuento_fopat` | entero | Descuento FOPAT |
| `valor_total_anticipos` | entero | Suma de los anticipos confirmados |
| `manifiesto_valor_a_cancelar` | entero | Valor pendiente por pagar del manifiesto |
| `descuento_liquidacion_manifiesto` | entero | Descuentos aplicados en la liquidación |
| `valores_adicionales_liquidacion_cumplido_manifiesto` | entero | Valores adicionales aplicados en la liquidación |

### Anticipos

El manifiesto puede tener hasta tres grupos de anticipo (`anticipo_`, `segundo_anticipo_`,
`tercer_anticipo_`), cada uno con las mismas cuatro columnas:

| Columna | Tipo | Descripción |
|---|---|---|
| `*_codigo` | texto | Código(s) del anticipo. Puede traer varios separados por coma |
| `*_fecha_creacion` | texto | Fecha(s) `yyyy-MM-dd`. Puede traer varias separadas por coma |
| `*_tipo_pago` | texto | Forma de pago (ej. `TRANSFERENCIA POR ARCHIVO`) |
| `*_valor_confirmado` | entero | Valor confirmado del anticipo |

### Valores de la liquidación y cartera

| Columna | Tipo | Descripción |
|---|---|---|
| `liqman_valortotal` | entero | Valor total de la liquidación. **Ver regla 6.2** |
| `valor_cartera_trasportador_manifiesto_anulado` | entero | Cartera del transportador por manifiesto anulado |
| `codigo_manifiesto_cartera_trasportador_manifiesto_anulado` | texto | Manifiesto anulado que origina esa cartera |
| `valor_cartera_trasportador_descuento_cumplido` | entero | Cartera del transportador por descuento de cumplido |
| `codigo_manifiesto_cartera_trasportador_descuento_cumplido` | texto | Manifiesto que origina esa cartera |
| `valor_cartera_transportador_contabilidad_sap` | entero | Cartera del transportador registrada en SAP |
| `saldo_final` | entero | Saldo final a pagar de la liquidación (valor total menos cartera). **Ver regla 6.2** |

### Control

| Columna | Tipo | Descripción |
|---|---|---|
| `liqman_observacion` | texto | Observación de la liquidación |
| `liquidacion_centro_costo` | texto | Centro de costo |
| `usuario_creacion` | texto | Usuario de Silogtran que creó la liquidación |
| `estado_liquidacion` | texto | Estado (ej. `PENDIENTE`) |
| `estatus_sap` | texto | Estatus de integración con SAP |
| `envio_correo` | texto | `SI` / `NO`: si se envió la liquidación por correo |
| `fecha_envio_correo` | fecha_hora | Fecha y hora del envío del correo |

---

## 6. Reglas de los datos

### 6.1 Tipos y vacíos
- **Montos:** siempre enteros. Cuando Silogtran los trae vacíos, la API devuelve `0`.
- **Códigos y documentos:** siempre texto, para conservar los ceros a la izquierda
  (`0101007855` ≠ `101007855`). Al cargarlos en otra herramienta, mantenerlos como texto.
- **Textos vacíos:** `null`.
- **Fechas:** texto ISO `yyyy-MM-dd`; `fecha_envio_correo` incluye hora.

### 6.2 Valores de la liquidación en una sola fila
Una liquidación agrupa varios manifiestos, así que ocupa varias filas. Silogtran reporta
`liqman_valortotal` y `saldo_final` **una sola vez por liquidación**, en una de sus filas; en las
demás filas de la misma liquidación esos campos vienen en `0`. Por eso:
- Para el total de liquidaciones, se suma la columna tal cual: no se duplica.
- Para el valor de una liquidación, se toma el máximo (o la suma) de sus filas, no el de una fila cualquiera.
- `sum(liqman_valortotal)` = `sum(manifiesto_valor_a_cancelar)` en cualquier rango.

### 6.3 Orden
Las filas salen en el mismo orden del informe de Silogtran, mes por mes dentro del rango.

---

## 7. Validaciones y errores

Todos los errores tienen la misma forma:

```json
{ "error": { "codigo": "rango_invalido", "mensaje": "El rango máximo es de 366 días" } }
```

| HTTP | `codigo` | Cuándo ocurre | Qué hacer |
|---|---|---|---|
| 400 | `fecha_invalida` | Falta una fecha o no es `yyyy-MM-dd` válida | Corregir el parámetro |
| 400 | `rango_invalido` | `fechaFinal` < `fechaInicial`, o el rango supera 366 días | Dividir el rango |
| 400 | `paginacion_invalida` | `offset` negativo o `limit` fuera de 1–10000 | Corregir el parámetro |
| 400 | `parametro_invalido` | Se envió un parámetro no soportado | Usar solo los parámetros de la sección 4 |
| 401 | `no_autorizado` | Token ausente o incorrecto | Revisar el header `Authorization` |
| 404 | `no_encontrado` | Ruta inexistente | Revisar la URL |
| 429 | `demasiadas_peticiones` | Más de 20 consultas por minuto desde la misma IP | Esperar un minuto |
| 502 | `silogtran_sesion` | La API no pudo iniciar sesión en Silogtran | Avisar al administrador de la API |
| 502 | `silogtran_estructura` | Silogtran cambió las columnas del informe | Avisar al administrador de la API |
| 503 | `silogtran_no_disponible` | Silogtran no respondió tras los reintentos | Reintentar después del tiempo indicado en `Retry-After` |

La API además valida la respuesta de Silogtran: si el informe deja de traer alguna de las
columnas esperadas, responde `502 silogtran_estructura` en lugar de entregar datos incompletos.

---

## 8. Frescura de los datos y caché

Cada consulta a Silogtran genera el informe en ese momento (unos 4–5 segundos por mes). Para
no cargar Silogtran y responder rápido, la API consulta el rango **mes por mes** y guarda cada
mes en caché:

| Datos del mes | Tiempo en caché |
|---|---|
| Incluye alguno de los últimos 7 días | 15 minutos |
| Más antiguos | 6 horas |

- Rangos que se solapan reutilizan los meses ya consultados.
- Si llegan dos consultas iguales al mismo tiempo, Silogtran se consulta una sola vez.
- `meta.fecha_extraccion` indica de cuándo es el dato.
- Si Silogtran falla, la API reintenta 3 veces. Si sigue fallando y tiene datos guardados del
  mismo mes, los entrega con `meta.desactualizado = true`.

Tiempos de referencia: un mes ≈ 4–5 s; dos meses y medio ≈ 12 s; desde caché < 0,1 s.
Recomendamos configurar en el cliente un timeout de al menos 2 minutos.

---

## 9. Ejemplos de consumo

### curl
```bash
curl -H "Authorization: Bearer <token>" --compressed "<URL_BASE>/v1/liquidaciones?fechaInicial=2026-10-01&fechaFinal=2026-10-14"
```

### Python (todas las páginas)
```python
import requests

BASE = "<URL_BASE>"
HEADERS = {"Authorization": "Bearer <token>"}

def liquidaciones(fecha_inicial, fecha_final):
    url = f"{BASE}/v1/liquidaciones?fechaInicial={fecha_inicial}&fechaFinal={fecha_final}&limit=5000"
    filas = []
    while url:
        r = requests.get(url, headers=HEADERS, timeout=180)
        r.raise_for_status()
        cuerpo = r.json()
        filas.extend(cuerpo["datos"])
        url = BASE + cuerpo["meta"]["siguiente"] if cuerpo["meta"]["siguiente"] else None
    return filas
```

### Qlik Sense (conector REST)
- **URL:** `<URL_BASE>/v1/liquidaciones?fechaInicial=...&fechaFinal=...`
- **Método:** GET.
- **Query headers:** `Authorization` = `Bearer <token>`.
- **Paginación:** tipo *Next URL*, ruta `meta/siguiente`. Si el conector exige URL absoluta, usar `limit=10000` en una sola página.
- **Tabla:** seleccionar `datos`.
- **Al cargar:** leer los códigos con `Text()` para no perder ceros a la izquierda.

---

## 10. Recomendaciones para almacenar

- **Llave:** usar `id` para insertar o actualizar (*upsert*). Consultar dos veces el mismo rango no duplica filas.
- **Las liquidaciones cambian después de creadas:** estado, estatus SAP, correo, cartera. Una
  estrategia simple es recargar en cada ejecución los últimos 30–60 días y reemplazar esos
  registros por `id`, dejando el histórico anterior intacto.
- **Carga histórica inicial:** el rango máximo es de 366 días; para periodos mayores, consultar año por año.
- **Trazabilidad:** guardar `meta.fecha_extraccion` junto con los datos.

---

## 11. Operación y configuración

### Cómo funciona por dentro
1. **Sesión:** la API inicia sesión en Silogtran con un usuario de servicio (usuario, clave y
   centro de costo), mantiene la sesión activa y la renueva sola si vence. La cookie vive solo
   en memoria.
2. **Consulta:** genera el Informe General en formato CSV para cada mes del rango (el mismo
   proceso que hace un usuario desde la pantalla), lo lee y lo normaliza al esquema de la
   sección 5.
3. **Caché, reintentos y compresión:** como se describe en la sección 8.
4. **Disponibilidad:** en hostings gratuitos que suspenden el servicio por inactividad, la API se
   llama a sí misma (`/health`) cada 10 minutos para mantenerse activa.

### Variables de entorno
Se configuran en un archivo `.env` (local) o en las variables del hosting.
Plantilla: [.env.example](.env.example).

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `SILOGTRAN_USUARIO` | Sí | | Usuario de servicio de Silogtran |
| `SILOGTRAN_CLAVE` | Sí | | Clave de ese usuario |
| `API_KEY` | Sí | | Token Bearer de la API (mínimo 24 caracteres) |
| `SILOGTRAN_CENTROCOSTO` | No | el único disponible | Centro de costo para el login (ej. `1-1`) |
| `SILOGTRAN_URL` | No | `https://construproyec.colombiasoftware.net` | URL de Silogtran |
| `HOST` / `PORT` | No | `0.0.0.0` / `8000` | Dirección y puerto |
| `MAX_DIAS_RANGO` | No | `366` | Rango máximo por consulta |
| `DIAS_RECIENTES` | No | `7` | Días considerados "recientes" para la caché |
| `CACHE_MINUTOS_RECIENTE` | No | `15` | Caché de meses recientes |
| `CACHE_MINUTOS_HISTORICO` | No | `360` | Caché de meses anteriores |
| `CACHE_MAX_BLOQUES` | No | `100` | Meses guardados en memoria |
| `LIMITE_DEFECTO` / `LIMITE_MAXIMO` | No | `1000` / `10000` | Tamaño de página |
| `REINTENTOS` | No | `3` | Reintentos ante fallas de Silogtran |
| `TIMEOUT_SILOGTRAN_SEG` | No | `300` | Timeout por petición a Silogtran |
| `KEEPALIVE_MINUTOS` | No | `10` | Frecuencia para mantener viva la sesión (0 = apagado) |
| `AUTOPING_URL` | No | `RENDER_EXTERNAL_URL` | URL pública para el autoping |
| `AUTOPING_MINUTOS` | No | `10` | Frecuencia del autoping (0 = apagado) |
| `MAX_PETICIONES_MINUTO` | No | `20` | Límite de consultas por minuto por IP |

### Ejecutar en local
```bash
pip install -r requirements.txt
python api_liquidacion.py
```
Queda disponible en `http://localhost:8000`.

### Monitoreo
`GET /health` (sin token):
```json
{ "ok": true, "ultima_consulta_silogtran_ok": "2026-10-14T15:42:14-05:00", "bloques_en_cache": 2 }
```

### Despliegue
Se despliega con el `Dockerfile` incluido. La guía del hosting definitivo se documentará
cuando la API quede publicada.

### Archivos del proyecto
| Archivo | |
|---|---|
| `api_liquidacion.py` | Código de la API |
| `requirements.txt` | Dependencias (`requests`) |
| `Dockerfile` | Imagen para despliegue (usuario sin privilegios) |
| `.env.example` | Plantilla de configuración |

---

## 12. Seguridad

- **Solo lectura:** la API únicamente inicia sesión y genera el informe; no crea, modifica ni borra nada en Silogtran.
- **Token Bearer** obligatorio en todas las rutas de datos, comparado en tiempo constante.
- **Credenciales** solo en variables de entorno; `.env` está excluido de git y de la imagen Docker.
- **Límites:** 20 consultas por minuto por IP y 366 días por consulta.
- **Logs** sin parámetros, tokens, cookies ni credenciales.
- **HTTPS** obligatorio una vez publicada.
- Se recomienda un **usuario de servicio** en Silogtran, con acceso solo a este informe, distinto de los usuarios personales.

---

## 13. Verificación contra Silogtran

Validamos la API comparándola con el Informe General descargado directamente en Silogtran
para el mismo rango (2026-10-02):

| Verificación | Resultado |
|---|---|
| Filas (254) y liquidaciones (112) | Iguales |
| 52 columnas, valor por valor en las 254 filas (huella SHA-256) | Idénticas |
| Orden de las filas | Igual |
| Totales de las 18 columnas de montos | Iguales |
| `id` único por fila | Sí |
