# Procesador inteligente de documentos

API y aplicación web en Python que recibe **facturas en PDF**, extrae sus datos en formato estructurado con un modelo de lenguaje —**local con Ollama** o en la nube con **Gemini**—, los **valida con reglas de negocio** y guarda el resultado en una base de datos. Los documentos con datos inconsistentes no se aceptan en silencio: quedan marcados para **revisión manual**, con el motivo.

> **Proyecto de portafolio.** No es un sistema listo para producción; las limitaciones están descritas más abajo.

## Qué hace

1. Subes una factura en PDF (por la página web o por la API).
2. El modelo elegido lee el documento y devuelve los datos con un esquema fijo (JSON): emisor, receptor, folio fiscal, montos, conceptos y más.
3. El sistema valida los datos con reglas propias (por ejemplo, que subtotal más IVA coincida con el total).
4. Si todo cuadra, el documento queda **validado**. Si no, queda en **revisión manual** con el detalle de cada regla que falló.
5. Desde el detalle puedes **aprobar**, **corregir los datos extraídos** o **rechazar** el documento. Las correcciones vuelven a ejecutar las reglas de validación.
6. La bitácora registra cada acción, revisor, comentario y el estado y datos antes y después del cambio.

## Elegir dónde se procesa

Desde el botón ⚙ de la página puedes cambiar, sin reiniciar el servidor:

| Opción | Qué envía | Cuándo usarla |
|---|---|---|
| **Local con Ollama** | Nada sale de tu equipo. | Documentos con datos personales o confidenciales. |
| **Gemini con máscara** (recomendada) | Solo el texto del PDF, con RFC, folio fiscal, correos, teléfonos y nombres o direcciones tras una etiqueta reemplazados por marcadores (`[RFC_1]`). Los valores reales se restauran localmente. | Cuando necesitas la calidad de Gemini y quieres reducir la exposición. |
| **Gemini sin privacidad** | El **PDF completo**. | Solo con documentos no sensibles. La página muestra un aviso con los riesgos y exige aceptarlo antes de guardar. |

Notas:

- La máscara es una **reducción de exposición, no una anonimización**: solo cubre patrones conocidos y los términos de `PRIVACIDAD_TERMINOS`. Un nombre sin etiqueta puede quedar sin enmascarar. Si el texto final conserva algún patrón sensible, **no se envía nada** a Gemini y la extracción falla.
- Con máscara u Ollama el PDF debe tener **texto seleccionable**; no se hace OCR de escaneos.
- Los modelos pequeños de Ollama pueden omitir campos. Para la clave de producto o servicio, si el modelo la deja vacía y el texto trae una clave de 8 dígitos por concepto, se recupera directamente del texto.
- La selección vive en el proceso del servidor: al reiniciar se vuelve a lo que diga `.env`.

## Por qué existe la validación

Un modelo de lenguaje puede equivocarse o "arreglar" datos sin avisar. Por eso el prompt le pide **transcribir exactamente lo impreso**, sin corregir ni calcular, y es el código el que decide si los números son coherentes. Así, una factura con el total mal sumado se detecta en lugar de guardarse como correcta.

## Arquitectura

```mermaid
flowchart LR
    U[Usuario] -->|PDF| W[Página web]
    W -->|POST /documentos| A[API FastAPI]
    A --> D{Ya procesado?<br/>huella SHA-256}
    D -->|sí| R[Devuelve el resultado guardado]
    D -->|no| E[Extractor]
    E -->|local| O[Ollama]
    E -->|nube| P1[Máscara de privacidad] --> G[Gemini API]
    E -->|modo simulado| M[Extracciones guardadas]
    O --> V[Validador de reglas]
    G --> V
    M --> V
    V -->|validado / revisión manual| DB[(PostgreSQL o SQLite)]
    DB --> A
```

## Stack

Python · FastAPI · Pydantic · Ollama · Gemini API (`google-genai`) · pypdf · SQLAlchemy · PostgreSQL (Docker) o SQLite · Bootstrap 5 · Pytest

## Estructura del proyecto

