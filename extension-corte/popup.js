const $ = (id) => document.getElementById(id);
const boton = $("cerrar");
const botonUltimo = $("descargarUltimo");
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

leerConfig().then((config) => {
  if (!config.token) verConfig(true);   // primera vez: abre directo la configuración
});

// --- Descarga del Excel -------------------------------------------------------
function ofrecerUltimo(cod) {
  if (!cod) return;
  botonUltimo.textContent = `⬇ Descargar corte ${cod} (Excel)`;
  botonUltimo.dataset.cod = cod;
  botonUltimo.hidden = false;
}
chrome.storage.local.get("ultimoCorte").then(({ ultimoCorte }) => ofrecerUltimo(ultimoCorte));

async function descargar(cod) {
  const estado = $("estadoDescarga");
  mostrar(estado, `Preparando corte ${cod}…`);
  try {
    const n = await descargarCorte(await leerConfig(), cod);
    mostrar(estado, `✅ liquidaciones_silogtran_${cod}.xlsx (${n} filas)`, "ok");
  } catch (e) {
    mostrar(estado, `❌ ${e.message}`, "error");
  }
}

botonUltimo.addEventListener("click", () => descargar(botonUltimo.dataset.cod));
$("descargar").addEventListener("click", () => {
  const cod = $("numero").value.trim();
  if (!/^\d+$/.test(cod)) return mostrar($("estadoDescarga"), "Escribe el número del corte.", "error");
  descargar(cod);
});

// --- Cerrar corte -------------------------------------------------------------
boton.addEventListener("click", async () => {
  const estado = $("estado");
  const config = await leerConfig();
  if (!config.token) return verConfig(true);
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
      if (cod) {
        await chrome.storage.local.set({ ultimoCorte: cod });
        ofrecerUltimo(cod);
      }
    } else {
      mostrar(estado, "❌ El corte falló. Avisa al administrador.", "error");
    }
  } catch (e) {
    mostrar(estado, `❌ ${e.message}`, "error");
  } finally {
    boton.disabled = false;
  }
});
