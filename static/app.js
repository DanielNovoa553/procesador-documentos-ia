const $ = (id) => document.getElementById(id);

let documentos = [];
let archivoSeleccionado = null;

function el(tag, texto, clase) {
  const e = document.createElement(tag);
  if (texto !== undefined && texto !== null) e.textContent = String(texto);
  if (clase) e.className = clase;
  return e;
}

const moneda = (n) =>
  n === null || n === undefined
    ? "—"
    : Number(n).toLocaleString("es-MX", { style: "currency", currency: "MXN" });

const vacio = (v) => (v === null || v === undefined || v === "" ? "—" : v);

function formatearFecha(f) {
  if (!f) return "—";
  const d = new Date(f + "T00:00:00");
  return Number.isNaN(d.getTime())
    ? f
    : d.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" });
}

function insignia(estado) {
  const ok = estado === "validado";
  const span = el("span", null, "estado " + (ok ? "estado-ok" : "estado-rev"));
  span.append(el("i", null, "bi " + (ok ? "bi-check-circle-fill" : "bi-exclamation-triangle-fill")));
  span.append(document.createTextNode(ok ? "Validado" : "En revisión"));
  return span;
}

/* ---------- Tema ---------- */

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-bs-theme", tema);
  $("tema-icono").className = "bi " + (tema === "dark" ? "bi-sun" : "bi-moon-stars");
}

