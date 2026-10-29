# Conexión a la base de Liquidaciones — guía para QlikSense

Documento para el equipo que integra en QlikSense. Es **solo lectura**: no se puede modificar nada.

## ¿Qué es?

Una base de datos **PostgreSQL** (alojada en Supabase) con la tabla **`liquidaciones`**, que contiene el
*Informe General de Liquidación de Manifiesto* de Silogtran. **Una fila por manifiesto.** Los datos se
**actualizan solos 3 veces al día: 6:00 a.m., 2:00 p.m. y 6:00 p.m.** (hora Colombia). Un proceso los
sincroniza desde Silogtran y tarda unos minutos en terminar.

No hay API que llamar: se consulta **directo** con el conector de PostgreSQL de QlikSense.

## Datos de conexión

| Campo | Valor |
|---|---|
| Tipo | PostgreSQL |
| Host | `aws-0-us-east-1.pooler.supabase.com` |
| Puerto | `5432` |
| Base de datos | `postgres` |
| Usuario | `qlik_ro.lnjyjftljnzedvgcewaw` |
| Contraseña | *(se entrega por separado, por canal seguro)* |
| SSL | **Obligatorio** (`require`) |
| Esquema / tabla | `public.liquidaciones` |

Cadena de conexión equivalente (reemplazar la clave):

```
postgresql://qlik_ro.lnjyjftljnzedvgcewaw:[CLAVE]@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require
```

## Cómo conectar en QlikSense

1. Crear una conexión de datos con el **conector PostgreSQL** (nativo de Qlik; si usan ODBC/JDBC,
   los mismos datos de arriba).
2. Llenar host, puerto, base, usuario y contraseña; **activar SSL**.
3. Probar la conexión y seleccionar la tabla `public.liquidaciones`.

En el **editor de carga de datos**, un ejemplo mínimo:

```sql
LIB CONNECT TO 'Liquidaciones_Supabase';

Liquidaciones:
LOAD *;
SELECT * FROM public.liquidaciones;
```

## Cómo consultar

- Tabla: **`public.liquidaciones`**. Llave única por fila: **`id`** = `liqman_codigo-manifiesto_codigo`.
- Las columnas son **las mismas del informe de Silogtran**. Notas de tipos:
  - **Códigos y documentos: léanlos como texto** (conservan los ceros a la izquierda).
  - **Montos: enteros**; si vienen vacíos en Silogtran, aquí son `0`.
  - **`liqman_valortotal`** y **`saldo_final`** traen el valor en **una sola fila** por liquidación (en las
    demás filas de esa liquidación van en `0`): sumar la columna da el total **sin duplicar**.
  - `envio_correo` / `fecha_envio_correo` están **vacíos cuando la liquidación aún no se ha enviado**
    (es lo mismo que muestra Silogtran, no es un dato faltante).
- Filtrar por fecha con **`liqman_fechacreacion`** (`yyyy-MM-dd`).
- Para **cargas incrementales**: usar `fecha_extraccion` (cuándo se actualizó cada fila) o
  `liqman_fechacreacion`.

Ejemplos:

```sql
-- Todo
SELECT * FROM public.liquidaciones;

-- Un rango de fechas
SELECT * FROM public.liquidaciones
WHERE liqman_fechacreacion BETWEEN '2026-01-01' AND '2026-01-31';
```

## Actualización y uso razonable (límites)

- Los datos se **refrescan solos a las 6 a.m., 2 p.m. y 6 p.m.**; programen la recarga de QlikSense unos
  minutos después de esas horas (por ejemplo, 6:30 a.m., 2:30 p.m. y 6:30 p.m.). Recargar más seguido no trae nada
  nuevo.
- Conexión de **solo lectura**: no se puede escribir ni borrar.
- Evitar *full reloads* muy frecuentes (varias veces por minuto). Lo ideal: unas pocas recargas al día,
  o **carga incremental**. (La base es pequeña, pero así se cuida el consumo de datos del plan.)

## Soporte

La base y el proceso de sincronización los administra el área de TI/operaciones de ELOGIA. Ante dudas o
si la conexión falla, contactar al administrador.
