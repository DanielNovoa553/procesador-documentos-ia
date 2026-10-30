# Procesador inteligente de documentos

API y aplicación web en Python que recibe **facturas en PDF**, extrae sus datos en formato estructurado con la **API de Gemini**, los **valida con reglas de negocio** y guarda el resultado en una base de datos. Los documentos con datos inconsistentes no se aceptan en silencio: quedan marcados para **revisión manual**, con el motivo.

![Lista de documentos](docs/img/lista.png)

> **Proyecto de portafolio.** Usa documentos sintéticos (inventados). No es un sistema listo para producción; las limitaciones están descritas más abajo.

## Qué hace

1. Subes una factura en PDF (por la página web o por la API).
2. Gemini lee el documento y devuelve los datos con un esquema fijo (salida estructurada en JSON): emisor, receptor, folio fiscal, montos, conceptos y más.
3. El sistema valida los datos con reglas propias (por ejemplo, que subtotal más IVA coincida con el total).
4. Si todo cuadra, el documento queda **validado**. Si no, queda en **revisión manual** con el detalle de cada regla que falló.
5. Consultas la lista, filtras por estado y abres el detalle de cada documento.

![Detalle de un documento](docs/img/detalle.png)

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
    E -->|modo real| G[Gemini API]
    E -->|modo simulado| M[Extracciones guardadas]
    G --> V[Validador de reglas]
    M --> V
    V -->|validado / revisión manual| P[(PostgreSQL o SQLite)]
    P --> A
```

## Stack

Python · FastAPI · Pydantic · Gemini API (`google-genai`) · SQLAlchemy · PostgreSQL (Docker) o SQLite · Bootstrap 5 · Pytest

## Estructura del proyecto

```
app/
  api.py           endpoints de FastAPI
  extractor.py     llamada a Gemini y manejo de errores
  schemas.py       esquema de la factura (Pydantic)
  validators.py    reglas de validación
  servicio.py      modo real / modo simulado
  models.py, db.py base de datos
  comparacion.py   comparación de resultados para la evaluación