function iniciarTema() {
  let tema = null;
  try {
    tema = localStorage.getItem("tema");
  } catch (e) {
    tema = null;
  }
  if (!tema) {
    tema = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  aplicarTema(tema);
}

$("btn-tema").addEventListener("click", () => {
  const nuevo = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
  aplicarTema(nuevo);
  try {
    localStorage.setItem("tema", nuevo);
  } catch (e) {
    /* sin almacenamiento disponible: el tema solo dura esta sesión */
  }
});

/* ---------- Avisos ---------- */

function toast(texto, tipo = "success") {
  const iconos = {
    success: "bi-check-circle-fill",
    danger: "bi-x-octagon-fill",
    warning: "bi-exclamation-triangle-fill",
    info: "bi-info-circle-fill",
  };
  const t = el("div", null, "toast align-items-center border-0 text-bg-" + tipo);
  t.setAttribute("role", "alert");
  const fila = el("div", null, "d-flex");
  const cuerpo = el("div", null, "toast-body");
  cuerpo.append(el("i", null, "bi " + iconos[tipo] + " me-2"), document.createTextNode(texto));
  const cerrar = el("button", null, "btn-close btn-close-white me-2 m-auto");
  cerrar.type = "button";
  cerrar.setAttribute("data-bs-dismiss", "toast");
  cerrar.setAttribute("aria-label", "Cerrar");
  fila.append(cuerpo, cerrar);
  t.append(fila);
  $("toasts").append(t);
  t.addEventListener("hidden.bs.toast", () => t.remove());
  new bootstrap.Toast(t, { delay: 5000 }).show();
}

/* ---------- Información del servidor ---------- */

async function cargarInfo() {
  try {
    const info = await (await fetch("/info")).json();
    const real = info.modo === "real";
    const b = $("modo");
    b.textContent = real ? "Modo real · " + info.modelo : "Modo simulado";
    b.className = "modo-badge" + (real ? " real" : "");
  } catch (e) {
    $("modo").textContent = "Sin conexión";
  }
}

/* ---------- Resumen y tabla ---------- */

function actualizarResumen() {
  const total = documentos.length;
  const validados = documentos.filter((d) => d.estado === "validado").length;
  const revision = total - validados;
  $("kpi-total").textContent = total;
  $("kpi-validados").textContent = validados;
  $("kpi-revision").textContent = revision;
  $("kpi-tasa").textContent = total ? Math.round((validados / total) * 100) + " %" : "—";
}

function filtrados() {
  const estado = $("filtro").value;
  const texto = $("buscar").value.trim().toLowerCase();
  return documentos.filter((d) => {
    if (estado && d.estado !== estado) return false;
    if (!texto) return true;
    const emisor = String(d.datos.emisor || "").toLowerCase();
    return d.archivo.toLowerCase().includes(texto) || emisor.includes(texto);
  });
}

function pintarTabla() {
  const tbody = $("tabla");
  tbody.replaceChildren();
  const lista = filtrados();

  if (lista.length === 0) {
    const tr = el("tr");
    const td = el("td", null, "vacio");
    td.colSpan = 6;
    td.append(el("i", null, "bi bi-inbox"));
    td.append(
      document.createTextNode(
        documentos.length === 0
          ? "Aún no hay documentos. Sube una factura en PDF para empezar."
          : "Ningún documento coincide con la búsqueda."
      )
    );
    tr.append(td);
    tbody.append(tr);
  }

  for (const d of lista) {
    const tr = el("tr");
    const celdaEstado = el("td");
    celdaEstado.append(insignia(d.estado));
    const flecha = el("td", null, "text-end text-secondary");
    flecha.append(el("i", null, "bi bi-chevron-right"));
    tr.append(
      el("td", d.archivo, "fw-medium"),
      el("td", vacio(d.datos.emisor)),
      el("td", formatearFecha(d.datos.fecha)),
      el("td", moneda(d.datos.total), "num"),
      celdaEstado,
      flecha
    );
    tr.addEventListener("click", () => abrirDetalle(d));
    tbody.append(tr);
  }

  $("contador").textContent =
    documentos.length === 0 ? "" : "Mostrando " + lista.length + " de " + documentos.length + " documentos";
}

async function cargarLista() {
  try {
    const r = await fetch("/documentos?limite=200");
    if (!r.ok) throw new Error("respuesta " + r.status);
    documentos = await r.json();
  } catch (e) {
    toast("No se pudo cargar la lista de documentos.", "danger");
    documentos = [];
  }
  actualizarResumen();
  pintarTabla();
}

/* ---------- Detalle ---------- */

/* ---------- Detalle ---------- */

function dato(clave, valor) {
  const f = el("div", null, "dato");
  f.append(el("span", clave, "clave"), el("span", vacio(valor), "valor"));
  return f;
}

function bloque(titulo, filas) {
  const b = el("div", null, "bloque");
  b.append(el("div", titulo, "seccion-titulo"));
  const rejilla = el("div", null, "rejilla");
  for (const [clave, valor] of filas) rejilla.append(dato(clave, valor));
  b.append(rejilla);
  return b;
}

function abrirDetalle(d) {
  const x = d.datos;
  $("detalle-titulo").textContent = d.archivo;
  $("detalle-fecha").textContent = "Procesado el " + new Date(d.creado_en).toLocaleString("es-MX");

  const cuerpo = $("detalle-cuerpo");
  cuerpo.replaceChildren();

  const cabecera = el("div", null, "d-flex flex-wrap align-items-center gap-3 mb-3");
  cabecera.append(insignia(d.estado));
  if (x.folio_fiscal) {
    const u = el("span", null, "text-secondary small");
    u.append(document.createTextNode("Folio fiscal: "), el("span", x.folio_fiscal, "uuid"));
    cabecera.append(u);
  }
  cuerpo.append(cabecera);

  if (d.motivos.length > 0) {
    const aviso = el("div", null, "aviso-revision");
    aviso.append(el("div", "Requiere revisión manual", "fw-semibold"));
    const lista = el("ul");
    for (const m of d.motivos) lista.append(el("li", m.detalle));
    aviso.append(lista);
    cuerpo.append(aviso);
  }

  cuerpo.append(
    bloque("Emisor", [
      ["Nombre", x.emisor],
      ["RFC", x.rfc_emisor],
      ["Régimen fiscal", x.regimen_fiscal_emisor],
      ["Lugar de expedición (C. P.)", x.lugar_expedicion],
    ]),
    bloque("Receptor", [
      ["Nombre", x.nombre_receptor],
      ["RFC", x.rfc_receptor],
      ["Régimen fiscal", x.regimen_fiscal_receptor],
      ["Código postal", x.codigo_postal_receptor],
      ["Uso de CFDI", x.uso_cfdi],
    ]),
    bloque("Comprobante", [
      ["Tipo", x.tipo_comprobante],
      ["Serie", x.serie],
      ["Folio", x.folio],
      ["Fecha de emisión", formatearFecha(x.fecha)],
      ["Moneda", x.moneda],
      ["Forma de pago", x.forma_pago],
      ["Método de pago", x.metodo_pago],
      ["Exportación", x.exportacion],
    ])
  );

  const conceptos = x.conceptos || [];
  const descuento = conceptos.reduce((s, c) => s + (c.descuento || 0), 0);
  const filasImportes = [["Subtotal", moneda(x.subtotal)]];
  if (descuento > 0) filasImportes.push(["Descuento", moneda(descuento)]);
  filasImportes.push(
    ["IVA", x.iva === null || x.iva === undefined ? "Sin IVA" : moneda(x.iva)],
    ["Total", moneda(x.total)]
  );
  cuerpo.append(bloque("Importes", filasImportes));

  const seccion = el("div", null, "bloque");
  seccion.append(el("div", "Conceptos", "seccion-titulo"));
  const envoltura = el("div", null, "table-responsive");
  const tabla = el("table", null, "table table-sm tabla mb-0");
  const thead = el("thead");
  const cab = el("tr");
  for (const [texto, clase] of [
    ["Clave", ""], ["Descripción", ""], ["Cant.", "text-end"],
    ["Unidad", ""], ["V. unitario", "text-end"], ["Importe", "text-end"],
  ]) {
    cab.append(el("th", texto, clase));
  }
  thead.append(cab);
  const tb = el("tbody");

  if (conceptos.length === 0) {
    const tr = el("tr");
    const td = el("td", "Sin conceptos", "text-secondary");
    td.colSpan = 6;
    tr.append(td);
    tb.append(tr);
  }
  for (const c of conceptos) {
    const tr = el("tr");
    tr.style.cursor = "default";
    const desc = el("td", c.descripcion);
    if (c.objeto_impuesto) desc.append(el("div", c.objeto_impuesto, "celda-sec"));
    const unidad = el("td", vacio(c.unidad));
    if (c.clave_unidad) unidad.append(el("div", c.clave_unidad, "celda-sec"));
    tr.append(
      el("td", vacio(c.clave_prod_serv)),
      desc,
      el("td", c.cantidad, "num"),
      unidad,
      el("td", c.valor_unitario === null || c.valor_unitario === undefined ? "—" : moneda(c.valor_unitario), "num"),
      el("td", moneda(c.importe), "num")
    );
    tb.append(tr);
  }
  tabla.append(thead, tb);
  envoltura.append(tabla);
  seccion.append(envoltura);
  cuerpo.append(seccion);

  cuerpo.append(bloque("Origen", [["Extraído con", d.modelo]]));

  const pie = $("detalle-pie");
  pie.replaceChildren();

  const copiar = el("button", null, "btn btn-outline-secondary btn-sm");
  copiar.type = "button";
  copiar.append(el("i", null, "bi bi-clipboard me-1"), document.createTextNode("Copiar JSON"));
  copiar.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(d.datos, null, 2));
      toast("JSON copiado al portapapeles.", "success");
    } catch (e) {
      toast("No se pudo copiar. Usa el botón de descarga.", "warning");
    }
  });

  const descargar = el("button", null, "btn btn-outline-secondary btn-sm");
  descargar.type = "button";
  descargar.append(el("i", null, "bi bi-download me-1"), document.createTextNode("Descargar JSON"));
  descargar.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(d.datos, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = d.archivo.replace(/\.pdf$/i, "") + ".json";
    a.click();
    URL.revokeObjectURL(url);
  });

  const eliminar = el("button", null, "btn btn-outline-danger btn-sm me-auto");
  eliminar.type = "button";
  eliminar.append(el("i", null, "bi bi-trash me-1"), document.createTextNode("Eliminar"));
  eliminar.addEventListener("click", async () => {
    if (!confirm("¿Eliminar este documento de la base de datos?")) return;
    try {
      const r = await fetch("/documentos/" + d.id, { method: "DELETE" });
      if (!r.ok) throw new Error("respuesta " + r.status);
      bootstrap.Modal.getOrCreateInstance($("detalle")).hide();
      toast("Documento eliminado.", "success");
      await cargarLista();
    } catch (e) {
      toast("No se pudo eliminar el documento.", "danger");
    }
  });

  const cerrar = el("button", "Cerrar", "btn btn-primary btn-sm");
  cerrar.type = "button";
  cerrar.setAttribute("data-bs-dismiss", "modal");

  pie.append(eliminar, copiar, descargar, cerrar);

  bootstrap.Modal.getOrCreateInstance($("detalle")).show();
}

