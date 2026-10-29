const $ = (id) => document.getElementById(id);
const boton = $("cerrar");
const botonDescargar = $("descargar");
const CAMPOS = ["token", "supabaseUrl", "supabaseKey", "claveExport", "repo"];
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function mostrar(el, texto, clase = "") {
  el.className = `estado ${clase}`;
  el.textContent = texto;
}

// --- Configuración (⚙): se muestra en la misma ventanita ---------------------
async function verConfig(abrir) {
  $("vistaConfig").hidden = !abrir;
  $("vistaPrincipal").hidden = abrir;
  $("engranaje").classList.toggle("activo", abrir);
  if (abrir) {
    const config = await leerConfig();
    for (const c of CAMPOS) $(c).value = config[c];
    mostrar($("estadoConfig"), "");
  }
}

$("engranaje").addEventListener("click", () => verConfig($("vistaConfig").hidden));

$("guardar").addEventListener("click", async () => {
  const valores = Object.fromEntries(CAMPOS.map((c) => [c, $(c).value.trim().replace(/^Bearer\s+/i, "")]));
  await chrome.storage.local.set(valores);
  mostrar($("estadoConfig"), "Guardado ✓", "ok");
  setTimeout(() => verConfig(false), 700);
});

// Al abrir siempre se muestra el corte; si falta configurar, se avisa (la ⚙ está arriba)
leerConfig().then((config) => {
  if (!config.token || !config.supabaseUrl || !config.supabaseKey || !config.claveExport) {
    mostrar($("estado"), "Falta configurar la extensión: pulsa ⚙ arriba a la derecha.", "error");
  }
});

// --- Descarga del Excel -------------------------------------------------------
// Un solo botón: baja el corte recién procesado o, si no hay uno en esta sesión, el último en Supabase.
function rotularDescarga(cod) {
  botonDescargar.dataset.cod = cod || "";
  botonDescargar.textContent = cod ? `⬇ Descargar corte ${cod} (Excel)` : "⬇ Descargar último corte (Excel)";
}

botonDescargar.addEventListener("click", async () => {
  const estado = $("estadoDescarga");
  botonDescargar.disabled = true;
  mostrar(estado, "Consultando el corte en Supabase…");
  try {
    const r = await descargarCorte(await leerConfig(), botonDescargar.dataset.cod || null);
    rotularDescarga(r.cod);
    mostrar(estado, `✅ liquidaciones_silogtran_${r.cod}.xlsx (${r.filas} filas)`, "ok");
  } catch (e) {
    mostrar(estado, `❌ ${e.message}`, "error");
  } finally {
    botonDescargar.disabled = false;
  }
});

// --- Cerrar corte -------------------------------------------------------------
boton.addEventListener("click", async () => {
  const estado = $("estado");
  const config = await leerConfig();
  if (!config.token) return mostrar(estado, "Falta el token de GitHub: pulsa ⚙ arriba a la derecha.", "error");
  if (!confirm("¿Cerrar el corte con las liquidaciones nuevas?")) return;

  boton.disabled = true;
  const desde = new Date(Date.now() - 10000); // margen por diferencia de reloj
  try {
    mostrar(estado, "Enviando…");
    await dispararCorte(config);

    let corrida = null;
    for (let i = 0; i < 20 && !corrida; i++) {
      await esperar(3000);
      corrida = await buscarCorrida(config, desde);
    }
    if (!corrida) throw new Error("GitHub no inició el corte. Intenta de nuevo en un minuto.");

    // Unos 1–3 minutos; si hay un cron corriendo, espera en fila a que termine
    for (let i = 0; i < 120 && corrida.status !== "completed"; i++) {
      mostrar(estado, corrida.status === "queued"
        ? "En fila (esperando otra sincronización)…"
        : "Procesando el corte… (1–3 min)");
      await esperar(5000);
      corrida = await leerCorrida(config, corrida.id);
    }

    if (corrida.status !== "completed") {
      mostrar(estado, "Sigue en proceso. Abre de nuevo en unos minutos para descargarlo.");
    } else if (corrida.conclusion === "success") {
      const resultado = await leerResultado(config, corrida.id);
      mostrar(estado, `✅ ${resultado || "Corte terminado"}`, "ok");
      const cod = (resultado || "").match(/^Corte (\d+)/)?.[1];
      if (cod) rotularDescarga(cod);   // la descarga apunta al corte recién creado
    } else {
      mostrar(estado, "❌ El corte falló. Avisa al administrador.", "error");
    }
  } catch (e) {
    mostrar(estado, `❌ ${e.message}`, "error");
  } finally {
    boton.disabled = false;
  }
});
