<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:4285F4,100:34A853&height=200&section=header&text=Zero-Asist&fontSize=70&fontColor=ffffff&fontAlignY=38&desc=Asistente%20inteligente%20de%20gestión%20documental%20financiera&descAlignY=58&descSize=18&animation=fadeIn" width="100%"/>

<!-- Badges dinámicos de estado del repositorio -->
[![CI](https://img.shields.io/github/actions/workflow/status/MMARTID/Zero-Asist/main.yml?branch=dev&style=for-the-badge&label=CI%20Pipeline&logo=github-actions&logoColor=white&color=2ea44f)](https://github.com/MMARTID/Zero-Asist/actions)
[![Last Commit](https://img.shields.io/github/last-commit/MMARTID/Zero-Asist/dev?style=for-the-badge&logo=git&logoColor=white&color=F05032&label=Último%20commit)](https://github.com/MMARTID/Zero-Asist/commits/dev)
[![Issues](https://img.shields.io/github/issues/MMARTID/Zero-Asist?style=for-the-badge&logo=github&logoColor=white&color=e4e669&label=Issues)](https://github.com/MMARTID/Zero-Asist/issues)
[![Stars](https://img.shields.io/github/stars/MMARTID/Zero-Asist?style=for-the-badge&logo=github&logoColor=white&color=gold&label=Stars)](https://github.com/MMARTID/Zero-Asist/stargazers)

<br/>

<!-- Stack tecnológico -->
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/)
[![Firestore](https://img.shields.io/badge/Cloud_Firestore-FFCA28?style=flat-square&logo=firebase&logoColor=black)](https://firebase.google.com/docs/firestore)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![pytest](https://img.shields.io/badge/pytest-97%20tests-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)

<br/>

> 🚀 **Zero-Asist** automatiza la captura, extracción y clasificación de documentos financieros —facturas, extractos bancarios, nóminas y más— directamente desde Gmail y mediante subida directa, almacenándolos estructurados en Google Cloud Firestore con **inteligencia artificial**.

<br/>

[🚀 Inicio rápido](#-inicio-rápido) · [📖 API Reference](#-api-reference) · [🏗️ Arquitectura](#️-arquitectura) · [🧪 Tests](#-tests) · [🐳 Docker](#-docker)

</div>

---

## 📋 Tabla de contenidos

- [✨ Características principales](#-características-principales)
- [🏗️ Arquitectura](#️-arquitectura)
- [📁 Estructura del proyecto](#-estructura-del-proyecto)
- [📄 Tipos de documento soportados](#-tipos-de-documento-soportados)
- [🚀 Inicio rápido](#-inicio-rápido)
- [🔌 API Reference](#-api-reference)
- [🔐 Seguridad del scheduler](#-seguridad-del-scheduler)
- [🐳 Docker](#-docker)
- [☁️ Despliegue en Google Cloud Run](#️-despliegue-en-google-cloud-run)
- [🧪 Tests](#-tests)
- [🛠️ Stack tecnológico](#️-stack-tecnológico)
- [🔄 Flujo de procesamiento](#-flujo-de-procesamiento-de-documentos)
- [📜 Licencia](#-licencia)

---

## ✨ Características principales

<div align="center">

| | Funcionalidad | Descripción |
|:---:|:---|:---|
| 🤖 | **Extracción con IA** | Usa Gemini 2.5 Flash para identificar y extraer automáticamente campos de documentos financieros |
| 📧 | **Integración Gmail** | Monitoriza tu bandeja de entrada y procesa adjuntos relevantes de forma automática |
| 🔒 | **Sin duplicados** | Deduplicación mediante hash SHA-256 con verificación previa a cualquier llamada a la IA |
| 🗃️ | **Persistencia estructurada** | Almacena todos los documentos normalizados en Google Cloud Firestore |
| 📄 | **10 tipos de documento** | Facturas, recibos, extractos bancarios, nóminas, SS, albaranes, contratos y más |
| 🚀 | **Listo para producción** | Desplegable en Google Cloud Run con autenticación OIDC para llamadas programadas |
| 🧪 | **Altamente testeado** | Suite de **97 tests** con pytest cubriendo todos los módulos críticos |
| ⚡ | **Filtrado de 3 capas** | Sistema progresivo que minimiza costes de la API de Gemini |

</div>

---

## 🏗️ Arquitectura

<details open>
<summary><strong>📐 Diagrama completo del sistema</strong></summary>

<br/>

```
┌──────────────────────────────────────────────────────────────────┐
│                         Zero-Asist API                           │
│                        (FastAPI · Cloud Run)                     │
└───────────────────────┬──────────────────┬───────────────────────┘
                        │                  │
           POST /procesar-documento   POST /poll-gmail
                        │                  │
              ┌─────────▼──────┐   ┌───────▼──────────┐
              │  Subida manual │   │   Gmail Poller    │
              │  (PDF/JPG/PNG/ │   │                   │
              │   XML)         │   │ ┌ Capa 1 ─────┐  │
              └─────────┬──────┘   │ │ Gmail Query │  │
                        │          │ └──────┬──────┘  │
                        │          │ ┌ Capa 2 ─────┐  │
                        │          │ │  Heurística │  │
                        │          │ │  local      │  │
                        │          │ └──────┬──────┘  │
                        │          │ ┌ Capa 3 ─────┐  │
                        │          │ │  Adjuntos   │  │
                        │          │ │  válidos    │  │
                        │          │ └──────┬──────┘  │
                        │          └────────┼─────────┘
                        │                   │
              ┌──────────▼───────────────────▼──────────┐
              │         Document Processor               │
              │                                          │
              │  1. SHA-256 hash                         │
              │  2. ¿Duplicado en Firestore? ──► skip    │
              │  3. Gemini 2.5 Flash (extracción)        │
              │  4. Normalización + conversión fechas    │
              │  5. Guardado transaccional (Firestore)   │
              └──────────────────────────────────────────┘
                         │                 │
              ┌───────────▼──┐   ┌──────────▼────────┐
              │   Gemini AI   │   │  Cloud Firestore  │
              │  (extracción) │   │  (documentos +    │
              └───────────────┘   │   gmail_processed)│
                                  └───────────────────┘
```

</details>

<details>
<summary><strong>📬 Filtrado de Gmail en tres capas</strong></summary>

<br/>

> El poller de Gmail aplica un sistema de filtrado progresivo que **minimiza el consumo de la API de Gemini**:

```
📥 Bandeja de entrada Gmail
        │
        ▼ Capa 1 — Gmail Query (gratis)
   has:attachment (filename:pdf OR filename:xml ...)
        │
        ▼ Capa 2 — Heurística local (sin LLM, gratis)
   keywords: factura, invoice, recibo, albarán, IVA ...
        │
        ▼ Capa 3 — Adjuntos válidos (MIME permitido)
   PDF · JPEG · PNG · XML
        │
        ▼ Solo aquí se llama a Gemini 💰
```

</details>

---

## 📁 Estructura del proyecto

<details>
<summary><strong>🗂️ Ver estructura completa</strong></summary>

<br/>

```
Zero-Asist/
├── app/
│   ├── main.py                    # FastAPI: endpoints /procesar-documento y /poll-gmail
│   ├── collectors/
│   │   ├── gmail_service.py       # Autenticación OAuth2 e inicialización del servicio Gmail
│   │   ├── gmail_reader.py        # Filtros Capa 1 y 2 + descarga de adjuntos
│   │   └── gmail_poller.py        # Orquestador principal del flujo Gmail
│   ├── ingestion/
│   │   └── normalizer.py          # Normalización y validación de datos extraídos
│   ├── models/
│   │   └── document.py            # Modelos Pydantic: tipos de documento y schemas
│   └── services/
│       ├── document_processor.py  # Pipeline central: hash → dedup → Gemini → Firestore
│       ├── gemini_client.py       # Cliente de Google Gemini 2.5 Flash
│       └── firestore_client.py    # Cliente de Cloud Firestore
├── test/
│   ├── conftest.py
│   ├── test_main.py
│   ├── test_document_processor.py
│   ├── test_gmail_poller.py
│   ├── test_gmail_reader.py
│   ├── test_gemini_client.py
│   └── test_normalizer.py
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── .github/
    └── workflows/
        └── main.yml               # CI: lint + format + test
```

</details>

---

## 📄 Tipos de documento soportados

<div align="center">

| Tipo (`document_type`) | Descripción |
|:---|:---|
| `invoice_received` | 📥 Factura recibida de proveedor |
| `invoice_issued` | 📤 Factura emitida a cliente |
| `receipt` | 🧾 Recibo de pago |
| `bank_statement` | 🏦 Extracto bancario |
| `payroll` | 💼 Nómina |
| `social_security_form` | 🛡️ Documento de Seguridad Social |
| `delivery_note` | 📦 Albarán de entrega |
| `contract` | 📋 Contrato |
| `tax_authority_communication` | 🏛️ Comunicación de la Agencia Tributaria |
| `other` | 📁 Cualquier otro documento |

</div>

---

## 🚀 Inicio rápido

### Prerrequisitos

- ![Python](https://img.shields.io/badge/-Python_3.11+-3776AB?style=flat-square&logo=python&logoColor=white) Python 3.11+
- ![GCP](https://img.shields.io/badge/-Google_Cloud-4285F4?style=flat-square&logo=googlecloud&logoColor=white) Cuenta de Google Cloud con Firestore habilitado
- ![Gemini](https://img.shields.io/badge/-Gemini_API_Key-4285F4?style=flat-square&logo=google&logoColor=white) Credenciales de la API de Gemini
- ![Gmail](https://img.shields.io/badge/-Gmail_OAuth2-EA4335?style=flat-square&logo=gmail&logoColor=white) *(Opcional)* Credenciales OAuth2 de Gmail para el poller

### 1. Clona el repositorio

```bash
git clone https://github.com/MMARTID/Zero-Asist.git
cd Zero-Asist
```

### 2. Instala las dependencias

```bash
pip install -r requirements.txt
```

### 3. Configura las variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# ── Google Gemini ───────────────────────────────────────────────
GEMINI_API_KEY=tu_api_key_de_gemini

# ── Google Cloud (Firestore) ────────────────────────────────────
# En Cloud Run se usa la cuenta de servicio por defecto.
# En local, apunta al fichero de credenciales:
GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/credenciales.json

# ── Gmail OAuth2 ────────────────────────────────────────────────
GMAIL_CREDENTIALS_PATH=/ruta/a/gmail_credentials.json
GMAIL_TOKEN_PATH=/ruta/a/gmail_token.json

# ── Autenticación del scheduler ─────────────────────────────────
# Para desarrollo local (token fijo):
SCHEDULER_DEV_TOKEN=mi_token_secreto_local

# Para producción con Cloud Scheduler (OIDC):
SCHEDULER_AUDIENCE=https://tu-servicio.run.app
```

### 4. Arranca el servidor

```bash
uvicorn app.main:app --reload --port 8080
```

> 🌐 La API estará disponible en `http://localhost:8080`  
> 📚 Documentación interactiva en `http://localhost:8080/docs`

---

## 🔌 API Reference

### `POST /procesar-documento`

Procesa un documento financiero subido directamente.

**Request** — `multipart/form-data`:

| Campo | Tipo | Requerido | Descripción |
|:---|:---|:---:|:---|
| `file` | `UploadFile` | ✅ | Documento a procesar (PDF, JPG, PNG, XML) |

> **Tipos MIME aceptados:** `application/pdf` · `image/jpeg` · `image/jpg` · `image/png` · `application/xml` · `text/xml`

<details>
<summary><strong>📗 Response 200 OK</strong></summary>

```json
{
  "documento_id": "a3f2c1d4e5b6...",
  "document_type": "invoice_received",
  "normalized_data": {
    "issuer_name": "Empresa Proveedora S.L.",
    "issuer_tax_id": "B12345678",
    "invoice_number": "F2024-0042",
    "issue_date": "2024-03-15",
    "total_amount": 1210.00,
    "currency": "EUR"
  }
}
```

</details>

<details>
<summary><strong>📕 Códigos de error</strong></summary>

| Código | Causa |
|:---:|:---|
| `400` | Archivo vacío, MIME no soportado o extensión desconocida |
| `409` | Documento duplicado (ya existe en Firestore) |
| `500` | Error interno en la extracción con Gemini |

</details>

---

### `POST /poll-gmail`

Dispara la consulta de Gmail y procesa los adjuntos pendientes. Requiere autenticación.

**Headers de autenticación** *(uno de los dos)*:

```http
X-Scheduler-Token: <SCHEDULER_DEV_TOKEN>   # desarrollo local
Authorization: Bearer <OIDC_TOKEN>          # producción (Cloud Scheduler)
```

<details>
<summary><strong>📗 Response 200 OK</strong></summary>

```json
{
  "procesados": 3,
  "duplicados": 1,
  "errores": 0,
  "descartados": 5,
  "documentos": [...],
  "detalle_duplicados": [...],
  "detalle_errores": []
}
```

</details>

---

## 🔐 Seguridad del scheduler

El endpoint `/poll-gmail` utiliza una dependencia FastAPI que verifica la autenticidad de la llamada en dos modos:

```
Llamada entrante
      │
      ├─ X-Scheduler-Token header?
      │       └─ ¿Coincide con SCHEDULER_DEV_TOKEN? → ✅ permitido (desarrollo)
      │
      └─ Authorization: Bearer <token>?
              └─ Validación OIDC con google-auth → ✅ permitido (producción)

Cualquier otro caso → ❌ 401 Unauthorized
```

---

## 🐳 Docker

```bash
# Construir la imagen
docker build -t zero-asist .

# Ejecutar localmente
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=tu_api_key \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  -v /ruta/local/credentials.json:/app/credentials.json \
  zero-asist
```

---

## ☁️ Despliegue en Google Cloud Run

```bash
# 1. Autenticarse con gcloud
gcloud auth login

# 2. Construir y subir la imagen a Artifact Registry
gcloud builds submit --tag gcr.io/TU_PROYECTO/zero-asist

# 3. Desplegar en Cloud Run
gcloud run deploy zero-asist \
  --image gcr.io/TU_PROYECTO/zero-asist \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=tu_api_key,SCHEDULER_AUDIENCE=https://zero-asist-xxx.run.app
```

> 💡 **Tip:** En Cloud Run, Firestore usa automáticamente la cuenta de servicio asociada al servicio. No necesitas configurar `GOOGLE_APPLICATION_CREDENTIALS`.

---

## 🧪 Tests

```bash
# Ejecutar todos los tests
pytest

# Con output detallado
pytest -v

# Solo un módulo específico
pytest test/test_document_processor.py -v
```

La suite incluye **97 tests** distribuidos en 6 módulos:

<div align="center">

| Módulo de test | Qué cubre |
|:---|:---|
| `test_main.py` | Endpoints FastAPI, validaciones HTTP, autenticación |
| `test_document_processor.py` | Pipeline central: hash, dedup, extracción, guardado |
| `test_gmail_poller.py` | Orquestación del flujo Gmail extremo a extremo |
| `test_gmail_reader.py` | Filtros de candidatos y descarga de adjuntos |
| `test_gemini_client.py` | Cliente de Gemini y parsing de respuestas |
| `test_normalizer.py` | Normalización, validación y conversión de fechas |

</div>

---

## 🛠️ Stack tecnológico

<div align="center">

| Capa | Tecnología |
|:---:|:---|
| **API** | [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/) + [![Uvicorn](https://img.shields.io/badge/Uvicorn-494949?style=flat-square&logo=gunicorn&logoColor=white)](https://www.uvicorn.org/) |
| **IA / LLM** | [![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev/) |
| **Base de datos** | [![Firestore](https://img.shields.io/badge/Cloud_Firestore-FFCA28?style=flat-square&logo=firebase&logoColor=black)](https://firebase.google.com/docs/firestore) |
| **Email** | [![Gmail API](https://img.shields.io/badge/Gmail_API-EA4335?style=flat-square&logo=gmail&logoColor=white)](https://developers.google.com/gmail/api) |
| **Modelos de datos** | [![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/) |
| **Autenticación** | [![google-auth](https://img.shields.io/badge/google--auth_OIDC-4285F4?style=flat-square&logo=google&logoColor=white)](https://google-auth.readthedocs.io/) |
| **Infraestructura** | [![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/) + [![Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/run) |
| **Testing** | [![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/) |
| **Linting / Formato** | [![flake8](https://img.shields.io/badge/flake8-3776AB?style=flat-square&logo=python&logoColor=white)](https://flake8.pycqa.org/) + [![black](https://img.shields.io/badge/black-000000?style=flat-square&logo=python&logoColor=white)](https://black.readthedocs.io/) |
| **CI/CD** | [![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white)](https://github.com/features/actions) |

</div>

---

## 🔄 Flujo de procesamiento de documentos

<details open>
<summary><strong>📊 Ver flujo completo</strong></summary>

<br/>

```
Documento (bytes)
      │
      ▼
┌─────────────────┐
│  Validar MIME   │ ← PDF, JPEG, PNG, XML
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SHA-256 hash   │ ← ID único del documento
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│ ¿Existe en Firestore?       │
│  (documentos/{hash})        │──── SÍ ──► 409 Duplicate
└────────┬────────────────────┘
         │ NO
         ▼
┌─────────────────────────────┐
│  Gemini 2.5 Flash           │
│  · Clasifica tipo documento │
│  · Extrae campos            │
│  · Responde en JSON         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Normalización              │
│  · Limpieza de datos        │
│  · Conversión de fechas     │
│  · Validación de campos     │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Guardado transaccional     │ ← Race condition safe
│  en Firestore               │
└────────┬────────────────────┘
         │
         ▼
    ✅ ProcessingResult
    { status, doc_hash,
      document_type,
      normalized_data }
```

</details>

---

## 📜 Licencia

Este proyecto está bajo la licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:34A853,100:4285F4&height=120&section=footer" width="100%"/>

**¿Te ha sido útil?** ⭐ Dale una estrella al repositorio

[![GitHub Stars](https://img.shields.io/github/stars/MMARTID/Zero-Asist?style=social)](https://github.com/MMARTID/Zero-Asist/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/MMARTID/Zero-Asist?style=social)](https://github.com/MMARTID/Zero-Asist/network/members)

<br/>

Hecho con ❤️ &nbsp;·&nbsp;
[🐛 Reportar un bug](https://github.com/MMARTID/Zero-Asist/issues/new?labels=bug) &nbsp;·&nbsp;
[💡 Solicitar una función](https://github.com/MMARTID/Zero-Asist/issues/new?labels=enhancement) &nbsp;·&nbsp;
[📖 Documentación](https://github.com/MMARTID/Zero-Asist#-tabla-de-contenidos)

</div>