/* ---------- Subida de archivos ---------- */

function elegirArchivo(archivo) {
  if (!archivo) return;
  const esPdf = archivo.type === "application/pdf" || archivo.name.toLowerCase().endsWith(".pdf");
  if (!esPdf) {
    toast("Solo se aceptan archivos PDF.", "warning");
    return;
  }
  archivoSeleccionado = archivo;
  $("dz-texto").textContent = archivo.name;
  $("dz-nombre").textContent = (archivo.size / 1024).toFixed(0) + " KB · listo para procesar";
  $("dropzone").classList.add("lleno");
  $("enviar").disabled = false;
}

const zona = $("dropzone");
zona.addEventListener("click", () => $("archivo").click());
zona.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    $("archivo").click();
  }
});
$("archivo").addEventListener("change", (ev) => elegirArchivo(ev.target.files[0]));

for (const evento of ["dragenter", "dragover"]) {
  zona.addEventListener(evento, (ev) => {
    ev.preventDefault();
    zona.classList.add("activa");
  });
}
for (const evento of ["dragleave", "drop"]) {
  zona.addEventListener(evento, (ev) => {
    ev.preventDefault();
    zona.classList.remove("activa");
  });
}
zona.addEventListener("drop", (ev) => elegirArchivo(ev.dataTransfer.files[0]));

