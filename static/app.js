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
  const etiquetas = {
    validado: ["Validado", "estado-ok", "bi-check-circle-fill"],
    aprobado: ["Aprobado", "estado-ok", "bi-check-circle-fill"],
    corregido: ["Corregido", "estado-ok", "bi-pencil-square"],
    revision_manual: ["En revisión", "estado-rev", "bi-exclamation-triangle-fill"],
    rechazado: ["Rechazado", "estado-rechazado", "bi-x-circle-fill"],
  };
  const [texto, clase, icono] = etiquetas[estado] || etiquetas.revision_manual;
  const span = el("span", null, "estado " + clase);
  span.append(el("i", null, "bi " + icono));
  span.append(document.createTextNode(texto));
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

/* ---------- Configuración de la IA ---------- */

let configActual = null;

const proveedorElegido = () => document.querySelector('input[name="proveedor"]:checked').value;
const privacidadElegida = () => document.querySelector('input[name="privacidad"]:checked').value;

function pintarModelos() {
  const prov = proveedorElegido();
  const lista = prov === "ollama" ? configActual.ollama_modelos : configActual.gemini_modelos;
  const select = $("cfg-modelo");
  select.replaceChildren();
  lista.forEach((m) => {
    const o = el("option", m);
    o.value = m;
    select.append(o);
  });
  if (configActual.proveedor === prov && lista.includes(configActual.modelo)) {
    select.value = configActual.modelo;
  }
  let ayuda = "";
  if (prov === "ollama" && !lista.length) {
    ayuda = "No se encontró Ollama o no tiene modelos instalados. Abre Ollama e instala uno con 'ollama pull'.";
  } else if (prov === "gemini" && !configActual.gemini_api_key) {
    ayuda = "Falta GEMINI_API_KEY en el archivo .env.";
  }
  $("cfg-modelo-ayuda").textContent = ayuda;
  actualizarPrivacidad();
}

function actualizarPrivacidad() {
  const gemini = proveedorElegido() === "gemini";
  const sin = gemini && privacidadElegida() === "sin_mascara";
  $("cfg-privacidad").classList.toggle("d-none", !gemini);
  $("cfg-aviso").classList.toggle("d-none", !sin);
  if (!sin) $("cfg-acepto").checked = false;
  validarConfig();
}

function validarConfig() {
  const sin = proveedorElegido() === "gemini" && privacidadElegida() === "sin_mascara";
  $("cfg-guardar").disabled = !$("cfg-modelo").value || (sin && !$("cfg-acepto").checked);
}

async function abrirConfig() {
  try {
    const r = await fetch("/config");
    if (!r.ok) throw new Error("respuesta " + r.status);
    configActual = await r.json();
  } catch (e) {
    toast("No se pudo cargar la configuración.", "danger");
    return;
  }
  $("config-simulado").classList.toggle("d-none", configActual.modo === "real");
  $(configActual.proveedor === "gemini" ? "prov-gemini" : "prov-ollama").checked = true;
  $(configActual.privacidad === "sin_mascara" ? "priv-sin" : "priv-mascara").checked = true;
  $("cfg-acepto").checked = false;
  pintarModelos();
  bootstrap.Modal.getOrCreateInstance($("config")).show();
}

