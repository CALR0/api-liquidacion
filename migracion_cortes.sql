-- Migración para una base que YA existe (ejecutar una vez en Supabase → SQL Editor).
-- Agrega el corte de liquidación sin tocar los datos actuales: las filas existentes quedan sin corte.

alter table public.liquidaciones add column if not exists cod_corte   int;
alter table public.liquidaciones add column if not exists fecha_corte timestamptz;
create index if not exists idx_liq_cod_corte on public.liquidaciones (cod_corte);

create table if not exists public.cortes (
  cod_corte          int primary key,
  fecha_corte        timestamptz not null default now(),
  liquidaciones      int not null,
  filas              int not null,
  origen             text
);
alter table public.cortes enable row level security;   -- el job escribe como admin; nadie más

-- Si QlikSense también debe ver el registro de cortes (opcional):
-- grant select on public.cortes to qlik_ro;
-- create policy qlik_lectura_cortes on public.cortes for select to qlik_ro using (true);
