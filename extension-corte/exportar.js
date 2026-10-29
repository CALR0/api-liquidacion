// Descarga las liquidaciones de un corte desde Supabase (función exportar_corte) como Excel.
const OMITIR = new Set(["id", "fecha_extraccion"]);   // columnas técnicas que no van en el archivo

function fechaColombia(iso) {
  const d = new Date(new Date(iso).getTime() - 5 * 3600 * 1000);   // UTC-5
  return d.toISOString().slice(0, 16).replace("T", " ");
}

async function traerCorte(config, codCorte) {
  if (!config.supabaseUrl || !config.supabaseKey || !config.claveExport) {
    throw new Error("Falta configurar Supabase y la clave de exportación en Opciones.");
  }
  const url = `${config.supabaseUrl.replace(/\/+$/, "")}/rest/v1/rpc/exportar_corte`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { apikey: config.supabaseKey, "Content-Type": "application/json" },
    body: JSON.stringify({ p_cod_corte: Number(codCorte), p_clave: config.claveExport }),
  });
  if (!resp.ok) {
    const texto = await resp.text();
    if (texto.includes("Clave de exportación inválida")) throw new Error("La clave de exportación no es correcta.");
    if (resp.status === 401 || resp.status === 403) throw new Error("La clave pública de Supabase no es válida.");
    throw new Error(`Supabase respondió ${resp.status}`);
  }
  return resp.json();
}

async function descargarCorte(config, codCorte) {
  const filas = await traerCorte(config, codCorte);
  if (!filas.length) throw new Error(`El corte ${codCorte} no tiene liquidaciones.`);
  const columnas = Object.keys(filas[0]).filter((c) => !OMITIR.has(c));
  // Montos con separador de miles; cod_corte es un código, va como texto
  const numericas = new Set(columnas.filter((c) => c !== "cod_corte" && filas.some((f) => typeof f[c] === "number")));
  for (const f of filas) {
    if (f.fecha_corte) f.fecha_corte = fechaColombia(f.fecha_corte);
  }
  const blob = crearXlsx(`Corte ${codCorte}`, columnas, filas, numericas);
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(blob);
  enlace.download = `liquidaciones_silogtran_${codCorte}.xlsx`;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(enlace.href), 10000);
  return filas.length;
}