function reiniciarZona() {
  archivoSeleccionado = null;
  $("archivo").value = "";
  $("dz-texto").textContent = "Arrastra una factura en PDF o haz clic para seleccionarla";
  $("dz-nombre").textContent = "Máximo 5 MB";
  zona.classList.remove("lleno");
}

function cargando(activo) {
  $("enviar").disabled = activo || !archivoSeleccionado;
  $("enviar-spinner").classList.toggle("d-none", !activo);
  $("enviar-texto").textContent = activo ? "Procesando…" : "Procesar";
}

$("enviar").addEventListener("click", async () => {
  if (!archivoSeleccionado) return;
  const datos = new FormData();
  datos.append("archivo", archivoSeleccionado);
  cargando(true);

  try {
    const r = await fetch("/documentos", { method: "POST", body: datos });
    const cuerpo = await r.json();
    if (!r.ok) {
      const detalle = typeof cuerpo.detail === "string" ? cuerpo.detail : "No se pudo procesar el documento.";
      toast(detalle, "danger");
    } else {
      if (r.status === 200) {
        toast("Este documento ya estaba procesado.", "info");
      } else if (cuerpo.estado === "validado") {
        toast("Documento procesado y validado.", "success");
      } else {
        toast("Documento procesado: requiere revisión manual.", "warning");
      }
      reiniciarZona();
      await cargarLista();
      abrirDetalle(cuerpo);
    }
  } catch (e) {
    toast("No se pudo conectar con el servidor.", "danger");
  } finally {
    cargando(false);
  }
});

$("filtro").addEventListener("change", pintarTabla);
$("buscar").addEventListener("input", pintarTabla);

iniciarTema();
cargarInfo();
cargarLista();