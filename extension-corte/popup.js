const boton = document.getElementById("cerrar");
const estado = document.getElementById("estado");
const botonUltimo = document.getElementById("descargarUltimo");
const estadoDescarga = document.getElementById("estadoDescarga");
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function mostrar(el, html, clase = "") {
  el.className = clase;
  el.innerHTML = html;
}

document.getElementById("opciones").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

// El último corte cerrado desde este equipo queda listo para descargar al abrir la ventanita
async function ofrecerUltimo(cod) {
  if (!cod) return;
  botonUltimo.textContent = `⬇ Descargar corte ${cod} (Excel)`;
  botonUltimo.dataset.cod = cod;
  botonUltimo.hidden = false;
}
chrome.storage.local.get("ultimoCorte").then(({ ultimoCorte }) => ofrecerUltimo(ultimoCorte));

async function descargar(cod) {
  const config = await leerConfig();
  mostrar(estadoDescarga, `Preparando corte ${cod}…`);
  try {
    const n = await descargarCorte(config, cod);
    mostrar(estadoDescarga, `✅ liquidaciones_silogtran_${cod}.xlsx (${n} filas)`, "ok");
  } catch (e) {
    mostrar(estadoDescarga, `❌ ${e.message}`, "error");
  }
}

botonUltimo.addEventListener("click", () => descargar(botonUltimo.dataset.cod));
document.getElementById("descargar").addEventListener("click", () => {
  const cod = document.getElementById("numero").value.trim();
  if (!/^\d+$/.test(cod)) {
    mostrar(estadoDescarga, "Escribe el número del corte.", "error");
    return;
  }
  descargar(cod);
});

boton.addEventListener("click", async () => {
  const config = await leerConfig();
  if (!config.token) {
    mostrar(estado, "Falta configurar el token en Opciones.", "error");
    return;
  }
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
    if (!corrida) throw new Error("GitHub no inició la corrida. Intenta de nuevo en un minuto.");

    const enlace = `<a href="${corrida.html_url}" target="_blank">ver detalle</a>`;
    // Unos 1–3 minutos; si hay un cron corriendo, espera en fila a que termine
    for (let i = 0; i < 120 && corrida.status !== "completed"; i++) {
      mostrar(estado, corrida.status === "queued"
        ? `En fila (esperando otra sincronización)… ${enlace}`
        : `Procesando el corte… ${enlace}`);
      await esperar(5000);
      corrida = await leerCorrida(config, corrida.id);
    }

    if (corrida.status !== "completed") {
      mostrar(estado, `Sigue en proceso; revisa el resultado en ${enlace}.`);
    } else if (corrida.conclusion === "success") {
      const resultado = await leerResultado(config, corrida.id);
      mostrar(estado, `✅ ${resultado || "Corte terminado"} · ${enlace}`, "ok");
      const cod = (resultado || "").match(/^Corte (\d+)/)?.[1];
      if (cod) {
        await chrome.storage.local.set({ ultimoCorte: cod });
        ofrecerUltimo(cod);
      }
    } else {
      mostrar(estado, `❌ El corte falló. Avisa al administrador · ${enlace}`, "error");
    }
  } catch (e) {
    mostrar(estado, `❌ ${e.message}`, "error");
  } finally {
    boton.disabled = false;
  }
});
