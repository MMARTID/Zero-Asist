"use client";

import { useDocuments, type Document } from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";

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

export default function DocumentosPage() {
  const { cuentaId } = useParams<{ cuentaId: string }>();
  const { data, error: swrError, isLoading } = useDocuments(cuentaId);
  const documents: Document[] = data?.documentos ?? [];
  const error = swrError?.message || "";

  return (
    <div>
      <Link
        href={`/dashboard/cuentas/${cuentaId}`}
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
        </svg>
        Volver a la cuenta
      </Link>
      <h2 className="mt-2 mb-8 text-2xl font-bold tracking-tight text-foreground">Documentos</h2>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {error}
        </div>
      )}

      {isLoading && !data ? (
        <div className="flex h-48 items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="spinner" />
            <p className="text-sm text-muted">Cargando documentos…</p>
          </div>
        </div>
      ) : documents.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
          <svg className="h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          <p className="mt-3 text-sm font-medium text-muted">No hay documentos procesados aún</p>
        </div>
      ) : (
        <div className="space-y-2">
          {documents.map((doc) => (
            <div
              key={doc.doc_hash}
              className="group rounded-xl bg-white p-4 shadow-sm ring-1 ring-black/5 transition-all hover:shadow-md hover:ring-black/10"
            >
              {/* Header: Type + Filename + Amount */}
              <div className="flex items-start justify-between gap-4 mb-2">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  <span className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 mt-0.5 ${DOC_TYPE_COLORS[doc.document_type ?? ""] ?? "bg-gray-50 text-gray-600 ring-gray-200"}`}>
                    {DOC_TYPE_LABELS[doc.document_type ?? ""]?.slice(0, 12) ?? "Otro"}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-foreground leading-snug">
                      {doc.filename || doc.doc_hash.slice(0, 16)}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {!!doc.normalized?.invoice_number && (
                        <span className="text-xs text-gray-500 font-medium">
                          Nº {String(doc.normalized.invoice_number)}
                        </span>
                      )}
                      {doc.created_at && (
                        <span className="text-xs text-gray-400">
                          {new Date(doc.created_at).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "2-digit" })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {doc.normalized?.total_amount != null && (
                  <span className="shrink-0 text-lg font-bold tracking-tight text-foreground tabular-nums">
                    {Number(doc.normalized.total_amount).toLocaleString("es-ES", {
                      style: "currency",
                      currency: "EUR",
                    })}
                  </span>
                )}
              </div>

              {/* Extracted info row */}
              {doc.normalized && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 mb-3 px-0.5">
                  {!!(doc.normalized as Record<string, unknown>).issuer_name && (
                    <span>
                      <span className="text-gray-400">Emisor:</span>{" "}
                      <span className="font-medium text-foreground">
                        {String((doc.normalized as Record<string, unknown>).issuer_name)?.slice(0, 30)}
                      </span>
                    </span>
                  )}
                  {!!(doc.normalized as Record<string, unknown>).client_name && (
                    <span>
                      <span className="text-gray-400">Cliente:</span>{" "}
                      <span className="font-medium text-foreground">
                        {String((doc.normalized as Record<string, unknown>).client_name)?.slice(0, 30)}
                      </span>
                    </span>
                  )}
                </div>
              )}

              {/* Actions footer */}
              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                {doc.normalized && (
                  <details className="group/details">
                    <summary className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-brand hover:text-brand-dark transition-colors">
                      <svg className="h-3.5 w-3.5 shrink-0 transition-transform group-open/details:rotate-90" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                      </svg>
                      Datos
                    </summary>
                    <pre className="mt-2 overflow-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-600 ring-1 ring-black/5 max-h-40">
                      {JSON.stringify(doc.normalized, null, 2)}
                    </pre>
                  </details>
                )}
                
                <Link
                  href={`/dashboard/review/${cuentaId}/${doc.doc_hash}`}
                  className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-700 px-3 py-1.5 text-xs font-semibold text-white transition-all hover:shadow-md hover:from-indigo-700 hover:to-indigo-800 active:scale-95"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0l-3-3m3 3L18 6" />
                  </svg>
                  Revisar
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
