"use client";

import {
  useContact,
  useContactDocuments,
  updateContact,
  revalidatePrefix,
  type Document,
} from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

const DOC_TYPE_LABELS: Record<string, string> = {
  invoice_received: "Factura recibida",
  invoice_sent: "Factura emitida",
  payment_receipt: "Recibo de pago",
  administrative_notice: "Notificación",
  bank_document: "Documento bancario",
  contract: "Contrato",
  expense_ticket: "Ticket de gasto",
  other: "Otro",
};

const DOC_TYPE_COLORS: Record<string, string> = {
  invoice_received: "bg-blue-50 text-blue-700 ring-blue-200",
  invoice_sent: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  payment_receipt: "bg-violet-50 text-violet-700 ring-violet-200",
  administrative_notice: "bg-amber-50 text-amber-700 ring-amber-200",
  bank_document: "bg-cyan-50 text-cyan-700 ring-cyan-200",
  contract: "bg-rose-50 text-rose-700 ring-rose-200",
  expense_ticket: "bg-orange-50 text-orange-700 ring-orange-200",
};

function RoleBadge({ role }: { role: string }) {
  const colors =
    role === "proveedor"
      ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
      : role === "cliente"
        ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
        : "bg-gray-50 text-gray-600 ring-1 ring-gray-200";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors}`}>
      {role.charAt(0).toUpperCase() + role.slice(1)}
    </span>
  );
}

export default function ContactoDetailPage() {
  const { cuentaId, contactoId } = useParams<{
    cuentaId: string;
    contactoId: string;
  }>();

  const { data: contact, error: contactError, mutate: mutateContact } = useContact(cuentaId, contactoId);
  const { data: docsData } = useContactDocuments(cuentaId, contactoId);
  const documents: Document[] = docsData?.documentos ?? [];
  const [error, setError] = useState("");
  const [verifying, setVerifying] = useState(false);

  async function handleVerify() {
    if (!cuentaId || !contactoId) return;
    setVerifying(true);
    try {
      await updateContact(cuentaId, contactoId, {});
      await mutateContact();
      revalidatePrefix(`/dashboard/cuentas/${cuentaId}/contactos`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al verificar");
    } finally {
      setVerifying(false);
    }
  }

  const displayError = error || contactError?.message || "";

  if (displayError) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-50 p-4 text-red-600 ring-1 ring-red-100">
        <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
        <p className="text-sm">Error: {displayError}</p>
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="spinner" />
          <p className="text-sm text-muted">Cargando contacto…</p>
        </div>
      </div>
    );
  }

  const isVerified = contact.source === "user_verified";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href={`/dashboard/cuentas/${cuentaId}?tab=contactos`}
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Contactos de la cuenta
        </Link>
        <div className="mt-3 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-light text-brand text-lg font-bold">
            {contact.nombre_fiscal[0]}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight text-foreground">{contact.nombre_fiscal}</h2>
              {isVerified && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200" title="Verificado">
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Verificado
                </span>
              )}
              {!isVerified && contact.confidence < 0.7 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-200" title="Confianza baja">
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                  </svg>
                  Pendiente
                </span>
              )}
            </div>
            <div className="mt-1 flex items-center gap-2">
              {contact.tax_id && (
                <span className="font-mono text-sm text-muted">{contact.tax_id}</span>
              )}
              {contact.roles.map((r) => (
                <RoleBadge key={r} role={r} />
              ))}
              <span className="text-xs text-muted">
                {contact.source === "ai_extracted"
                  ? "Extraído automáticamente"
                  : contact.source === "user_verified"
                    ? "Verificado"
                    : "Creado manualmente"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Fiscal data */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 className="font-semibold text-foreground">Datos fiscales</h3>
          {!isVerified && (
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {verifying ? "Verificando…" : "Verificar contacto"}
            </button>
          )}
        </div>
        <div className="p-5">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              { label: "Nombre fiscal", value: contact.nombre_fiscal },
              contact.nombre_comercial ? { label: "Nombre comercial", value: contact.nombre_comercial } : null,
              { label: "NIF / CIF", value: contact.tax_id || "—", mono: true },
              { label: "Dirección fiscal", value: contact.direccion_fiscal || "—" },
              contact.codigo_postal ? { label: "Código postal", value: contact.codigo_postal } : null,
              { label: "Email", value: contact.email_contacto || "—" },
              { label: "Teléfono", value: contact.telefono || "—" },
              { label: "IBAN", value: contact.iban || "—", mono: true },
              { label: "Forma de pago habitual", value: contact.forma_pago_habitual || "—" },
            ]
              .filter(Boolean)
              .map((item) => (
                <div key={item!.label} className="rounded-lg bg-gray-50/50 p-3">
                  <dt className="text-xs font-medium text-muted">{item!.label}</dt>
                  <dd className={`mt-1 text-sm text-foreground ${(item as { mono?: boolean }).mono ? "font-mono" : ""}`}>
                    {item!.value}
                  </dd>
                </div>
              ))}
          </dl>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted">Documentos</p>
            <div className="rounded-lg bg-violet-50 p-2 text-violet-600">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
          </div>
          <p className="mt-3 text-3xl font-bold tracking-tight">{contact.total_documentos}</p>
        </div>
        {contact.total_recibido != null && (
          <div className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted">Total recibido</p>
              <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
                </svg>
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold tracking-tight">
              {contact.total_recibido.toLocaleString("es-ES", { style: "currency", currency: "EUR" })}
            </p>
          </div>
        )}
        {contact.total_facturado != null && (
          <div className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted">Total facturado</p>
              <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold tracking-tight">
              {contact.total_facturado.toLocaleString("es-ES", { style: "currency", currency: "EUR" })}
            </p>
          </div>
        )}
      </div>

      {/* Associated documents */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="border-b border-border px-5 py-4">
          <h3 className="font-semibold text-foreground">
            Documentos asociados
            <span className="ml-2 text-sm font-normal text-muted">({documents.length})</span>
          </h3>
        </div>
        <div className="p-5">
          {documents.length === 0 ? (
            <div className="flex flex-col items-center py-8">
              <svg className="h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <p className="mt-2 text-sm text-muted">Sin documentos asociados.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {documents.map((doc) => (
                <div
                  key={doc.doc_hash}
                  className="group flex items-center justify-between rounded-lg bg-white px-4 py-3 text-sm ring-1 ring-black/5 transition-colors hover:bg-gray-50"
                >
                  <div className="flex flex-1 items-center gap-3 min-w-0">
                    <span className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${DOC_TYPE_COLORS[doc.document_type ?? ""] ?? "bg-gray-50 text-gray-600 ring-gray-200"}`}>
                      {DOC_TYPE_LABELS[doc.document_type ?? ""] ?? doc.document_type ?? "Desconocido"}
                    </span>
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-medium text-foreground truncate">
                        {doc.filename || doc.doc_hash.slice(0, 12)}
                      </span>
                      <div className="flex items-center gap-2 text-xs text-muted">
                        {!!doc.normalized?.invoice_number && (
                          <span>Nº {String(doc.normalized.invoice_number)}</span>
                        )}
                        {doc.created_at && (
                          <span>
                            {new Date(doc.created_at).toLocaleDateString("es-ES")}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {doc.normalized?.total_amount != null && (
                      <span className="font-semibold text-foreground hidden sm:inline">
                        {Number(doc.normalized.total_amount).toLocaleString("es-ES", {
                          style: "currency",
                          currency: "EUR",
                        })}
                      </span>
                    )}
                    <Link
                      href={`/dashboard/review/${cuentaId}/${doc.doc_hash}`}
                      className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700 whitespace-nowrap"
                    >
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                      </svg>
                      Revisar
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
