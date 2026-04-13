<div align="center">

# ⚡ Zero-Asist

### Asistente inteligente de gestión documental financiera

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Gemini AI](https://img.shields.io/badge/Gemini_2.5_Flash-AI-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Firestore](https://img.shields.io/badge/Cloud_Firestore-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)](https://firebase.google.com/docs/firestore)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![pytest](https://img.shields.io/badge/pytest-251_tests-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/MMARTID/Zero-Asist/main.yml?branch=dev&style=for-the-badge&label=CI&logo=github-actions&logoColor=white)](https://github.com/MMARTID/Zero-Asist/actions)

<br/>

> **Zero-Asist** es una plataforma SaaS multi-tenant para gestorías que automatiza la captura, extracción y clasificación de documentos financieros —facturas, extractos bancarios, contratos y más— directamente desde Gmail y mediante subida directa, almacenándolos estructurados en Google Cloud Firestore con inteligencia artificial.

</div>

---

## ✨ Características principales

| Funcionalidad | Descripción |
|---|---|
| 🤖 **Extracción con IA** | Gemini 2.5 Flash clasifica y extrae campos en dos fases; fallback automático a `gemini-2.5-flash-lite` |
| 📧 **Integración Gmail** | Watch API en tiempo real + polling manual; filtrado en 3 capas para minimizar costes de API |
| 🔄 **Reintentos automáticos** | Endpoint `/internal/retry-failed` reprocesa mensajes fallidos sin necesidad de un poll completo |
| 🔒 **Sin duplicados** | Deduplicación SHA-256 antes de cualquier llamada a Gemini |
| 🏢 **Multi-tenant** | Arquitectura gestoría → clientes; cada cliente tiene su colección aislada en Firestore |
| 🗃️ **Persistencia estructurada** | Documentos normalizados con líneas fiscales (IVA, IGIC, IRPF, RE) en Firestore |
| 🖥️ **Dashboard web** | Frontend Next.js 15 + Firebase Auth para gestión de clientes y documentos |
| 🚀 **Cloud-native** | Backend en Cloud Run, frontend en Docker standalone; CI/CD con GitHub Actions |
| 🧪 **Altamente testeado** | 251 tests con pytest cubriendo todos los módulos críticos |

---

## 🏗️ Arquitectura

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js · Firebase Auth)               │
│         Dashboard: clientes, documentos, stats, onboarding Gmail     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ Authorization: Bearer <Firebase ID Token>
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Zero-Asist API (FastAPI · Cloud Run)         │
├────────────┬──────────────┬──────────────┬────────────┬─────────────┤
│ /dashboard │ /onboarding  │  /webhook    │ /internal  │/procesar-   │
│ (Firebase  │  (OAuth2     │  (Pub/Sub    │ (Cloud     │ documento   │
│  Auth)     │   Gmail)     │   JWT)       │ Scheduler) │ /poll-gmail │
└────────────┴──────┬───────┴──────┬───────┴────────────┴──────┬──────┘
                    │              │                             │
         ┌──────────▼──────────────▼─────────────────────────  ▼ ──────┐
         │                    Document Processor                        │
         │  1. SHA-256 hash → ¿Duplicado? → skip                       │
         │  2. Gemini 2.5 Flash: clasificar → extraer (JSON schema)    │
         │  3. Normalizar (fechas, monedas, líneas fiscales)           │
         │  4. Guardar transaccionalmente en Firestore                  │
         └────────────────────┬─────────────────────────────────────────┘
                              │
              ┌───────────────▼────────────────────┐
              │  Cloud Firestore (multi-tenant)     │
              │  gestorias/{g}/clientes/{c}/        │
              │    documentos/        (docs)        │
              │    gmail_processed/  (tracking)     │
              └────────────────────────────────────┘
```

### Filtrado de Gmail en tres capas

El poller aplica un sistema de filtrado progresivo que **minimiza el consumo de la API de Gemini**:

```
📥 Bandeja de entrada Gmail
        │
        ▼ Capa 1 — Gmail Query (gratis)
   has:attachment (filename:pdf OR filename:xml OR filename:jpg ...)
        │
        ▼ Capa 2 — Heurística local (sin LLM, gratis)
   keywords: factura, invoice, recibo, albarán, IVA, nómina ...
        │
        ▼ Capa 3 — Adjuntos válidos (MIME permitido)
   PDF · JPEG · PNG · XML
        │
        ▼ Solo aquí se llama a Gemini 💰