```
app/
  api.py            endpoints de FastAPI
  extractor.py      extracción con Gemini y con Ollama
  privacidad.py     enmascarado de datos personales antes de enviar a Gemini
  configuracion.py  cambio de proveedor, modelo y privacidad en caliente
  schemas.py        esquema de la factura (Pydantic)
  validators.py     reglas de validación
  servicio.py       modo real / modo simulado
  models.py, db.py  modelos relacionales y conexión a base de datos
  persistencia.py  sincronización de columnas/conceptos y migración de documentos existentes
  comparacion.py    comparación de resultados para la evaluación
static/             página web (index.html, styles.css, app.js)
scripts/            generar facturas de prueba, evaluar y utilidades
tests/              pruebas automáticas
resultados/         reporte de evaluación y extracciones guardadas
docker-compose.yml  PostgreSQL local para desarrollo
```

## Cómo ejecutarlo

Requisitos: Python 3.10 o superior y Git. Docker y Ollama son opcionales.

```bash
git clone https://github.com/TU_USUARIO/procesador-documentos-ia.git
cd procesador-documentos-ia
python -m venv .venv
```

Activa el entorno: `.venv\Scripts\Activate.ps1` en Windows (PowerShell) o `source .venv/bin/activate` en Linux y macOS. Después:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.api:app --reload
```

Crea un archivo `.env` en la raíz con las variables que necesites (ver tabla más abajo). Abre <http://127.0.0.1:8000> para la página, o <http://127.0.0.1:8000/docs> para la documentación interactiva de la API.

### Modo simulado (por defecto)

Con `EXTRACTOR_MODO=mock` el programa **no llama a ningún modelo**: lee extracciones ya guardadas en `resultados/extracciones/<modelo>/`. Sirve para desarrollar sin gastar cuota ni necesitar una clave. Solo funciona con archivos cuyo nombre coincida con una extracción guardada.

### Modo real con Ollama (local)

1. Instala [Ollama](https://ollama.com/download) y descarga un modelo, por ejemplo `ollama pull llama3.2:3b` (ligero) o `ollama pull llama3.1:8b` (más preciso, pero más lento).
2. En `.env`:
   ```dotenv
   EXTRACTOR_MODO=real
   LLM_PROVEEDOR=ollama
   OLLAMA_MODEL=llama3.2:3b
   OLLAMA_NUM_CTX=4096
   ```
3. Reinicia el servidor y sube un PDF. La primera respuesta puede tardar varios minutos en equipos sin GPU; el límite de espera es de 5 minutos.

Si los modelos se descargan en una unidad con poco espacio, define `OLLAMA_MODELS` (variable de Windows para el programa Ollama, no para esta app) con otra carpeta y reinicia Ollama.

### Modo real con Gemini

1. Genera una clave en Google AI Studio y ponla en `.env` (nunca en el código).
2. En `.env`:
   ```dotenv
   EXTRACTOR_MODO=real
   LLM_PROVEEDOR=gemini
   GEMINI_API_KEY=tu_clave
   GEMINI_MODEL=gemini-3.8-flash
   GEMINI_ENTRADA=mascara
   ```
3. Reinicia el servidor y sube un PDF.

### Variables de entorno

| Variable | Descripción |
|---|---|
| `EXTRACTOR_MODO` | `mock` (por defecto) o `real`. |
| `LLM_PROVEEDOR` | `gemini` (por defecto) u `ollama`. |
| `GEMINI_API_KEY` | Clave de la API de Gemini. |
| `GEMINI_MODEL` | Modelo de Gemini. En modo simulado debe coincidir con la carpeta de `resultados/extracciones/`. |
| `GEMINI_MODELOS` | Opcional. Lista separada por comas de respaldo si no se puede consultar la API de Gemini. Cuando la API responde, la página muestra hasta 10 modelos compatibles con `generateContent`. |
| `GEMINI_ENTRADA` | `pdf` (envía el PDF completo, por defecto), `texto` (envía el texto sin enmascarar) o `mascara` (envía el texto enmascarado). |
| `PRIVACIDAD_TERMINOS` | Opcional. Términos adicionales a enmascarar, separados por `;`. |
| `OLLAMA_MODEL` | Modelo de Ollama (por defecto `llama3.1:8b`). |
| `OLLAMA_URL` | Dirección de Ollama (por defecto `http://127.0.0.1:11434`). |
| `OLLAMA_NUM_CTX` | Tamaño de contexto de Ollama (por defecto `8192`). |
| `DATABASE_URL` | Opcional. Si no se define, usa SQLite (`documentos.db`). |

