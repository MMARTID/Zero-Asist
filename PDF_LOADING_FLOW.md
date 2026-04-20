# Zero-Asist PDF Loading Flow Analysis

## 1. REVIEW PAGE PDF LOADING
**File:** [frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx](frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx)

### Flow Overview
```
Component Mount → Load Document → Load PDF (if has_original) → Pass Blob URL to PDFViewer
```

### Step 1a: Initial Load
**Lines [46-50](frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx#L46-L50)**
```typescript
useEffect(() => {
  loadDocument();
  loadQueue();
}, [cuentaId, docHash]);
```
- Runs when component mounts or `cuentaId`/`docHash` changes
- Calls `loadDocument()` to fetch document metadata

### Step 1b: Document Loading
**Lines [60-71](frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx#L60-L71)**
```typescript
const loadDocument = async () => {
  try {
    setLoading(true);
    const doc = await getDocument(cuentaId, docHash);
    setDocument(doc);
    setFormData(doc.normalized || {});
    setDocumentType(doc.document_type || "other");
    setHasChanges(false);
  } catch (error) {
    logError("Error loading document", error);
    toast.error("Error al cargar el documento");
  } finally {
    setLoading(false);
  }
};
```
- Uses `getDocument()` from [frontend/lib/api.ts](frontend/lib/api.ts#L471)
- **Authentication:** Firebase ID token via `getHeaders()`
- **Request:** `GET /dashboard/cuentas/{cuentaId}/documentos/{docHash}`
- **Response:** `DocumentDetail` object with metadata including `has_original` flag

### Step 1c: PDF Loading Effect
**Lines [52-59](frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx#L52-L59)**
```typescript
useEffect(() => {
  if (document?.has_original) loadPDF();
  return () => {
    if (pdfBlobRef.current) URL.revokeObjectURL(pdfBlobRef.current);
  };
}, [document?.doc_hash]);
```
- **Cleanup**: Revokes blob URL when component unmounts or doc changes
- Only triggers PDF fetch if `has_original` is `true`
- Uses `useRef` to track blob URLs for cleanup

### Step 2: PDF Fetch with Authentication
**Lines [90-110](frontend/app/dashboard/review/[cuentaId]/[docHash]/page.tsx#L90-L110)**

#### Authentication Headers
```typescript
const user = await import("@/lib/firebase").then((m) => m.getFirebaseAuth().currentUser);
if (!user) throw new Error("Not authenticated");
const token = await user.getIdToken();
```
- Gets Firebase `currentUser`
- **Calls** `getIdToken()` to get fresh JWT token
- **Note:** Always gets fresh token (not cached) to ensure validity

#### Fetch Configuration
```typescript
const res = await fetch(
  `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/dashboard/cuentas/${cuentaId}/documentos/${docHash}/original`,
  { headers: { Authorization: `Bearer ${token}` } }
);
```
- **Endpoint:** `/dashboard/cuentas/{cuentaId}/documentos/{docHash}/original`
- **Method:** `GET`
- **Auth Header:** `Authorization: Bearer {Firebase JWT}`
- **No Content-Type needed** (response is binary)
- **API Base URL:** `process.env.NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`)

#### Blob Handling
```typescript
if (res.ok) {
  const blob = await res.blob();
  if (pdfBlobRef.current) URL.revokeObjectURL(pdfBlobRef.current);
  const url = URL.createObjectURL(blob);
  pdfBlobRef.current = url;
  setPdfBlob(url);
}
```
- **Response type:** `res.blob()` (binary data)
- **Blob URL lifecycle:**
  1. Revoke previous blob URL (if exists) to free memory
  2. Create new blob URL: `URL.createObjectURL(blob)`
  3. Store in ref: `pdfBlobRef.current = url`
  4. Store in state: `setPdfBlob(url)` → triggers PDFViewer re-render
- **Cleanup:** Blob URLs are revoked in cleanup function on unmount

---

## 2. PDF VIEWER COMPONENT
**File:** [frontend/components/pdf-viewer.tsx](frontend/components/pdf-viewer.tsx)

### Props Interface
**Lines [10-14](frontend/components/pdf-viewer.tsx#L10-L14)**
```typescript
interface PDFViewerProps {
  blobUrl: string | null;
  filename?: string;
  loading?: boolean;
}
```
- **`blobUrl`**: Object URL from review page (e.g., `blob:http://localhost:3000/...`)
- **`loading`**: Loading state from parent
- **`filename`**: Optional filename (not used currently)

### PDF.js Configuration
**Lines [5-8](frontend/components/pdf-viewer.tsx#L5-L8)**
```typescript
if (typeof window !== "undefined" && !pdfjs.GlobalWorkerOptions.workerSrc) {
  pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
}
```
- **Worker Setup**: Sets path to PDF.js worker file
- **File Location:** `/public/pdf.worker.min.mjs` (copied from `pdfjs-dist`)
- **When:** Only runs on client (checks `typeof window`)
- **Guard:** Only sets if not already configured (`!pdfjs.GlobalWorkerOptions.workerSrc`)
- **Why:** Worker handles PDF parsing in separate thread (avoids blocking main thread)

### Blob URL Change Handling
**Lines [25-31](frontend/components/pdf-viewer.tsx#L25-L31)**
```typescript
useEffect(() => {
  // Reset state when blob URL changes
  setPageNumber(1);
  setScale(1);
  setError(null);
}, [blobUrl]);
```
- Resets pagination, zoom, and errors when blob URL changes
- Allows seamless page transitions

### React-PDF Document Loading
**Lines [95-101](frontend/components/pdf-viewer.tsx#L95-L101)**
```typescript
<Document
  file={blobUrl}
  onLoadSuccess={handleDocumentLoadSuccess}
  onLoadError={handleDocumentLoadError}
  loading={<div className="text-center text-xs text-gray-600">Cargando…</div>}
>
  <Page pageNumber={pageNumber} scale={scale} renderTextLayer renderAnnotationLayer />
</Document>
```
- **`file` prop**: Receives blob URL directly
- **Blob URL handling by react-pdf**: Internally makes XHR request to blob URL
  - No auth header needed (blob URL contains data)
  - Worker processes PDF in background
- **Features:**
  - `renderTextLayer`: Selectable text overlay
  - `renderAnnotationLayer`: Form fields, links, annotations
- **Error handling:** `onLoadError` callback

### Error Handler
**Lines [37-39](frontend/components/pdf-viewer.tsx#L37-L39)**
```typescript
const handleDocumentLoadError = (error: Error) => {
  setError(`Error cargando PDF: ${error.message}`);
};
```
- Displays error if PDF loading fails
- Shows user-friendly message

### Response Type: NOT CORS-related
- **Blob URL has no CORS restrictions** by design:
  - Object URL is local to browser
  - Contains actual file bytes (not a reference)
  - Worker can read directly without Cross-Origin request
- **Potential Issues:**
  - Browser memory (blob URLs hold memory until revoked)
  - **Solution:** Implemented cleanup in review page effect

---

## 3. BACKEND API ENDPOINT
**File:** [backend/app/api/dashboard.py](backend/app/api/dashboard.py)

### Endpoint Definition
**Lines [242-280](backend/app/api/dashboard.py#L242-L280)**
```python
@router.get("/cuentas/{cuenta_id}/documentos/{doc_hash}/original")
def download_original_document(
    cuenta_id: str,
    doc_hash: str,
    gestoria_id: str = Depends(get_current_gestoria),
):
```

### Authentication (via Dependency Injection)

**`get_current_gestoria` dependency:** [backend/app/api/auth.py](backend/app/api/auth.py#L58-L108)

```python
def get_current_gestoria(
    claims: dict = Depends(_verify_firebase_token),
) -> str:
```

**Token Verification:** [backend/app/api/auth.py](backend/app/api/auth.py#L23-L57)
```python
def _verify_firebase_token(request: Request) -> dict:
  """Extract and verify a Firebase ID token from the Authorization header."""
  import firebase_admin
  from firebase_admin import auth as firebase_auth

  if not firebase_admin._apps:
    firebase_admin.initialize_app()

  auth_header = request.headers.get("Authorization", "")
  if not auth_header.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

  token = auth_header[len("Bearer "):]
  try:
    decoded = firebase_auth.verify_id_token(token)
  except Exception as e:
    logger.warning("Firebase token verification failed: %s", e)
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

**Authentication Flow:**
1. Extract `Authorization: Bearer {token}` header
2. Verify token with Firebase Admin SDK
3. Get custom claim or lookup user in Firestore
4. Return `gestoria_id` (tenant context)

### Database Lookup
**Lines [255-262](backend/app/api/dashboard.py#L255-L262)**
```python
ctx = TenantContext(gestoria_id=gestoria_id, cliente_id=cuenta_id)
db = _get_db()

doc = db.collection(ctx.docs_collection).document(doc_hash).get()
if not doc.exists:
  raise HTTPException(status_code=404, detail="Documento no encontrado")

data = doc.to_dict()
storage_path = data.get("storage_path")
```
- **Database:** Firestore
- **Collection:** `gestorias/{gestoria_id}/cuentas/{cuenta_id}/documentos`
- **Document key:** `doc_hash`
- **Multitenancy:** Enforced via `gestoria_id` (from auth)
- **Check:** Returns 404 if document doesn't exist or `storage_path` is missing

### Storage Retrieval
**Lines [263-273](backend/app/api/dashboard.py#L263-L273)**
```python
if not storage_path:
  raise HTTPException(
    status_code=404,
    detail="Original no disponible — el documento fue procesado antes de activar el almacenamiento",
  )

content = _gcs.download_document(storage_path)
if content is None:
  raise HTTPException(status_code=503, detail="Error al recuperar el archivo desde el almacenamiento")
```
- **Storage Backend:** Google Cloud Storage
- **Error Handling:**
  - 404 if no `storage_path` (old documents without storage)
  - 503 if GCS download fails
- **Returns:** Raw bytes (content)

### Response Headers
**Lines [274-282](backend/app/api/dashboard.py#L274-L282)**
```python
mime_type = data.get("mime_type", "application/octet-stream")
filename = data.get("file_name", "documento")
return Response(
  content=content,
  media_type=mime_type,
  headers={
    "Content-Disposition": f'inline; filename="{filename}"',
    "Cache-Control": "private, max-age=300",
  },
)
```

**Response Details:**
- **Status:** 200 OK
- **Content-Type:** `mime_type` from document (e.g., `application/pdf`, `image/jpeg`)
- **Content-Disposition:** `inline; filename="{filename}"`
  - Tells browser to display inline (not download)
  - Includes original filename
- **Cache-Control:** `private, max-age=300`
  - Private cache (don't cache shared)
  - 5-minute TTL
  - Prevents stale PDFs being served
- **Body:** Raw file bytes (blob)
- **No CORS headers set** (not needed for blob retrieval by same origin)

---

## 4. COMPLETE FLOW DIAGRAM

```
REVIEW PAGE LOAD
├── useEffect [cuentaId, docHash] (lines 46-50)
│   ├── loadDocument()
│   │   ├── Firebase: getIdToken()
│   │   ├── Fetch: GET /dashboard/cuentas/{cuentaId}/documentos/{docHash}
│   │   │   └── Headers: Authorization: Bearer {JWT}
│   │   ├── Parse JSON response → DocumentDetail
│   │   └── setState: setDocument, setFormData, setDocumentType
│   │
│   └── loadQueue()
│       └── Fetch review queue (for navigation)
│
└── useEffect [document?.doc_hash] (lines 52-59) → Cleanup on unmount
    ├── Check: document?.has_original
    └── If true: loadPDF()
        ├── Firebase: getIdToken() (fresh token)
        ├── Fetch: GET /dashboard/cuentas/{cuentaId}/documentos/{docHash}/original
        │   └── Headers: Authorization: Bearer {JWT}
        ├── Response: res.blob() (binary PDF/image)
        ├── Blob Processing:
        │   ├── Revoke previous URL: URL.revokeObjectURL(pdfBlobRef.current)
        │   ├── Create new URL: URL.createObjectURL(blob)
        │   ├── Store ref: pdfBlobRef.current = url
        │   └── Update state: setPdfBlob(url)
        └── Cleanup (on unmount):
            └── URL.revokeObjectURL(pdfBlobRef.current)

PDF VIEWER COMPONENT (new state)
├── useEffect [blobUrl] (lines 25-31)
│   └── Reset: page=1, scale=1, error=null
└── Render Document (lines 95-101)
    ├── react-pdf Document: file={blobUrl}
    ├── Worker processes PDF via blob URL
    ├── Success: setNumPages, clearError
    └── Error: setError

BACKEND FLOW
└── GET /dashboard/cuentas/{cuentaId}/documentos/{docHash}/original
    ├── Dependency: get_current_gestoria
    │   └── Verify Firebase JWT → get gestoria_id
    ├── Firestore lookup: gestorias/{gestoria_id}/cuentas/{cuenta_id}/documentos/{doc_hash}
    ├── Check: document exists
    ├── Check: storage_path exists
    ├── GCS: download_document(storage_path) → bytes
    └── Response:
        ├── Status: 200
        ├── Content-Type: {mime_type}
        ├── Content-Disposition: inline; filename=...
        ├── Cache-Control: private, max-age=300
        └── Body: Raw bytes (PDF/image data)
```

---

## 5. POTENTIAL ISSUES & SOLUTIONS

### Issue 1: CORS Problems
**Unlikely because:**
- Blob URLs are same-origin (no cross-origin request)
- PDF worker reads from blob URL directly
- No browser CORS checks for blob:// protocol

**If still seeing CORS errors:**
- Check browser console for actual error
- Likely not CORS but auth token expiration

### Issue 2: Blob URL Cleanup
**Current implementation handles:**
- Revokes on unmount (cleanup function)
- Revokes on page change (new effect)
- Safe because `requestAnimationFrame` pattern [line 39 in api.ts]

**Potential leak if:**
- Browser tab open for hours
- Multiple documents loaded
- **Solution:** Implemented with ref tracking

### Issue 3: Token Expiration
**Frontend always gets fresh token:**
- `loadPDF()` calls `getIdToken()` (not cached)
- Firebase SDK auto-refreshes if needed
- **Safe:** Token is fresh when fetch happens

### Issue 4: Old Documents Without Storage
**Handled at lines [263-265] in dashboard.py:**
- Returns 404 if `storage_path` is null
- Error message: "Original no disponible"
- User sees: "Error al cargar el PDF"

---

## 6. KEY IMPLEMENTATION DETAILS

### State Management (Review Page)
| State Variable | Type | Purpose |
|---|---|---|
| `pdfBlob` | `string \| null` | Current blob URL passed to PDFViewer |
| `pdfBlobRef` | `useRef<string>` | Tracks blob URL for cleanup |
| `pdfLoading` | `boolean` | Loading indicator |
| `document` | `DocumentDetail` | Metadata (including `has_original`) |

### Environment Variables
- **Frontend:** `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`)
- **Backend:** Firebase credentials (via Admin SDK initialization)

### Multitenancy Enforcement
- **Frontend:** Uses authenticated user's Firebase token
- **Backend:** Verifies token → gets `gestoria_id` → filters Firestore queries
- **Result:** User can only access their own documents

### Caching Strategy
- **Frontend:** SWR for document metadata, blob URLs for PDF (no HTTP cache)
- **Backend:** `Cache-Control: private, max-age=300` (5 min)