async function guardarConfig() {
  const cuerpo = {
    proveedor: proveedorElegido(),
    modelo: $("cfg-modelo").value,
    privacidad: privacidadElegida(),
    acepta_riesgo: $("cfg-acepto").checked,
  };
  try {
    const r = await fetch("/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const datos = await r.json();
    if (!r.ok) {
      toast(typeof datos.detail === "string" ? datos.detail : "No se pudo guardar la configuración.", "danger");
      return;
    }
    bootstrap.Modal.getOrCreateInstance($("config")).hide();
    toast("Configuración guardada.", "success");
    await cargarInfo();
  } catch (e) {
    toast("No se pudo conectar con el servidor.", "danger");
  }
}

document.querySelectorAll('input[name="proveedor"]').forEach((i) => i.addEventListener("change", pintarModelos));
document.querySelectorAll('input[name="privacidad"]').forEach((i) => i.addEventListener("change", actualizarPrivacidad));
$("cfg-acepto").addEventListener("change", validarConfig);
$("cfg-modelo").addEventListener("change", validarConfig);
$("cfg-guardar").addEventListener("click", guardarConfig);
$("btn-config").addEventListener("click", abrirConfig);

/* ---------- Resumen y tabla ---------- */

function actualizarResumen() {
  const total = documentos.length;
  const aceptados = new Set(["validado", "aprobado", "corregido"]);
  const validados = documentos.filter((d) => aceptados.has(d.estado)).length;
  const revision = documentos.filter((d) => d.estado === "revision_manual").length;
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

function campo(clave, valor, ancho, extra) {
  const c = el("div", null, "campo" + (ancho ? " ancho" : ""));
  c.append(el("div", clave, "campo-clave"));
  const faltante = valor === null || valor === undefined || valor === "";
  const clases = "campo-valor" + (faltante ? " sin-dato" : "") + (extra && !faltante ? " " + extra : "");
  const v = el("div", faltante ? "No aparece" : valor, clases);
  if (faltante) v.title = "No aparece en el documento";
  c.append(v);
  return c;
}

function panel(titulo, hijos) {
  const p = el("section", null, "panel");
  p.append(el("h3", titulo, "panel-titulo"));
  const g = el("div", null, "panel-grid");
  g.append(...hijos);
  p.append(g);
  return p;
}

function filaImporte(clave, valor, total) {
  const f = el("div", null, "importe-fila" + (total ? " importe-total" : ""));
  f.append(el("span", clave), el("span", valor));
  return f;
}

function abrirDetalle(d) {
  const x = d.datos;
  $("detalle-titulo").textContent = d.archivo;
  $("detalle-fecha").textContent =
    "Procesado el " + new Date(d.creado_en).toLocaleString("es-MX") + " · Extraído con " + d.modelo;

  const cuerpo = $("detalle-cuerpo");
  cuerpo.replaceChildren();

  const barra = el("div", null, "mb-3");
  barra.append(insignia(d.estado));
  cuerpo.append(barra);

  if (d.motivos.length > 0) {
    const aviso = el("div", null, "aviso-revision");
    aviso.append(el(
      "div",
      d.estado === "revision_manual" ? "Requiere revisión manual" : "Alertas de validación",
      "fw-semibold"
    ));
    const lista = el("ul");
    for (const m of d.motivos) lista.append(el("li", m.detalle));
    aviso.append(lista);
    cuerpo.append(aviso);
  }

  const paneles = el("div", null, "paneles");
  paneles.append(
    panel("Emisor", [
      campo("Nombre", x.emisor, true),
      campo("RFC", x.rfc_emisor),
      campo("Lugar de expedición (C. P.)", x.lugar_expedicion),
      campo("Régimen fiscal", x.regimen_fiscal_emisor, true),
    ]),
    panel("Receptor", [
      campo("Nombre", x.nombre_receptor, true),
      campo("RFC", x.rfc_receptor),
      campo("Código postal", x.codigo_postal_receptor),
      campo("Régimen fiscal", x.regimen_fiscal_receptor, true),
      campo("Uso de CFDI", x.uso_cfdi, true),
    ]),
    panel("Comprobante", [
      campo("Folio fiscal (UUID)", x.folio_fiscal, true, "uuid"),
      campo("Tipo", x.tipo_comprobante),
      campo("Fecha de emisión", x.fecha ? formatearFecha(x.fecha) : null),
      campo("Serie", x.serie),
      campo("Folio del emisor", x.folio),
      campo("Moneda", x.moneda),
      campo("Exportación", x.exportacion),
      campo("Forma de pago", x.forma_pago),
      campo("Método de pago", x.metodo_pago),
    ])
  );
  cuerpo.append(paneles);

  const conceptos = x.conceptos || [];

  const secConceptos = el("section", null, "panel");
  secConceptos.append(el("h3", "Conceptos", "panel-titulo"));
  const envoltura = el("div", null, "tabla-conceptos");
  const tabla = el("table", null, "table tabla mb-0");
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
    const desc = el("td", c.descripcion);
    if (c.objeto_impuesto) desc.append(el("div", c.objeto_impuesto, "celda-sec"));
    const unidad = el("td", vacio(c.unidad));
    if (c.clave_unidad) unidad.append(el("div", c.clave_unidad, "celda-sec"));
    tr.append(
      el("td", vacio(c.clave_prod_serv || c.no_identificacion)),
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
  secConceptos.append(envoltura);

  const descuento = conceptos.reduce((s, c) => s + (c.descuento || 0), 0);
  const secImportes = el("section", null, "panel");
  secImportes.append(el("h3", "Importes", "panel-titulo"));
  secImportes.append(filaImporte("Subtotal", moneda(x.subtotal)));
  if (descuento > 0) secImportes.append(filaImporte("Descuento", moneda(descuento)));
  secImportes.append(
    filaImporte("IVA", x.iva === null || x.iva === undefined ? "Sin IVA" : moneda(x.iva)),
    filaImporte("Total", moneda(x.total), true)
  );

  const inferior = el("div", null, "fila-inferior");
  inferior.append(secConceptos, secImportes);
  cuerpo.append(inferior);

  const revision = el("section", null, "panel mt-3");
  revision.append(el("h3", "Revisión manual", "panel-titulo"));
  const etiquetaRevisor = el("label", "Revisor", "form-label small fw-semibold");
  etiquetaRevisor.htmlFor = "revisor-" + d.id;
  revision.append(etiquetaRevisor);
  const revisor = el("input", null, "form-control form-control-sm mb-2");
  revisor.id = "revisor-" + d.id;
  revisor.type = "text";
  revisor.maxLength = 100;
  revisor.placeholder = "Nombre del revisor (opcional)";
  revision.append(revisor);
  const etiquetaComentario = el("label", "Comentario o motivo de rechazo", "form-label small fw-semibold");
  etiquetaComentario.htmlFor = "comentario-" + d.id;
  revision.append(etiquetaComentario);
  const comentario = el("textarea", null, "form-control form-control-sm mb-2");
  comentario.id = "comentario-" + d.id;
  comentario.rows = 2;
  comentario.maxLength = 1000;
  comentario.placeholder = "Comentario (obligatorio para rechazar)";
  revision.append(comentario);

  const acciones = el("div", null, "d-flex flex-wrap gap-2");
  const aprobar = el("button", null, "btn btn-success btn-sm");
  aprobar.type = "button";
  aprobar.append(el("i", null, "bi bi-check-lg me-1"), document.createTextNode("Aprobar"));
  aprobar.addEventListener("click", () => ejecutarRevision(
    d,
    "aprobar",
    { revisor: revisor.value.trim() || "Revisor", comentario: comentario.value }
  ));
  const corregir = el("button", null, "btn btn-outline-primary btn-sm");
  corregir.type = "button";
  corregir.append(el("i", null, "bi bi-pencil me-1"), document.createTextNode("Editar datos"));
  acciones.append(aprobar, corregir);

  const rechazar = el("button", null, "btn btn-outline-danger btn-sm");
  rechazar.type = "button";
  rechazar.append(el("i", null, "bi bi-x-lg me-1"), document.createTextNode("Rechazar"));
  rechazar.addEventListener("click", () => {
    if (!comentario.value.trim()) {
      toast("Escribe el motivo del rechazo.", "warning");
      comentario.focus();
      return;
    }
    ejecutarRevision(d, "rechazar", {
      revisor: revisor.value.trim() || "Revisor",
      motivo: comentario.value.trim(),
    });
  });
  acciones.append(rechazar);

  const editor = el("div", null, "d-none mt-3");
  const etiquetaJson = el("label", "Datos extraídos (JSON)", "form-label small fw-semibold");
  const json = el("textarea", null, "form-control font-monospace small");
  json.id = "datos-json-" + d.id;
  etiquetaJson.htmlFor = json.id;
  editor.append(etiquetaJson);
  json.rows = 14;
  json.spellcheck = false;
  json.value = JSON.stringify(d.datos, null, 2);
  editor.append(json);
  const guardarCorreccion = el("button", "Guardar corrección", "btn btn-primary btn-sm mt-2");
  guardarCorreccion.type = "button";
  guardarCorreccion.addEventListener("click", async () => {
    let datosCorregidos;
    try {
      datosCorregidos = JSON.parse(json.value);
      if (!datosCorregidos || Array.isArray(datosCorregidos) || typeof datosCorregidos !== "object") {
        throw new Error("El contenido debe ser un objeto JSON.");
      }
    } catch (e) {
      toast("JSON inválido: " + e.message, "warning");
      return;
    }
    await ejecutarRevision(d, "corregir", {
      revisor: revisor.value.trim() || "Revisor",
      comentario: comentario.value,
      datos: datosCorregidos,
    });
  });
  editor.append(guardarCorreccion);
  corregir.addEventListener("click", () => {
    editor.classList.toggle("d-none");
    json.value = JSON.stringify(d.datos, null, 2);
    if (!editor.classList.contains("d-none")) json.focus();
  });

  revision.append(acciones, editor);
  cuerpo.append(revision);

  const secBitacora = el("section", null, "panel mt-3");
  secBitacora.append(el("h3", "Bitácora de cambios", "panel-titulo"));
  const listaBitacora = el("div", "Cargando bitácora…", "text-secondary small");
  secBitacora.append(listaBitacora);
  cuerpo.append(secBitacora);
  cargarBitacora(d.id, listaBitacora);

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

async function ejecutarRevision(documento, accion, datos) {
  const metodos = { aprobar: "POST", corregir: "PUT", rechazar: "POST" };
  try {
    const r = await fetch("/documentos/" + documento.id + "/" + accion, {
      method: metodos[accion],
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    });
    const respuesta = await r.json();
    if (!r.ok) {
      const detalle = typeof respuesta.detail === "string"
        ? respuesta.detail
        : JSON.stringify(respuesta.detail || "No se pudo guardar la revisión.");
      toast(detalle, "danger");
      return;
    }
    toast("Revisión guardada.", "success");
    await cargarLista();
    abrirDetalle(respuesta);
  } catch (e) {
    toast("No se pudo conectar con el servidor.", "danger");
  }
}

async function cargarBitacora(documentoId, destino) {
  try {
    const r = await fetch("/documentos/" + documentoId + "/bitacora");
    const cambios = await r.json();
    if (!r.ok) throw new Error("respuesta " + r.status);
    destino.replaceChildren();
    if (cambios.length === 0) {
      destino.append(el("div", "Aún no hay cambios registrados.", "text-secondary small"));
      return;
    }
    for (const cambio of cambios) {
      const entrada = el("article", null, "bitacora-item");
      const encabezado = el("div", null, "d-flex flex-wrap justify-content-between gap-2");
      encabezado.append(
        el("strong", cambio.accion[0].toUpperCase() + cambio.accion.slice(1)),
        el("span", new Date(cambio.creado_en).toLocaleString("es-MX"), "text-secondary small")
      );
      entrada.append(encabezado);
      entrada.append(el(
        "div",
        cambio.revisor + " · " + cambio.estado_anterior + " → " + cambio.estado_nuevo,
        "small"
      ));
      if (cambio.comentario) entrada.append(el("div", cambio.comentario, "small mt-1"));

      const campos = Object.keys({ ...cambio.datos_anteriores, ...cambio.datos_nuevos })
        .filter((clave) =>
          JSON.stringify(cambio.datos_anteriores[clave]) !== JSON.stringify(cambio.datos_nuevos[clave])
        );
      const motivosCambiaron =
        JSON.stringify(cambio.motivos_anteriores) !== JSON.stringify(cambio.motivos_nuevos);
      if (campos.length > 0 || motivosCambiaron) {
        const detalle = el("details", null, "small mt-1");
        detalle.append(el(
          "summary",
          "Diferencias" + (campos.length ? ": " + campos.join(", ") : "")
        ));
        for (const clave of campos) {
          const anterior = JSON.stringify(cambio.datos_anteriores[clave]);
          const nuevo = JSON.stringify(cambio.datos_nuevos[clave]);
          detalle.append(el("div", clave + ": " + anterior + " → " + nuevo, "text-break"));
        }
        if (motivosCambiaron) {
          detalle.append(el(
            "div",
            "Motivos: " + JSON.stringify(cambio.motivos_anteriores) + " → " +
              JSON.stringify(cambio.motivos_nuevos),
            "text-break"
          ));
        }
        entrada.append(detalle);
      }
      destino.append(entrada);
    }
  } catch (e) {
    destino.textContent = "No se pudo cargar la bitácora.";
  }
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