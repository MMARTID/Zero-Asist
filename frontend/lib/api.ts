import { getFirebaseAuth } from "./firebase";

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

// ---- Dashboard ----

export interface ClientSummary {
  cliente_id: string;
  nombre: string;
  email: string;
  gmail_email: string | null;
  gmail_watch_status: string | null;
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
  return request<{ gestoria_id: string; clientes: ClientSummary[] }>(
    "/dashboard/clientes"
  );
}

export function getClient(clienteId: string) {
  return request<ClientDetail>(`/dashboard/clientes/${clienteId}`);
}

export function getDocuments(clienteId: string, limit = 50) {
  return request<{
    gestoria_id: string;
    cliente_id: string;
    documentos: Document[];
    count: number;
  }>(`/dashboard/clientes/${clienteId}/documentos?limit=${limit}`);
}

// ---- Onboarding ----

export function createClient(nombre: string, email: string) {
  return request<{ cliente_id: string; gestoria_id: string; nombre: string }>(
    "/onboarding/clientes",
    { method: "POST", body: JSON.stringify({ nombre, email }) }
  );
}

export async function getGmailAuthorizeUrl(clienteId: string): Promise<string> {
  const data = await request<{ authorization_url: string }>(
    `/onboarding/gmail/authorize/${clienteId}`
  );
  return data.authorization_url;
}