```

---

## 📁 Estructura del proyecto

```
Zero-Asist/                          ← Monorepo
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, routers
│   │   ├── api/
│   │   │   ├── auth.py              # Dependencia Firebase Auth + auto-registro
│   │   │   ├── dashboard.py         # GET /dashboard/clientes|stats|documentos
│   │   │   ├── documents.py         # POST /procesar-documento
│   │   │   ├── gmail.py             # POST /poll-gmail
│   │   │   ├── internal.py          # POST /internal/renew-watches + /retry-failed
│   │   │   ├── onboarding.py        # POST /onboarding/clientes + OAuth2 Gmail
│   │   │   └── webhook.py           # POST /webhook (Pub/Sub JWT)
│   │   ├── collectors/
│   │   │   ├── gmail_service.py     # Autenticación OAuth2 por tenant
│   │   │   ├── gmail_reader.py      # Filtros Capa 1+2 + descarga adjuntos
│   │   │   ├── gmail_poller.py      # Orquestador del flujo Gmail
│   │   │   └── gmail_watch.py       # Gmail Watch API (start/renew/stop)
│   │   ├── ingestion/
│   │   │   ├── normalizer.py        # Orquestador de normalización
│   │   │   ├── invoice.py           # Normalización de facturas
│   │   │   ├── bank_document.py     # Normalización de extractos
│   │   │   ├── helpers.py           # Primitivas: fechas, monedas, impuestos
│   │   │   ├── validation.py        # Validación de coherencia aritmética
│   │   │   └── constants.py         # Regexes, tablas de impuestos, tolerancias
│   │   ├── models/
│   │   │   ├── document.py          # DocumentType enum + schemas Pydantic
│   │   │   └── registry.py          # Registro de tipos (schema + prompts + normalizer)
│   │   └── services/
│   │       ├── document_processor.py# Pipeline: hash → dedup → Gemini → Firestore
│   │       ├── gemini_client.py     # Gemini 2.5 Flash con fallback y reintentos
│   │       ├── firestore_client.py  # Cliente Firestore + transacciones
│   │       ├── credential_store.py  # OAuth tokens por tenant (Firestore)
│   │       ├── tenant.py            # TenantContext: paths de colecciones
│   │       ├── errors.py            # PipelineError con códigos estructurados
│   │       └── constants.py         # Nombres de colecciones
│   ├── tests/                       # 251 tests pytest
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .flake8
│
├── frontend/
│   ├── app/                         # Next.js 15 App Router
│   │   ├── login/                   # Google Sign-In
│   │   └── dashboard/               # Gestión clientes y documentos
│   ├── components/                  # nav.tsx, auth-guard.tsx
│   ├── lib/                         # api.ts, auth-context.tsx, firebase.ts
│   ├── __tests__/                   # Tests frontend (Vitest recomendado)
│   ├── Dockerfile                   # Multi-stage standalone build
│   └── package.json
│
├── .github/workflows/main.yml       # CI: backend (lint+test) + frontend (lint+build)
├── .env.example                     # Template de variables de entorno
├── .gitignore
└── README.md
```

---

## 📄 Tipos de documento soportados

| Tipo (`document_type`) | Descripción | Campos principales extraídos |
|---|---|---|
| `invoice_received` | Factura recibida de proveedor | `issuer_name`, `issuer_nif`, `invoice_number`, `issue_date`, `base_amount`, `total_amount`, `tax_lines`, `currency` |
| `invoice_sent` | Factura emitida a cliente | igual que `invoice_received` + `client_name`, `client_nif`, `payment_status` |
| `payment_receipt` | Justificante o comprobante de pago | `payment_date`, `amount`, `currency`, `payment_method`, `iban`, `issuer_entity` |
| `administrative_notice` | Documento fiscal, tributario o administrativo | `issuer_entity`, `notice_type`, `issue_date`, `deadline`, `expedient_number`, `summary` |
| `bank_document` | Extracto bancario, aviso del banco | `bank_name`, `document_date`, `iban`, `movements[]` (date, description, amount, balance_after) |
| `contract` | Contrato o acuerdo legal | `parties[]` (name, nif), `contract_date`, `subject`, `duration`, `economic_terms`, `signed` |
| `expense_ticket` | Ticket de compra o gasto menor | `issuer_name`, `issue_date`, `base_amount`, `total_amount`, `tax_lines`, `concept` |
| `other` | Cualquier otro documento | sin extracción de campos específicos |

### Líneas fiscales (`tax_lines`)

Las facturas y tickets incluyen un array de líneas fiscales que soporta todos los regímenes españoles:

| `tax_type` | Descripción |
|---|---|
| `iva` | IVA peninsular (4%, 10%, 21%) |
| `igic` | IGIC Canarias (3%, 7%, 15%) |
| `ipsi` | IPSI Ceuta/Melilla |
| `re` | Recargo de equivalencia |
| `irpf` | Retención IRPF |

---

## 🚀 Inicio rápido

### Prerrequisitos

- Python 3.11+ y Node.js 20+
- Proyecto de Google Cloud con Firestore y Gmail API habilitados
- API key de Google Gemini
- Proyecto de Firebase con Authentication habilitado

### 1. Clona el repositorio

```bash
git clone https://github.com/MMARTID/Zero-Asist.git
cd Zero-Asist
```

### 2. Instala las dependencias

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 3. Configura las variables de entorno

```bash
cp .env.example backend/.env
cp .env.example frontend/.env.local
```

Variables del backend (`backend/.env`):

```env
# Google Gemini
GEMINI_API_KEY=

