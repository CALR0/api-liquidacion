// Generador mínimo de Excel (.xlsx) sin dependencias: una hoja con encabezado con estilo, fila fija,
// filtros, anchos de columna, montos con separador de miles y códigos como texto.
// Un .xlsx es un ZIP de archivos XML; aquí se arma sin compresión (método "store").

const XLSX_ESTILOS = { normal: 0, encabezado: 1, numero: 2, texto: 3 };

function xmlEscapar(v) {
  return String(v).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]))
    // caracteres de control no válidos en XML
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

function columnaLetra(i) {
  let s = "";
  for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
  return s;
}

function hojaXml(columnas, filas, numericas) {
  const ultima = columnaLetra(columnas.length - 1);
  const anchos = columnas.map((c) => {
    const largo = Math.max(c.length, ...filas.slice(0, 500).map((f) => String(f[c] ?? "").length));
    return Math.min(Math.max(largo + 2, 10), 50);
  });
  const celda = (ref, valor, col) => {
    if (valor === null || valor === undefined || valor === "") return "";
    if (numericas.has(col) && typeof valor === "number") {
      return `<c r="${ref}" s="${XLSX_ESTILOS.numero}"><v>${valor}</v></c>`;
    }
    return `<c r="${ref}" s="${XLSX_ESTILOS.texto}" t="inlineStr"><is><t xml:space="preserve">${xmlEscapar(valor)}</t></is></c>`;
  };
  const encabezado = columnas.map((c, j) =>
    `<c r="${columnaLetra(j)}1" s="${XLSX_ESTILOS.encabezado}" t="inlineStr"><is><t>${xmlEscapar(c)}</t></is></c>`).join("");
  const cuerpo = filas.map((f, i) =>
    `<row r="${i + 2}">${columnas.map((c, j) => celda(`${columnaLetra(j)}${i + 2}`, f[c], c)).join("")}</row>`).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${anchos.map((w, j) => `<col min="${j + 1}" max="${j + 1}" width="${w}" customWidth="1"/>`).join("")}</cols>
<sheetData><row r="1">${encabezado}</row>${cuerpo}</sheetData>
<autoFilter ref="A1:${ultima}${filas.length + 1}"/>
</worksheet>`;
}

function libroArchivos(nombreHoja, columnas, filas, numericas) {
  const hoja = xmlEscapar(nombreHoja).slice(0, 31);
  const ultima = columnaLetra(columnas.length - 1);
  return {
    "[Content_Types].xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`,
    "_rels/.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
    "xl/workbook.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="${hoja}" sheetId="1" r:id="rId1"/></sheets>
<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'${hoja}'!$A$1:$${ultima}$${filas.length + 1}</definedName></definedNames>
</workbook>`,
    "xl/_rels/workbook.xml.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`,
    "xl/styles.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`,
    "xl/worksheets/sheet1.xml": hojaXml(columnas, filas, numericas),
  };
}

// --- ZIP sin compresión ---------------------------------------------------
const CRC_TABLA = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLA[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function zipStore(archivos) {
  const enc = new TextEncoder();
  const partes = [], central = [];
  let offset = 0;
  for (const [nombre, contenido] of Object.entries(archivos)) {
    const n = enc.encode(nombre), d = enc.encode(contenido), crc = crc32(d);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
    local.setUint32(14, crc, true); local.setUint32(18, d.length, true); local.setUint32(22, d.length, true);
    local.setUint16(26, n.length, true);
    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true); cen.setUint16(4, 20, true); cen.setUint16(6, 20, true);
    cen.setUint16(8, 0x0800, true); cen.setUint32(16, crc, true); cen.setUint32(20, d.length, true);
    cen.setUint32(24, d.length, true); cen.setUint16(28, n.length, true); cen.setUint32(42, offset, true);
    partes.push(new Uint8Array(local.buffer), n, d);
    central.push(new Uint8Array(cen.buffer), n);
    offset += 30 + n.length + d.length;
  }
  const tamCentral = central.reduce((s, p) => s + p.length, 0);
  const fin = new DataView(new ArrayBuffer(22));
  const total = Object.keys(archivos).length;
  fin.setUint32(0, 0x06054b50, true); fin.setUint16(8, total, true); fin.setUint16(10, total, true);
  fin.setUint32(12, tamCentral, true); fin.setUint32(16, offset, true);
  return new Blob([...partes, ...central, new Uint8Array(fin.buffer)],
    { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

function crearXlsx(nombreHoja, columnas, filas, numericas) {
  return zipStore(libroArchivos(nombreHoja, columnas, filas, numericas));
}

if (typeof module !== "undefined") module.exports = { crearXlsx, libroArchivos, zipStore };
