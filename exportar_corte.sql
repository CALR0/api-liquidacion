-- Exportación de un corte para la extensión de Chrome (ejecutar una vez en Supabase → SQL Editor).
--
-- La extensión llama a la función exportar_corte(cod_corte, clave) con la clave pública del proyecto.
-- La función solo devuelve las filas de UN corte (el indicado o, si no se indica, el último) y solo si
-- la clave de exportación es correcta: con la clave pública sola no se puede leer la tabla liquidaciones.

-- 0) Con la clave pública nadie debe leer la tabla directo: RLS activo en liquidaciones.
--    (El job escribe como dueño de la tabla y no se ve afectado; a QlikSense se le garantiza su política.)
alter table public.liquidaciones enable row level security;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'qlik_ro')
     and not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'liquidaciones'
                     and policyname = 'qlik_lectura') then
    create policy qlik_lectura on public.liquidaciones for select to qlik_ro using (true);
  end if;
end $$;

-- 1) Configuración privada (sin políticas RLS: nadie la puede leer desde fuera)
create table if not exists public.config_privada (
  clave  text primary key,
  valor  text not null
);
alter table public.config_privada enable row level security;

-- 2) Clave de exportación: reemplace el texto por una clave larga y aleatoria
--    (ej. la que genera: python -c "import secrets; print(secrets.token_urlsafe(32))").
--    Para cambiarla después, vuelva a ejecutar solo esta sentencia con la clave nueva.
insert into public.config_privada (clave, valor)
values ('clave_exportacion', 'REEMPLACE_POR_UNA_CLAVE_LARGA')
on conflict (clave) do update set valor = excluded.valor;

-- 3) Función de exportación
drop function if exists public.exportar_corte(int, text);
create function public.exportar_corte(p_cod_corte int, p_clave text)
returns setof public.liquidaciones
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_clave is null or length(p_clave) < 24 or not exists (
       select 1 from config_privada where clave = 'clave_exportacion' and valor = p_clave) then
    raise exception 'Clave de exportación inválida' using errcode = '28000';
  end if;
  return query
    select * from liquidaciones
    where cod_corte = coalesce(p_cod_corte, (select max(cod_corte) from liquidaciones))
    order by liqman_codigo, manifiesto_codigo;
end;
$$;

revoke all on function public.exportar_corte(int, text) from public;
grant execute on function public.exportar_corte(int, text) to anon, authenticated;
