import { getFirebaseAuth } from "./firebase";
import useSWR, { type SWRConfiguration, mutate as globalMutate } from "swr";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getHeaders(): Promise<HeadersInit> {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await getHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...headers, ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }
  return res.json();
}

// SWR fetcher — uses the authenticated request() helper
async function swrFetcher<T>(path: string): Promise<T> {
  return request<T>(path);
}

/**
 * Fetches the original file for a document and opens it in a new tab.
 * Uses a blob URL so the auth header is included in the request.
 * Revokes the blob URL immediately after opening to prevent memory leaks.
 */
export async function openDocumentOriginal(
  cuentaId: string,
  docHash: string
): Promise<void> {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await user.getIdToken();
  const res = await fetch(
    `${API_URL}/dashboard/cuentas/${cuentaId}/documentos/${docHash}/original`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Error ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  
  // Open in new tab first, then immediately revoke the blob URL
  // The browser caches the content, so revocation is safe after window.open()
  window.open(url, "_blank");
  
  // Use requestAnimationFrame to ensure open() completes before revocation
  requestAnimationFrame(() => {
    URL.revokeObjectURL(url);
  });
}

// ---- Gestoría Profile ----

export interface GestoriaProfile {
  gestoria_id: string;
  nombre: string;
  phone_number: string;
  gestoria_software?: string;
  onboarding_complete: boolean;
}

export function fetchGestoriaProfile() {
  return request<GestoriaProfile>("/dashboard/gestoria");
}

export function updateGestoriaProfile(nombre: string, phone_number: string, gestoria_software?: string) {
  return request<GestoriaProfile>("/dashboard/gestoria", {
    method: "PATCH",
    body: JSON.stringify({ nombre, phone_number, gestoria_software }),
  });
}

// ---- Dashboard ----

export interface ClientSummary {
  cuenta_id: string;
  nombre: string;
  phone_number: string;
  tax_id: string | null;
  tax_country: string | null;
  tax_type: string | null;
  gmail_email: string | null;
  gmail_watch_status: string | null;
  min_income: number | null;
  max_income: number | null;
}

export interface ClientDetail extends ClientSummary {
  gestoria_id: string;
  gmail_watch_state: Record<string, unknown> | null;
}

export interface Document {
  doc_hash: string;
  document_type: string | null;
  filename: string | null;
  created_at: string | null;
  normalized: Record<string, unknown> | null;
  contact_refs?: ContactRef[];
  has_original?: boolean;
  review_status?: string; // "pending" | "reviewed"
}

export interface GlobalDocument extends Document {
  cuenta_id: string;
  cuenta_nombre: string;
}

export interface ContactRef {
  contacto_id: string;
  rol_en_documento: string; // "emisor" | "receptor" | "parte"
}

export interface ContactSummary {
  contacto_id: string;
  nombre_fiscal: string;
  tax_id: string | null;
  tax_country: string | null;
  tax_type: string | null;
  roles: string[];
  confidence: number;
  source: string | null;
  total_documentos: number;
  ultima_interaccion: string | null;
}

export interface ContactDetail extends ContactSummary {
  gestoria_id: string;
  cuenta_id: string;
  nombre_comercial: string | null;
  verified_at: string | null;
  direccion_fiscal: string | null;
  codigo_postal: string | null;
  email_contacto: string | null;
  telefono: string | null;
  iban: string | null;
  forma_pago_habitual: string | null;
  total_facturado: number | null;
  total_recibido: number | null;
  created_from_document: string | null;
  updated_at: string | null;
}

export interface Stats {
  gestoria_id: string;
  total_clients: number;
  connected_gmail: number;
  active_watches: number;
  total_documents: number;
}

export function getStats() {
  return request<Stats>("/dashboard/stats");
}

export function getClients() {
  return request<{ gestoria_id: string; cuentas: ClientSummary[] }>(
    "/dashboard/cuentas"
  );
}

export function getClient(cuentaId: string) {
  return request<ClientDetail>(`/dashboard/cuentas/${cuentaId}`);
}

export function getDocuments(cuentaId: string, limit = 50) {
  return request<{
    gestoria_id: string;
    cuenta_id: string;
    documentos: Document[];
    count: number;
  }>(`/dashboard/cuentas/${cuentaId}/documentos?limit=${limit}`);
}

// ---- Contacts ----

export function getContacts(cuentaId: string, rol?: string) {
  const params = rol ? `?rol=${rol}` : "";
  return request<{
    gestoria_id: string;
    cuenta_id: string;
    contactos: ContactSummary[];
    count: number;
  }>(`/dashboard/cuentas/${cuentaId}/contactos${params}`);
}

export function getContact(cuentaId: string, contactoId: string) {
  return request<ContactDetail>(
    `/dashboard/cuentas/${cuentaId}/contactos/${contactoId}`
  );
}

export function updateContact(
  cuentaId: string,
  contactoId: string,
  data: Record<string, unknown>
) {
  return request<{ status: string; contacto_id: string; fields_updated: string[] }>(
    `/dashboard/cuentas/${cuentaId}/contactos/${contactoId}`,
    { method: "PATCH", body: JSON.stringify(data) }
  );
}

export function getContactDocuments(
  cuentaId: string,
  contactoId: string,
  limit = 50
) {
  return request<{
    gestoria_id: string;
    cuenta_id: string;
    contacto_id: string;
    documentos: Document[];
    count: number;
  }>(
    `/dashboard/cuentas/${cuentaId}/contactos/${contactoId}/documentos?limit=${limit}`
  );
}

// ---- Onboarding ----

export function createClient(nombre: string, phone_number: string, tax_id: string) {
  return request<{ cuenta_id: string; gestoria_id: string; nombre: string; tax_id: string; tax_country: string; tax_type: string }>(
    "/onboarding/cuentas",
    { method: "POST", body: JSON.stringify({ nombre, phone_number, tax_id }) }
  );
}

export interface AnalyzeImportResponse {
  mapping: Record<string, string>;
  normalized_rows: Array<{
    nombre_fiscal: string;
    tax_id: string;
    phone_number: string;
    email_contacto?: string;
    direccion_fiscal?: string;
    codigo_postal?: string;
    confidence?: Record<string, number>;
  }>;
  warnings: string[];
}

export function analyzeImport(headers: string[], rows: string[][]) {
  return request<AnalyzeImportResponse>(
    "/onboarding/cuentas/import/analyze",
    { method: "POST", body: JSON.stringify({ headers, rows }) }
  );
}

export interface BulkCreateResponse {
  created: number;
  skipped: number;
  errors: Array<{ index: number; message: string }>;
}

export function bulkCreateClients(cuentas: Array<{
  nombre_fiscal: string;
  tax_id: string;
  phone_number: string;
  email_contacto?: string;
  direccion_fiscal?: string;
  codigo_postal?: string;
}>) {
  return request<BulkCreateResponse>(
    "/onboarding/cuentas/bulk",
    { method: "POST", body: JSON.stringify({ cuentas }) }
  );
}

export async function getGmailAuthorizeUrl(cuentaId: string): Promise<string> {
  const data = await request<{ authorization_url: string }>(
    `/onboarding/gmail/authorize/${cuentaId}`
  );
  return data.authorization_url;
}

// ---- SWR Hooks ----

const FAST_REFRESH: SWRConfiguration = { refreshInterval: 10_000, dedupingInterval: 5_000 };
const NORMAL: SWRConfiguration = { refreshInterval: 30_000, dedupingInterval: 10_000 };

export function useGestoriaProfile(enabled = true) {
  return useSWR<GestoriaProfile>(
    enabled ? "/dashboard/gestoria" : null,
    swrFetcher,
    NORMAL,
  );
}

export async function updateGestoriaSettings(
  nombre: string,
  phone_number: string,
  gestoria_software?: string,
): Promise<void> {
  await request("/dashboard/gestoria", {
    method: "PATCH",
    body: JSON.stringify({ nombre, phone_number, gestoria_software }),
  });
  await globalMutate("/dashboard/gestoria");
}

export function useGlobalDocuments(limit = 50) {
  return useSWR<{
    gestoria_id: string;
    documentos: GlobalDocument[];
    total: number;
  }>(`/dashboard/documentos?limit=${limit}`, swrFetcher, FAST_REFRESH);
}

export function useStats() {
  return useSWR<Stats>("/dashboard/stats", swrFetcher, NORMAL);
}

export function useClients() {
  return useSWR<{ gestoria_id: string; cuentas: ClientSummary[] }>(
    "/dashboard/cuentas",
    swrFetcher,
    NORMAL,
  );
}

export function useClient(cuentaId: string | undefined) {
  return useSWR<ClientDetail>(
    cuentaId ? `/dashboard/cuentas/${cuentaId}` : null,
    swrFetcher,
    NORMAL,
  );
}

export async function updateCuenta(
  cuentaId: string,
  data: Record<string, unknown>,
): Promise<void> {
  await request(`/dashboard/cuentas/${cuentaId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
  await globalMutate(`/dashboard/cuentas/${cuentaId}`);
  revalidatePrefix("/dashboard/cuentas");
}

export async function deleteCuenta(cuentaId: string): Promise<void> {
  await request(`/dashboard/cuentas/${cuentaId}`, { method: "DELETE" });
  revalidatePrefix("/dashboard");
}

export async function dismissAlert(cuentaId: string, docHash: string): Promise<void> {
  await request("/dashboard/alerts/dismiss", {
    method: "POST",
    body: JSON.stringify({ cuenta_id: cuentaId, doc_hash: docHash }),
  });
  revalidatePrefix("/dashboard/alerts");
}

export function useDocuments(cuentaId: string | undefined, limit = 50) {
  return useSWR<{
    gestoria_id: string;
    cuenta_id: string;
    documentos: Document[];
    count: number;
  }>(
    cuentaId ? `/dashboard/cuentas/${cuentaId}/documentos?limit=${limit}` : null,
    swrFetcher,
    FAST_REFRESH,
  );
}

export function useContacts(cuentaId: string | undefined, rol?: string) {
  const params = rol ? `?rol=${rol}` : "";
  return useSWR<{
    gestoria_id: string;
    cuenta_id: string;
    contactos: ContactSummary[];
    count: number;
  }>(
    cuentaId ? `/dashboard/cuentas/${cuentaId}/contactos${params}` : null,
    swrFetcher,
    FAST_REFRESH,
  );
}

export function useContact(cuentaId: string | undefined, contactoId: string | undefined) {
  return useSWR<ContactDetail>(
    cuentaId && contactoId
      ? `/dashboard/cuentas/${cuentaId}/contactos/${contactoId}`
      : null,
    swrFetcher,
    NORMAL,
  );
}

export function useContactDocuments(
  cuentaId: string | undefined,
  contactoId: string | undefined,
  limit = 50,
) {
  return useSWR<{
    gestoria_id: string;
    cuenta_id: string;
    contacto_id: string;
    documentos: Document[];
    count: number;
  }>(
    cuentaId && contactoId
      ? `/dashboard/cuentas/${cuentaId}/contactos/${contactoId}/documentos?limit=${limit}`
      : null,
    swrFetcher,
    FAST_REFRESH,
  );
}

/** Revalidate all keys matching a prefix (e.g. after creating a client). */
export function revalidatePrefix(prefix: string) {
  globalMutate((key) => typeof key === "string" && key.startsWith(prefix));
}

// ---- Alerts ----

export interface AlertIssue {
  field: string;
  message: string;
}

export interface Alert {
  cuenta_id: string;
  cuenta_nombre: string;
  doc_hash: string;
  document_type: string;
  filename: string | null;
  created_at: string | null;
  issues: AlertIssue[];
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
  limit: number;
}

export function useAlerts(limit = 20) {
  return useSWR<AlertsResponse>(
    `/dashboard/alerts?limit=${limit}`,
    swrFetcher,
    { ...NORMAL, refreshInterval: 60_000 },
  );
}

// ---- Fiscal Summary ----

export interface QuarterBucket {
  iva_soportado: number;
  iva_repercutido: number;
  irpf_retenido: number;
  total_facturado: number;
}

export interface FiscalSummary {
  year: number;
  quarters: Record<string, QuarterBucket>;
  annual: QuarterBucket;
}

export function useFiscalSummary(cuentaId: string | undefined, year: number) {
  return useSWR<FiscalSummary>(
    cuentaId ? `/dashboard/cuentas/${cuentaId}/fiscal-summary?year=${year}` : null,
    swrFetcher,
    NORMAL,
  );
}

// ---- Document Review ----

export interface DocumentDetail extends Document {
  gestoria_id: string;
  cuenta_id: string;
  extracted_data: Record<string, unknown> | null;
  contact_refs: ContactRef[];
  review_status: "pending" | "reviewed";
  reviewed_at: string | null;
  reviewed_by: string | null;
  storage_path?: string;
  mime_type?: string;
}

export interface ReviewQueueItem {
  cuenta_id: string;
  cuenta_nombre: string;
  doc_hash: string;
  document_type: string | null;
  filename: string | null;
  created_at: string | null;
}

export interface ReviewResponse {
  ok: boolean;
  next: ReviewQueueItem | null;
}

export async function getDocument(cuentaId: string, docHash: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/dashboard/cuentas/${cuentaId}/documentos/${docHash}`);
}

export async function updateDocument(
  cuentaId: string,
  docHash: string,
  data: {
    normalized_data?: Record<string, unknown>;
    document_type?: string;
  }
): Promise<DocumentDetail> {
  return request<DocumentDetail>(
    `/dashboard/cuentas/${cuentaId}/documentos/${docHash}`,
    { method: "PATCH", body: JSON.stringify(data) }
  );
}

export async function reviewDocument(
  cuentaId: string,
  docHash: string,
  data: { changes?: Record<string, unknown> }
): Promise<ReviewResponse> {
  return request<ReviewResponse>(
    `/dashboard/cuentas/${cuentaId}/documentos/${docHash}/review`,
    { method: "POST", body: JSON.stringify(data) }
  );
}

export async function getReviewQueue(limit = 50): Promise<{
  gestoria_id: string;
  queue: ReviewQueueItem[];
  total: number;
  limit: number;
}> {
  return request(`/dashboard/review-queue?limit=${limit}`);
}

export function useDocument(cuentaId: string | undefined, docHash: string | undefined) {
  return useSWR<DocumentDetail>(
    cuentaId && docHash ? `/dashboard/cuentas/${cuentaId}/documentos/${docHash}` : null,
    swrFetcher,
    NORMAL,
  );
}

export function useReviewQueue(limit = 50) {
  return useSWR<{
    gestoria_id: string;
    queue: ReviewQueueItem[];
    total: number;
    limit: number;
  }>(
    `/dashboard/review-queue?limit=${limit}`,
    swrFetcher,
    NORMAL,
  );
}