static/            página web (index.html, styles.css, app.js)
scripts/           generar facturas de prueba, evaluar, utilidades
tests/             pruebas automáticas (22)
data/facturas/     facturas de prueba sintéticas y sus respuestas correctas
resultados/        reportes de evaluación y extracciones guardadas
docker-compose.yml PostgreSQL local para desarrollo
```

## Cómo ejecutarlo

Requisitos: Python 3.10 o superior y Git. Docker es opcional.

```bash
git clone https://github.com/TU_USUARIO/procesador-documentos-ia.git
cd procesador-documentos-ia
python -m venv .venv
```

Activa el entorno: `.venv\Scripts\Activate.ps1` en Windows (PowerShell) o `source .venv/bin/activate` en Linux y macOS. Después:

```bash
python -m pip install -r requirements.txt
cp .env.example .env        # en Windows: copy .env.example .env
python -m uvicorn app.api:app --reload
```

Abre <http://127.0.0.1:8000> para la página, o <http://127.0.0.1:8000/docs> para la documentación interactiva de la API.

### Modo simulado (por defecto)

Con `EXTRACTOR_MODO=mock` el programa **no llama a Gemini**: lee extracciones ya guardadas en `resultados/extracciones/<modelo>/`. Sirve para desarrollar y probar sin gastar cuota ni necesitar una clave. Solo funciona con las facturas de `data/facturas/` que tienen una extracción guardada (`factura_001`, `003`, `004`, `005`, `006`, `007`, `009`, `012`, `013`, `016` y `020`).

### Modo real

1. Genera una clave en Google AI Studio y ponla en tu archivo `.env` (nunca en el código).
2. Cambia `EXTRACTOR_MODO=real` y reinicia el servidor.
3. Sube un PDF: se envía a la API de Gemini.

### Variables de entorno

| Variable | Descripción |
|---|---|
| `GEMINI_API_KEY` | Clave de la API de Gemini (solo en modo real). |
| `GEMINI_MODEL` | Modelo a usar. Debe coincidir con la carpeta de `resultados/extracciones/` en modo simulado. |
| `EXTRACTOR_MODO` | `mock` (por defecto) o `real`. |
| `DATABASE_URL` | Opcional. Si no se define, usa SQLite (`documentos.db`). |

### PostgreSQL con Docker (opcional)

```bash
docker compose up -d
```

y en `.env`:

```
DATABASE_URL=postgresql+psycopg://docs:docs@127.0.0.1:5433/documentos
```

Las credenciales `docs/docs` son solo para desarrollo local; el contenedor escucha únicamente en `127.0.0.1`.

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
| `GET` | `/documentos` | Lista documentos. Parámetros: `estado`, `limite`, `desplazamiento`. |
| `GET` | `/documentos/{id}` | Detalle de un documento. |
| `DELETE` | `/documentos/{id}` | Elimina un documento. |
| `GET` | `/info` | Modo y modelo en uso. |

Errores: `400` si el archivo no es un PDF, `413` si supera el tamaño, `502` si falla la extracción y `422` si el filtro de estado no es válido.

## Evaluación

Se midió con las facturas sintéticas de `data/facturas/`, generadas con `scripts/generar_facturas.py`: tres diseños, tres formatos de fecha y de uno a cinco conceptos. Cada una tiene un archivo con la respuesta correcta.

**Resultado (27 de octubre de 2026, modelo `gemini-3.8-flash`):**

| Medición | Resultado |
|---|---|
| Facturas evaluadas | 11 (7 correctas y 4 con errores intencionales) |
| Campos principales extraídos correctamente | 77 de 77 |
| Errores intencionales detectados con el motivo correcto | 4 de 4 |
| Falsos positivos (facturas correctas enviadas a revisión) | 0 |

Los errores intencionales son: total mal sumado, RFC inválido, conceptos que no suman el subtotal y fecha futura.

**Cómo leer este resultado:**

- Es una **muestra pequeña de documentos limpios** generados por código. No demuestra que funcione con escaneos, fotos o facturas reales de formato libre.
- La evaluación corresponde a los campos principales (emisor, RFC, fecha, montos y conceptos). Los campos adicionales del CFDI y el prompt ampliado **no se han evaluado de forma sistemática**; se probaron a mano con un CFDI real, que no se incluye en el repositorio.
- Para reproducirla hace falta una clave de Gemini: `python scripts/evaluar.py`. El script guarda cada extracción, así que puede reanudarse, y se detiene al alcanzar el límite de cuota.

## Pruebas automáticas

```bash
python -m pytest -v
```

22 pruebas: reglas de validación y endpoints de la API. No usan Gemini ni internet; la API se prueba con una base de datos temporal y una extracción simulada.

## Decisiones de diseño

- **Salida estructurada con esquema:** Gemini responde con la estructura de `schemas.py`, y la respuesta se vuelve a validar con Pydantic.
- **Transcribir, no corregir:** el prompt prohíbe calcular o completar datos; la coherencia la verifica el código.
- **Nulos permitidos:** si un dato no aparece, el modelo devuelve vacío en lugar de inventarlo.
- **Deduplicación por huella SHA-256:** subir el mismo PDF dos veces devuelve el resultado guardado sin volver a llamar a Gemini.
- **Modo simulado por defecto:** evita gastar cuota por accidente.
- **Datos como JSON:** la factura extraída se guarda en una columna JSON. Es práctico en un MVP porque tolera cambios de esquema; en un sistema real los campos de búsqueda (emisor, fecha, total, folio fiscal) serían columnas, con los conceptos en su propia tabla.
- **Seguridad básica:** la página inserta el texto del PDF con `textContent` (nunca como HTML), la API limita el tamaño y comprueba que el archivo sea un PDF, y las claves viven solo en `.env`.

## Limitaciones

- **Datos sintéticos.** No se ha evaluado con documentos reales ni escaneados.
- **IVA:** solo se valida la tasa del 16 %. No hay manejo de otras tasas ni de retenciones.
- **Moneda:** la interfaz muestra los importes con formato de pesos mexicanos aunque la factura venga en otra moneda.
- **Sin autenticación ni permisos.** Pensado para ejecutarse en local.
- **La revisión manual solo marca:** todavía no se pueden aprobar ni corregir documentos desde la interfaz.
- **Privacidad:** en modo real el PDF se envía a un servicio externo. En el plan gratuito de Gemini, Google puede usar los datos enviados para mejorar sus productos (revisa los términos vigentes). No subas documentos reales o confidenciales.
- **Cuota:** el plan gratuito limita las solicitudes por minuto y por día, y los modelos disponibles cambian con el tiempo.
- **CFDI:** para facturas electrónicas mexicanas, el archivo XML contiene los datos de forma estructurada y es más confiable que leer el PDF. Este proyecto está pensado para documentos sin formato estructurado.

## Próximos pasos

- Flujo de revisión manual: aprobar, corregir y rechazar, con bitácora de cambios.
- Procesamiento asíncrono en AWS (S3, SQS, Lambda y DynamoDB, con CDK).
- Columnas reales para los campos de búsqueda y tabla de conceptos.
- Evaluación con documentos más difíciles (escaneos, rotados, sin RFC, con IVA en 0 %).
- Otros tipos de documento.

## Datos de prueba

Todas las facturas de `data/facturas/` son ficticias, y cada PDF lo indica al pie. Los RFC, nombres y montos son inventados y no tienen validez fiscal. Las fechas se calculan a partir del día en que se ejecuta el generador, por lo que al regenerarlas cambian.