# OAuth2 Gmail (flujo de onboarding)
OAUTH_CLIENT_ID=
OAUTH_CLIENT_SECRET=
OAUTH_REDIRECT_URI=http://localhost:8000/onboarding/gmail/callback
OAUTH_CLIENT_CONFIG_PATH=oauth_client_config.json

# Google Cloud Pub/Sub (Gmail Watch)
GMAIL_PUBSUB_TOPIC=projects/TU_PROYECTO/topics/gmail-notifications

# URL del servicio en producción (para validación JWT del webhook)
CLOUD_RUN_URL=https://tu-servicio.run.app

# Frontend URL para CORS
FRONTEND_URL=http://localhost:3000
```

Variables del frontend (`frontend/.env.local`):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
```

### 4. Arranca los servidores

```bash
# Backend (desde backend/)
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend (desde frontend/, en otra terminal)
cd frontend
npm run dev
```

- API: `http://localhost:8000` — Documentación interactiva: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`

---

## 🔌 API Reference

Todos los endpoints del dashboard y onboarding requieren **Firebase ID Token** en la cabecera `Authorization: Bearer <token>`.

### Dashboard (requiere Firebase Auth)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/dashboard/stats` | Totales de la gestoría: clientes, Gmail conectados, watches activos, documentos |
| `GET` | `/dashboard/clientes` | Lista todos los clientes con su estado de Gmail y watch |
| `GET` | `/dashboard/clientes/{cliente_id}` | Detalle de un cliente |
| `GET` | `/dashboard/clientes/{cliente_id}/documentos` | Documentos procesados (`?limit=50`) |

### Onboarding (requiere Firebase Auth)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/onboarding/clientes` | Registra un nuevo cliente `{"nombre": "...", "email": "..."}` |
| `GET` | `/onboarding/gmail/authorize/{cliente_id}` | Devuelve `{"authorization_url": "https://accounts.google.com/..."}` |
| `GET` | `/onboarding/gmail/callback` | Callback OAuth2 de Google; guarda tokens y activa el watch |

### Procesamiento de documentos

#### `POST /procesar-documento`

Sube y procesa un documento financiero directamente. Sin autenticación.

**Request** — `multipart/form-data` con campo `file`.

**MIME aceptados:** `application/pdf`, `image/jpeg`, `image/jpg`, `image/png`, `application/xml`, `text/xml`

**Response `200 OK`:**

```json
{
  "documento_id": "sha256-hash",
  "document_type": "invoice_received",
  "normalized_data": {
    "issuer_name": "Empresa S.L.",
    "issuer_nif": "B12345678",
    "invoice_number": "F2024-0042",
    "issue_date": "2024-03-15",
    "base_amount": 1000.00,
    "total_amount": 1210.00,
    "tax_lines": [{"tax_type": "iva", "rate": 21.0, "base_amount": 1000.0, "amount": 210.0}],
    "currency": "EUR"
  }
}
```

