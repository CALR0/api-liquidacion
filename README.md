# API de Liquidación de Manifiestos — v1

API REST de **solo lectura** que entrega el *Informe General de Liquidación de Manifiesto* de
Silogtran (Despacho → Liquidación Manifiesto → Informe General) en JSON. Está pensada para que
tableros (Qlik Sense), bodegas de datos y otros sistemas tomen la información sin entrar a Silogtran.

Entrega lo mismo que el informe: una fila por manifiesto, con todas sus columnas y tipos estables.
El consumidor decide cómo agrupar, filtrar o almacenar.

**URL base:** `https://liqmanifiesto-construproyec.onrender.com`

---

## 1. Autenticación

Todas las rutas, excepto `/health`, requieren el token en el header:

```
Authorization: Bearer <token>
```

El token es fijo y lo entrega el administrador de la API. Sin token, o con uno incorrecto, la
respuesta es `401`. En Postman se configura en **Authorization → Bearer Token**.

## 2. Endpoints

| Método | Ruta | Token | Descripción |
|---|---|---|---|
| GET | `/v1/liquidaciones` | Sí | Datos del informe por rango de fechas (paginado) |
| GET | `/v1/esquema` | Sí | Columnas con su tipo y descripción |
| GET | `/health` | No | Estado del servicio |

## 3. Consulta

```
GET https://liqmanifiesto-construproyec.onrender.com/v1/liquidaciones?fechaInicial=2026-10-01&fechaFinal=2026-10-14
Authorization: Bearer <token>
```

| Parámetro | Obligatorio | Formato | Descripción |
|---|---|---|---|
| `fechaInicial` | Sí | `yyyy-MM-dd` | Desde (incluida), por fecha de creación de la liquidación |
| `fechaFinal` | Sí | `yyyy-MM-dd` | Hasta (incluida) |
| `offset` | No | entero ≥ 0 | Fila inicial. Por defecto `0` |
| `limit` | No | 1–10000 | Filas por página. Por defecto `1000` |

El único filtro es el rango de fechas, de máximo 366 días.

### Respuesta

```json
{
  "meta": {
    "fechaInicial": "2026-10-02",
    "fechaFinal": "2026-10-02",
    "total": 254,
    "offset": 0,
    "limit": 1000,
    "devueltos": 254,
    "siguiente": null,
    "fecha_extraccion": "2026-10-14T15:42:14-05:00",
    "desde_cache": false,
    "desactualizado": false
  },
  "datos": [
    {
      "id": "0101007855-0101221789",
      "liqman_codigo": "0101007855",
      "liqman_fechacreacion": "2026-10-02",
      "manifiesto_codigo": "0101221789",
      "vehiculo_placa": "SUK246",
      "flete_real_despacho": 4500000,
      "...": "resto de columnas"
    }
  ]
}
```

| `meta` | Descripción |
|---|---|
| `total` | Filas del rango completo |
| `devueltos` | Filas de esta página |
| `siguiente` | Ruta de la página siguiente; `null` si es la última |
| `fecha_extraccion` | Momento en que se leyó Silogtran (hora Colombia) |
| `desde_cache` | `true` si salió de la caché de la API |
| `desactualizado` | `true` si Silogtran no respondió y se entregaron los últimos datos guardados |

Para traer todo el rango, se sigue `siguiente` hasta que sea `null`.

## 4. Columnas

