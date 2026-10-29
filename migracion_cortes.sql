-- Migración para una base que YA existe (ejecutar una vez en Supabase → SQL Editor).
-- Agrega el corte de liquidación sin tocar los datos actuales: las filas existentes quedan sin corte.

alter table public.liquidaciones add column if not exists cod_corte   int;
alter table public.liquidaciones add column if not exists fecha_corte timestamptz;
create index if not exists idx_liq_cod_corte on public.liquidaciones (cod_corte);