| Código | Causa |
|---|---|
| `400` | Archivo vacío o MIME no soportado |
| `409` | Documento duplicado (mismo SHA-256 ya en Firestore) |
| `503` | Gemini no disponible o rate limit |
| `500` | Error interno |

#### `POST /poll-gmail`

Dispara manualmente el polling de Gmail para todos los clientes activos. Sin autenticación.

**Response `200 OK`:**

```json
{
  "status": "success",
  "procesados": 3,
  "duplicados": 1,
  "errores": 0,
  "descartados": 5,
  "documentos": [],
  "detalle_duplicados": [],
  "detalle_errores": []
}
```

### Webhook (Pub/Sub)

#### `POST /webhook`

Recibe notificaciones push de Gmail Watch vía Google Cloud Pub/Sub. Verifica el JWT de Pub/Sub con `CLOUD_RUN_URL` como audience (se omite la verificación si la variable no está configurada). Renueva el watch automáticamente si expira en menos de 24 h.

### Tareas internas (Cloud Scheduler)

Ambos endpoints aceptan la cabecera `X-CloudScheduler` que Cloud Scheduler añade automáticamente.

#### `POST /internal/renew-watches`

Renueva todos los Gmail watches con `gmail_watch_status == "active"`. Llamar cada 6 días (los watches expiran a los ~7 días).

```json
{"renewed": 5, "failed": 0, "errors": []}
```

#### `POST /internal/retry-failed`

Re-procesa mensajes de Gmail con `status == "error"` en Firestore. Más eficiente que un poll completo: solo reintenta los mensajes que fallaron anteriormente.

```json
{"retried": 3, "succeeded": 2, "failed_again": 1, "errors": []}
```

---

## 🔐 Autenticación

### Firebase Auth (dashboard y onboarding)

```
Frontend                       Backend
   │                              │
   │── Authorization: Bearer ──► │
   │    <Firebase ID Token>       │
   │                              ├─ ¿Custom claim gestoria_id? → fast path ✅
   │                              ├─ ¿Usuario en Firestore usuarios/{uid}? → lookup ✅
   │                              └─ ¿Usuario nuevo? → auto-registro ✅
   │                                  (crea gestoría nueva en Firestore)
```

### Webhook JWT (Pub/Sub)

```
Cloud Pub/Sub → POST /webhook → verify JWT (audience = CLOUD_RUN_URL)
```

---

## 🤖 Motor de IA: Gemini

La extracción usa **dos fases** para garantizar JSON válido y tipado:

```
Documento (bytes/XML)
      │
      ▼ Fase 1 — Clasificación
   gemini-2.5-flash + response_schema=ClassificationResult
   → document_type: "invoice_received" | "bank_document" | ...
      │
      ▼ Fase 2 — Extracción
   gemini-2.5-flash + response_schema=<schema específico del tipo>
   → campos estructurados según el tipo detectado
```

**Estrategia de reintentos** (`tenacity`):
- 5 intentos en `gemini-2.5-flash`
- 5 intentos en `gemini-2.5-flash-lite` (fallback automático)
- Reintentos en: `UNAVAILABLE`, `RATE_LIMIT`, `PARSE_ERROR`

**Códigos de error estructurados** (`PipelineError.code`):

| Código | Causa |
|---|---|
| `UNAVAILABLE` | 503 del servicio |
| `RATE_LIMIT` | 429 / RESOURCE_EXHAUSTED |
| `TIMEOUT` | DEADLINE_EXCEEDED |
| `VALIDATION` | Respuesta con formato inesperado |
| `PARSE_ERROR` | JSON no válido en la respuesta |
| `INVALID_MIME` | Tipo de archivo no soportado |
| `UNKNOWN` | Cualquier otro error |

---

## 🐳 Docker

```bash
# Backend
cd backend
docker build -t zero-asist-backend .
docker run -p 8000:8000 --env-file .env zero-asist-backend

# Frontend
cd frontend
docker build -t zero-asist-frontend .
docker run -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8000 \
  -e NEXT_PUBLIC_FIREBASE_API_KEY=... \
  zero-asist-frontend
```

---

## ☁️ Despliegue en Google Cloud Run

