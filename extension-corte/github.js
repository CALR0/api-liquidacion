// Acceso mínimo a la API de GitHub para disparar y seguir el workflow corte.yml.
const WORKFLOW = "corte.yml";
const DEFAULTS = { repo: "CALR0/api-liquidacion", token: "", supabaseUrl: "", supabaseKey: "", claveExport: "" };

async function leerConfig() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}

async function gh(config, ruta, opciones = {}) {
  const resp = await fetch(`https://api.github.com/repos/${config.repo}${ruta}`, {
    ...opciones,
    headers: {
      Authorization: `Bearer ${config.token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opciones.headers || {}),
    },
  });
  if (!resp.ok) {
    const mensajes = {
      401: "Token inválido o vencido. Revísalo en ⚙ Configuración.",
      403: "El token no tiene permiso Actions: Read and write sobre el repositorio.",
      404: "No se encontró el repositorio o el workflow corte.yml.",
    };
    throw new Error(mensajes[resp.status] || `GitHub respondió ${resp.status}`);
  }
  return resp.status === 204 ? null : resp.json();
}

async function dispararCorte(config) {
  await gh(config, `/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main" }),
  });
}

// GitHub no devuelve el id de la corrida al disparar: se busca la primera creada después del clic.
async function buscarCorrida(config, desde) {
  const datos = await gh(config, `/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=5`);
  return (datos.workflow_runs || []).find((r) => new Date(r.created_at) >= desde) || null;
}

async function leerCorrida(config, id) {
  return gh(config, `/actions/runs/${id}`);
}

// El job deja el resultado como anotación "Corte" (ej. "Corte 15: 12 liquidaciones (30 filas)").
async function leerResultado(config, runId) {
  try {
    const { jobs } = await gh(config, `/actions/runs/${runId}/jobs`);
    for (const job of jobs || []) {
      const notas = await gh(config, `/check-runs/${job.id}/annotations`);
      const nota = (notas || []).find((n) => n.title === "Corte");
      if (nota) return nota.message;
    }
  } catch (e) {
    // Si no se puede leer la anotación, la persona igual ve el estado y el enlace a la corrida
  }
  return null;
}
