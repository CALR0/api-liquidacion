const boton = document.getElementById("cerrar");
const estado = document.getElementById("estado");
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function mostrar(html, clase = "") {
  estado.className = clase;
  estado.innerHTML = html;
}

document.getElementById("opciones").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

boton.addEventListener("click", async () => {
  const config = await leerConfig();
  if (!config.token) {
    mostrar("Falta configurar el token en Opciones.", "error");
    return;
  }
  if (!confirm("¿Cerrar el corte con las liquidaciones nuevas?")) return;

  boton.disabled = true;
  const desde = new Date(Date.now() - 10000); // margen por diferencia de reloj
  try {
    mostrar("Enviando…");
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
      mostrar(corrida.status === "queued"
        ? `En fila (esperando otra sincronización)… ${enlace}`
        : `Procesando el corte… ${enlace}`);
      await esperar(5000);
      corrida = await leerCorrida(config, corrida.id);
    }

    if (corrida.status !== "completed") {
      mostrar(`Sigue en proceso; revisa el resultado en ${enlace}.`);
    } else if (corrida.conclusion === "success") {
      const resultado = await leerResultado(config, corrida.id);
      mostrar(`✅ ${resultado || "Corte terminado"} · ${enlace}`, "ok");
    } else {
      mostrar(`❌ El corte falló. Avisa al administrador · ${enlace}`, "error");
    }
  } catch (e) {
    mostrar(`❌ ${e.message}`, "error");
  } finally {
    boton.disabled = false;
  }
});