### PostgreSQL con Docker (opcional)

```bash
docker compose up -d
```

y en `.env`, con la cadena de conexión que corresponda a `docker-compose.yml`:

```
DATABASE_URL=postgresql+psycopg://USUARIO:CLAVE@127.0.0.1:5433/documentos
```

Las credenciales de `docker-compose.yml` son solo para desarrollo local; el contenedor escucha únicamente en `127.0.0.1`.

## Qué se extrae

- **Comprobante:** folio fiscal (UUID), serie, folio, tipo, fecha de emisión, lugar de expedición, moneda, forma y método de pago, exportación.
- **Emisor y receptor:** nombre, RFC, régimen fiscal, código postal y uso de CFDI (del receptor).
- **Importes:** subtotal, IVA (puede no existir) y total.
- **Conceptos:** descripción, cantidad, importe, clave de producto o servicio, unidad, valor unitario, descuento y objeto de impuesto.

Los campos específicos del CFDI son opcionales: si un documento no los trae, se guardan como vacíos.
No se extraen sellos digitales, cadena original ni datos del certificado.

## Reglas de validación

| Regla | Qué comprueba |
|---|---|
| `campo_faltante` | Existen emisor, RFC del emisor, fecha, subtotal, total y al menos un concepto. |
| `rfc_invalido` / `rfc_receptor_invalido` | El RFC tiene un formato válido. |
| `folio_fiscal_invalido` | El folio fiscal tiene formato de UUID. |
| `fecha_invalida` / `fecha_futura` | La fecha existe y no es posterior a hoy. |
| `concepto_importe_incoherente` | Cantidad por valor unitario coincide con el importe del concepto. |
| `subtotal_no_coincide_conceptos` | La suma de los conceptos coincide con el subtotal. |
| `iva_incoherente` | Si hay IVA, equivale al 16 % de la base (subtotal menos descuentos). |
| `total_no_coincide` | El total coincide con la base más el IVA. |

Las diferencias de centavos se toleran. Una factura sin IVA (por ejemplo, honorarios o conceptos "no objeto de impuesto") es válida si el total coincide con el subtotal.

## API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/documentos` | Sube un PDF (máximo 5 MB). Devuelve `201` si es nuevo y `200` si ya estaba procesado. |
| `GET` | `/documentos` | Lista documentos. Parámetros: `estado`, `busqueda`, `limite`, `desplazamiento`. La búsqueda usa columnas de archivo, emisor, RFC, folio, fecha y total, además de la descripción de conceptos. |
| `GET` | `/documentos/{id}` | Detalle de un documento. |
| `POST` | `/documentos/{id}/aprobar` | Aprueba manualmente. Acepta `revisor` y `comentario` opcionales. |
| `PUT` | `/documentos/{id}/corregir` | Corrige `datos` (JSON de factura), vuelve a validar y registra el cambio. |
| `POST` | `/documentos/{id}/rechazar` | Rechaza; requiere `motivo` y acepta `revisor`. |
| `GET` | `/documentos/{id}/bitacora` | Historial de revisiones con snapshots de datos y estado. |
| `DELETE` | `/documentos/{id}` | Elimina un documento. |
| `POST` | `/documentos/{id}/revalidar` | Vuelve a aplicar las reglas de validación a los datos guardados. |
| `GET` | `/info` | Modo y modelo en uso. |
| `GET` | `/config` | Proveedor, modelo y privacidad actuales, con los modelos disponibles. |
| `PUT` | `/config` | Cambia proveedor, modelo y privacidad. Enviar el PDF completo a Gemini exige `acepta_riesgo: true`. |

Errores: `400` si el archivo no es un PDF o la configuración no es válida, `413` si supera el tamaño, `502` si falla la extracción y `422` si el filtro de estado no es válido.

## Evaluación

Se midió con facturas sintéticas generadas con `scripts/generar_facturas.py`: tres diseños, tres formatos de fecha y de uno a cinco conceptos. Cada una tiene un archivo con la respuesta correcta. Los PDF generados no se incluyen en el repositorio.

**Resultado con Gemini (27 de octubre de 2026, modelo `gemini-3.8-flash`):**