El orden es fijo y los nombres son los mismos del informe. `/v1/esquema` devuelve esta lista en JSON.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | texto | Llave única: `liqman_codigo-manifiesto_codigo` |
| `liqman_codigo` | texto | Código de la liquidación |
| `liqman_fechacreacion` | fecha | Fecha de creación de la liquidación (la que filtra el rango) |
| `transferencia_codigo` | texto | Código de la transferencia |
| `comegr_codigo` | texto | Comprobante de egreso |
| `vale_codigo` | texto | Código del vale |
| `banco_nombre` | texto | Banco / cuenta de pago |
| `beneficiario` | texto | Beneficiario del pago |
| `beneficiario_documento` | texto | Documento del beneficiario |
| `poseedor` | texto | Poseedor del vehículo |
| `poseedor_documento` | texto | Documento del poseedor |
| `vehiculo_placa` | texto | Placa |
| `manifiesto_codigo` | texto | Código del manifiesto |
| `ruta` | texto | `ORIGEN - DESTINO` |
| `cliente_remesa_codigo` | texto | `CLIENTE - REMESA`, separados por coma si son varios |
| `manifiesto_fecha_creacion` | fecha | Creación del manifiesto |
| `manifiesto_fecha_cumplido` | fecha | Cumplido del manifiesto |
| `flete_real_despacho` | entero | Flete del despacho |
| `descuento_cumplido_manifiesto` | entero | Descuentos del cumplido |
| `valores_adicionales_cumplido_manifiesto` | entero | Adicionales del cumplido |
| `impuesto_manifiesto_retefuente` | entero | Retención en la fuente |
| `impuesto_manifiesto_reteica` | entero | ReteICA |
| `descuento_fopat` | entero | Descuento FOPAT |
| `anticipo_codigo` | texto | Código(s) del anticipo, separados por coma |
| `anticipo_fecha_creacion` | texto | Fecha(s) del anticipo, separadas por coma |
| `anticipo_tipo_pago` | texto | Forma de pago |
| `anticipo_valor_confirmado` | entero | Valor confirmado |
| `segundo_anticipo_*` / `tercer_anticipo_*` | — | Mismas cuatro columnas para el 2.º y 3.er anticipo |
| `valor_total_anticipos` | entero | Total de anticipos |
| `manifiesto_valor_a_cancelar` | entero | Valor por pagar del manifiesto |
| `descuento_liquidacion_manifiesto` | entero | Descuentos de la liquidación |
| `valores_adicionales_liquidacion_cumplido_manifiesto` | entero | Adicionales de la liquidación |
| `liqman_valortotal` | entero | Valor total de la liquidación (ver 5.2) |
| `valor_cartera_trasportador_manifiesto_anulado` | entero | Cartera por manifiesto anulado |
| `codigo_manifiesto_cartera_trasportador_manifiesto_anulado` | texto | Manifiesto que origina esa cartera |
| `valor_cartera_trasportador_descuento_cumplido` | entero | Cartera por descuento de cumplido |
| `codigo_manifiesto_cartera_trasportador_descuento_cumplido` | texto | Manifiesto que origina esa cartera |
| `valor_cartera_transportador_contabilidad_sap` | entero | Cartera registrada en SAP |
| `saldo_final` | entero | Saldo a pagar de la liquidación (ver 5.2) |
| `liqman_observacion` | texto | Observación |
| `liquidacion_centro_costo` | texto | Centro de costo |
| `usuario_creacion` | texto | Usuario que creó la liquidación |
| `estado_liquidacion` | texto | Estado (ej. `PENDIENTE`) |
| `estatus_sap` | texto | Estatus en SAP |
| `envio_correo` | texto | `SI` / `NO` |
| `fecha_envio_correo` | fecha_hora | `yyyy-MM-dd HH:mm:ss` |

## 5. Reglas de los datos

1. **Tipos:**
   - Montos: enteros; si vienen vacíos en Silogtran, la API devuelve `0`.
   - Códigos y documentos: texto, para conservar los ceros a la izquierda. Al cargarlos, mantenerlos como texto.
   - Textos vacíos: `null`.
   - Fechas: `yyyy-MM-dd`.
2. **`liqman_valortotal` y `saldo_final`** salen una sola vez por liquidación, en una de sus filas;
   en las demás filas de esa liquidación vienen en `0`. Sumar la columna tal cual da el total
   correcto sin duplicar.
3. **Orden:** el mismo del informe de Silogtran.

## 6. Errores

Todos tienen esta forma: `{ "error": { "codigo": "...", "mensaje": "..." } }`

| HTTP | `codigo` | Causa |
|---|---|---|
| 400 | `fecha_invalida` | Falta una fecha o no es `yyyy-MM-dd` |
| 400 | `rango_invalido` | `fechaFinal` menor que `fechaInicial`, o más de 366 días |
| 400 | `paginacion_invalida` | `offset` o `limit` fuera de rango |
| 400 | `parametro_invalido` | Parámetro no soportado |
| 401 | `no_autorizado` | Token ausente o incorrecto |
| 404 | `no_encontrado` | Ruta inexistente |
| 429 | `demasiadas_peticiones` | Más de 20 consultas por minuto por cliente, más de 40 por minuto en total, o más de 10 tokens inválidos por minuto |
| 502 | `silogtran_sesion` | No se pudo iniciar sesión en Silogtran |
| 503 | `silogtran_sesion_en_pausa` | El login a Silogtran está en pausa tras un fallo, para no bloquear el usuario; reintentar según `Retry-After` |
| 502 | `silogtran_estructura` | El informe de Silogtran cambió sus columnas |
| 503 | `silogtran_no_disponible` | Silogtran no respondió; reintentar según el header `Retry-After` |

## 7. Rendimiento y caché

- La API descarga de Silogtran **meses completos** y los guarda en caché. Cualquier día o rango
  dentro de un mes ya consultado se responde desde la caché, recortado al rango pedido.
