-- Esquema para Supabase (Postgres). Ejecútalo en Supabase → SQL Editor.
-- Tabla de liquidaciones (una fila por manifiesto, llave id = liqman_codigo-manifiesto_codigo)
-- + tabla de estado del sync (freno anti-bloqueo del usuario de Silogtran).

create table if not exists public.liquidaciones (
  id                                                      text primary key,
  liqman_codigo                                           text,
  liqman_fechacreacion                                    date,
  transferencia_codigo                                    text,
  comegr_codigo                                           text,
  vale_codigo                                             text,
  banco_nombre                                            text,
  beneficiario                                            text,
  beneficiario_documento                                  text,
  poseedor                                                text,
  poseedor_documento                                      text,
  vehiculo_placa                                          text,
  manifiesto_codigo                                       text,
  ruta                                                    text,
  cliente_remesa_codigo                                   text,
  manifiesto_fecha_creacion                               text,
  manifiesto_fecha_cumplido                               text,
  flete_real_despacho                                     bigint not null default 0,
  descuento_cumplido_manifiesto                           bigint not null default 0,
  valores_adicionales_cumplido_manifiesto                 bigint not null default 0,
  impuesto_manifiesto_retefuente                          bigint not null default 0,
  impuesto_manifiesto_reteica                             bigint not null default 0,
  descuento_fopat                                         bigint not null default 0,
  anticipo_codigo                                         text,
  anticipo_fecha_creacion                                 text,
  anticipo_tipo_pago                                      text,
  anticipo_valor_confirmado                               bigint not null default 0,
  segundo_anticipo_codigo                                 text,
  segundo_anticipo_fecha_creacion                         text,
  segundo_anticipo_tipo_pago                              text,
  segundo_anticipo_valor_confirmado                       bigint not null default 0,
  tercer_anticipo_codigo                                  text,
  tercer_anticipo_fecha_creacion                          text,
  tercer_anticipo_tipo_pago                               text,
  tercer_anticipo_valor_confirmado                        bigint not null default 0,
  valor_total_anticipos                                   bigint not null default 0,
  manifiesto_valor_a_cancelar                             bigint not null default 0,
  descuento_liquidacion_manifiesto                        bigint not null default 0,
  valores_adicionales_liquidacion_cumplido_manifiesto     bigint not null default 0,
  liqman_valortotal                                       bigint not null default 0,
  valor_cartera_trasportador_manifiesto_anulado           bigint not null default 0,
  codigo_manifiesto_cartera_trasportador_manifiesto_anulado text,
  valor_cartera_trasportador_descuento_cumplido           bigint not null default 0,
  codigo_manifiesto_cartera_trasportador_descuento_cumplido text,
  valor_cartera_transportador_contabilidad_sap            bigint not null default 0,
  saldo_final                                             bigint not null default 0,
  liqman_observacion                                      text,
  liquidacion_centro_costo                                text,
  usuario_creacion                                        text,
  estado_liquidacion                                      text,
  estatus_sap                                             text,
  envio_correo                                            text,
  fecha_envio_correo                                      text,
  fecha_extraccion                                        timestamptz not null default now()
);

create index if not exists idx_liq_fechacreacion on public.liquidaciones (liqman_fechacreacion);
create index if not exists idx_liq_manifiesto     on public.liquidaciones (manifiesto_codigo);
create index if not exists idx_liq_estado_sap     on public.liquidaciones (estatus_sap);

-- Estado del sync: freno de login para no bloquear el usuario de Silogtran.
create table if not exists public.sync_estado (
  clave           text primary key,
  fallos          int not null default 0,
  bloqueado_hasta timestamptz,
  actualizado     timestamptz not null default now()
);