| Medición | Resultado |
|---|---|
| Facturas evaluadas | 11 (7 correctas y 4 con errores intencionales) |
| Campos principales extraídos correctamente | 77 de 77 |
| Errores intencionales detectados con el motivo correcto | 4 de 4 |
| Falsos positivos (facturas correctas enviadas a revisión) | 0 |

Los errores intencionales son: total mal sumado, RFC inválido, conceptos que no suman el subtotal y fecha futura. El reporte está en `resultados/`.

**Cómo leer este resultado:**

- Es una **muestra pequeña de documentos limpios** generados por código. No demuestra que funcione con escaneos, fotos o facturas reales de formato libre.
- **No se ha evaluado de forma sistemática** el modo con Ollama, el enmascarado ni los campos adicionales del CFDI; se probaron a mano con un CFDI real, que no se incluye en el repositorio.
- Para reproducirla hace falta una clave de Gemini y las facturas generadas: `python scripts/generar_facturas.py` y luego `python scripts/evaluar.py`.

## Pruebas automáticas

```bash
python -m pytest -v
```

Cubren las reglas de validación, el enmascarado de privacidad, el extractor con Gemini y los endpoints de la API y de configuración. No usan Gemini, Ollama ni internet: la API se prueba con una base de datos temporal y clientes simulados.

## Decisiones de diseño

- **Salida estructurada con esquema:** el modelo responde con la estructura de `schemas.py`, y la respuesta se vuelve a validar con Pydantic.
- **Transcribir, no corregir:** el prompt prohíbe calcular o completar datos; la coherencia la verifica el código.
- **Nulos permitidos:** si un dato no aparece, el modelo devuelve vacío en lugar de inventarlo.
- **Deduplicación por huella SHA-256:** subir el mismo PDF dos veces devuelve el resultado guardado sin volver a llamar al modelo.
- **Privacidad que falla en seguro:** si tras enmascarar queda algún dato sensible, no se envía nada a Gemini.
- **Modo simulado por defecto:** evita gastar cuota por accidente.
- **Configuración persistente:** el proveedor, modelo y modo de privacidad seleccionados se guardan en la base de datos y se restauran al iniciar. Las claves de API nunca se guardan allí.
- **Datos y conceptos:** los datos completos también se mantienen como JSON para compatibilidad con la API y la bitácora; emisor, RFC, fecha, total y folios se guardan en columnas dedicadas, y cada concepto se almacena como fila independiente. La búsqueda de la lista consulta estos campos y las descripciones de conceptos directamente en la base de datos. Al iniciar, las columnas y conceptos se completan para documentos ya existentes.
- **Seguridad básica:** la página inserta el texto del PDF con `textContent` (nunca como HTML), la API limita el tamaño y comprueba que el archivo sea un PDF, y las claves viven solo en `.env`.

## Limitaciones

- **Sin evaluación con documentos reales ni escaneados.** El modo local no hace OCR.
- **Calidad del modelo local:** los modelos pequeños de Ollama son más lentos en equipos sin GPU y pueden cometer errores (por ejemplo, confundir cantidad y valor unitario). Las reglas de validación no detectan todos los casos.
- **IVA:** solo se valida la tasa del 16 %. No hay manejo de otras tasas ni de retenciones.
- **Moneda:** la interfaz muestra los importes con formato de pesos mexicanos aunque la factura venga en otra moneda.
- **Sin autenticación ni permisos.** Pensado para ejecutarse en local; `PUT /config`, los endpoints de revisión y la bitácora no verifican identidad. El campo `revisor` es informativo y no debe considerarse una firma o atribución confiable.
- **Privacidad con Gemini:** el modo sin máscara envía el PDF completo, y la máscara no es infalible. En el plan gratuito, Google puede usar los datos enviados para mejorar sus productos (revisa los términos vigentes). No subas documentos reales o confidenciales a Gemini; usa Ollama.
- **Cuota:** el plan gratuito de Gemini limita las solicitudes por minuto y por día, y los modelos disponibles cambian con el tiempo.
- **CFDI:** para facturas electrónicas mexicanas, el archivo XML contiene los datos de forma estructurada y es más confiable que leer el PDF. Este proyecto está pensado para documentos sin formato estructurado.

## Próximos pasos

- Evaluación del modo local y del enmascarado con documentos más difíciles (escaneos, rotados, sin RFC, con IVA en 0 %).
- Otros tipos de documento.