- El **mes en curso se precarga** en segundo plano cada 10 minutos, así que siempre responde al instante.
- Cada mes vive **15 minutos** en caché. Así, cualquier cambio en Silogtran, aunque sea de un
  mes antiguo, se refleja en la API como máximo 15 minutos después.
- Tiempos medidos en Render:
  - Mes fuera de caché: 3–5 s.
  - Cualquier rango en caché: menos de 0,5 s.
- Recomendado: timeout del cliente de 2 minutos.
- Si Silogtran falla, la API reintenta 3 veces. Si sigue fallando y tiene datos previos guardados, los entrega con `desactualizado: true`.
- Responde comprimido en gzip cuando el cliente lo acepta.

## 8. Ejemplos

**curl**
```bash
curl --compressed -H "Authorization: Bearer <token>" "https://liqmanifiesto-construproyec.onrender.com/v1/liquidaciones?fechaInicial=2026-10-01&fechaFinal=2026-10-14"
```

**Python**
```python
import requests

BASE = "https://liqmanifiesto-construproyec.onrender.com"
HEADERS = {"Authorization": "Bearer <token>"}

def liquidaciones(desde, hasta):
    url, filas = f"{BASE}/v1/liquidaciones?fechaInicial={desde}&fechaFinal={hasta}&limit=10000", []
    while url:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        cuerpo = r.json()
        filas += cuerpo["datos"]
        url = BASE + cuerpo["meta"]["siguiente"] if cuerpo["meta"]["siguiente"] else None
    return filas
```

**Qlik Sense (conector REST)**
- **Método:** GET.
- **URL:** la de la consulta, con `limit=10000`.
- **Header:** `Authorization: Bearer <token>`.
- **Tabla a cargar:** `datos`.
- **Códigos:** leerlos con `Text()` para conservar los ceros a la izquierda.

**Para almacenar**
- Usar `id` como llave para insertar o actualizar.
- Las liquidaciones cambian después de creadas (estado, SAP, cartera), así que conviene recargar
  periódicamente los últimos 30–60 días.

---

## 9. Despliegue y configuración

La API está desplegada en **Render**:
- Servicio Docker en el plan Free, que lee el código del repositorio privado de GitHub `api-liquidacion` (rama `main`).
- Health check en `/health`.
- Cada cambio subido a `main` se redespliega solo. También se puede forzar con **Manual Deploy → Deploy latest commit**.

**Variables de entorno** (Render → *Environment → Environment Variables*):

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SILOGTRAN_USUARIO` | Sí | Usuario de servicio de Silogtran |
| `SILOGTRAN_CLAVE` | Sí | Clave de ese usuario |
| `API_KEY` | Sí | Token Bearer de la API (mínimo 24 caracteres) |
| `SILOGTRAN_CENTROCOSTO` | No | Centro de costo del login (ej. `1-1`) |

Los demás parámetros (caché, límites, reintentos, timeouts) tienen valores por defecto y están
documentados en [.env.example](.env.example). `PORT` la asigna Render.

**Funcionamiento interno:**
- **Un solo login:** la API inicia sesión una vez y reutiliza la sesión hasta que Silogtran la cierre.
  Las consultas, la precarga y el keepalive nunca abren sesiones nuevas mientras la actual siga activa.
- **Protección del usuario:** si un login falla, la API no vuelve a intentarlo hasta pasado un tiempo
  que crece con cada fallo seguido: 30 min, 2 h, 8 h y luego 24 h. Como máximo hace 4 intentos fallidos al día.
  Además, nunca hace más de **2 logins por hora ni 10 por día**. Mientras tanto responde
  `503 silogtran_sesion_en_pausa`, o datos en caché marcados `desactualizado`.
  `/health` muestra `login_en_pausa_hasta`, `logins_ultima_hora` y `logins_ultimas_24h`.
- **Límites de consultas:** 20 por minuto por cliente y 40 por minuto en total; el límite total no se
  puede eludir cambiando de IP. Además, se permiten como máximo 10 intentos con token inválido por minuto e IP.
- En el plan gratuito, Render apaga el servicio tras 15 minutos sin uso. Para evitarlo, la API se
  consulta a sí misma (`/health`) cada 10 minutos.

**Monitoreo:** `GET /health` (sin token) responde con `ok`, la última consulta exitosa a Silogtran y
los meses en caché.

**Ejecutar en local:** copiar `.env.example` como `.env`, completarlo y ejecutar:
```bash
python api_liquidacion.py
```
Queda en `http://localhost:8000`.

**Seguridad:**
- La API es de solo lectura sobre Silogtran.
- Funciona solo por HTTPS y con token Bearer obligatorio.

Todos los derechos reservados.