```bash
cd backend
gcloud builds submit --tag gcr.io/TU_PROYECTO/zero-asist-backend .

gcloud run deploy zero-asist-backend \
  --image gcr.io/TU_PROYECTO/zero-asist-backend \
  --platform managed \
  --region europe-west1 \
  --set-env-vars GEMINI_API_KEY=...,CLOUD_RUN_URL=https://zero-asist-xxx.run.app,GMAIL_PUBSUB_TOPIC=...
```

> 💡 En Cloud Run, Firestore usa la cuenta de servicio del servicio automáticamente. No es necesario configurar `GOOGLE_APPLICATION_CREDENTIALS`.

---

## 🧪 Tests

```bash
# Todos los tests (desde backend/)
cd backend
pytest

# Modo verboso
pytest -v

# Un módulo específico
pytest tests/test_document_processor.py -v
```

La suite incluye **251 tests** distribuidos en 12 módulos:

| Módulo | Qué cubre |
|---|---|
| `test_main.py` | Endpoints FastAPI, validaciones HTTP |
| `test_auth.py` | Firebase Auth, resolución de gestoría, auto-registro |
| `test_dashboard.py` | Clientes, documentos, stats del dashboard |
| `test_onboarding.py` | Creación de clientes, flujo OAuth2 Gmail |
| `test_webhook.py` | Pub/Sub JWT, notificaciones, renovación de watches |
| `test_document_processor.py` | Pipeline: hash, dedup, extracción, guardado |
| `test_gemini_client.py` | Clasificación, extracción, reintentos, fallback de modelo |
| `test_gmail_poller.py` | Filtrado 3 capas, duplicados, errores |
| `test_gmail_reader.py` | Heurística de candidatos, descarga de adjuntos |
| `test_gmail_watch.py` | Start/renew/stop watch, detección de expiración |
| `test_normalizer.py` | Normalización, validación aritmética, líneas fiscales |

---

## 🛠️ Stack tecnológico

### Backend

| Capa | Tecnología | Versión |
|---|---|---|
| **API** | FastAPI + Uvicorn | 0.135.2 |
| **IA / LLM** | Google Gemini (google-genai) | 1.69.0 |
| **Base de datos** | Google Cloud Firestore | 2.26.0 |
| **Autenticación** | Firebase Admin SDK | 7.4.0 |
| **Email** | Gmail API (google-api-python-client) | 2.193.0 |
| **OAuth2** | google-auth-oauthlib | 1.3.1 |
| **Reintentos** | tenacity | — |
| **Testing** | pytest | — |
| **Linting / Formato** | flake8 + black | — |

### Frontend

| Capa | Tecnología | Versión |
|---|---|---|
| **Framework** | Next.js 15 (App Router) | 15.5 |
| **UI** | React + TailwindCSS 4 | 19 / 4 |
| **Lenguaje** | TypeScript | 5 |
| **Autenticación** | Firebase Auth | 12 |

---

## 🔄 Flujo de procesamiento de documentos

```
Documento (bytes)
      │
      ▼
┌─────────────────────┐
│  Validar MIME       │  PDF · JPEG · PNG · XML
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  SHA-256 hash       │  ID único del documento
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────┐
│ ¿Existe en Firestore?       │──── SÍ ──► 409 Duplicate
└────────┬────────────────────┘
         │ NO
         ▼
┌─────────────────────────────┐
│  Gemini — Fase 1            │  Clasificar tipo de documento
│  gemini-2.5-flash           │  (con fallback a flash-lite)
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Gemini — Fase 2            │  Extraer campos con schema
│  gemini-2.5-flash           │  específico del tipo detectado
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Normalización              │  Limpiar strings, monedas,
│                             │  fechas → Firestore Timestamp,
│                             │  validar aritmética fiscal
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Guardado transaccional     │  Race condition safe
│  gestorias/{g}/clientes/    │
│  {c}/documentos/{hash}      │
└────────┬────────────────────┘
         │
         ▼
    ✅ ProcessingResult
    { status, doc_hash,
      document_type,
      normalized_data }
```

---

## 📜 Licencia

Este proyecto está bajo la licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

<div align="center">

Hecho con ❤️ · [Reportar un bug](https://github.com/MMARTID/Zero-Asist/issues) · [Solicitar una función](https://github.com/MMARTID/Zero-Asist/issues)

</div>
