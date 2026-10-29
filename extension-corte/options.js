const campos = ["token", "origen", "repo"];

leerConfig().then((config) => {
  for (const c of campos) document.getElementById(c).value = config[c];
});

document.getElementById("guardar").addEventListener("click", async () => {
  const valores = Object.fromEntries(campos.map((c) => [c, document.getElementById(c).value.trim()]));
  await chrome.storage.local.set(valores);
  document.getElementById("guardado").textContent = "Guardado ✓";
});
