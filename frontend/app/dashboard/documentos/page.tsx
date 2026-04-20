"use client";

import {
  useGlobalDocuments,
  openDocumentOriginal,
  type GlobalDocument,
} from "@/lib/api";
import Link from "next/link";
import { useState, useMemo } from "react";

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

export default function DocumentosGlobalPage() {
  const { data, isLoading } = useGlobalDocuments(200);
  const documents = data?.documentos ?? [];

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [downloadingDoc, setDownloadingDoc] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let result = documents;

    if (typeFilter) {
      result = result.filter((d) => d.document_type === typeFilter);
    }

    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter((d) => {
        const n = d.normalized as Record<string, unknown> | null;
        const haystack = [
          d.filename,
          d.cuenta_nombre,
          d.document_type ? DOC_TYPE_LABELS[d.document_type] : null,
          n?.issuer_name,
          n?.issuer_nif,
          n?.client_name,
          n?.client_nif,
          n?.invoice_number,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }

    return result;
  }, [documents, search, typeFilter]);

  async function handleViewOriginal(doc: GlobalDocument) {
    setDownloadingDoc(doc.doc_hash);
    try {
      await openDocumentOriginal(doc.cuenta_id, doc.doc_hash);
    } finally {
      setDownloadingDoc(null);
    }
  }

  function relativeTime(dateStr: string | null): string {
    if (!dateStr) return "";
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "ahora";
    if (mins < 60) return `hace ${mins} min`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `hace ${hours} h`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `hace ${days} d`;
    return new Date(dateStr).toLocaleDateString("es-ES");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Bandeja de entrada
          </h2>
          <p className="mt-1 text-sm text-muted">
            Últimos documentos recibidos en todas las cuentas
          </p>
        </div>
        {data && (
          <span className="rounded-full bg-brand-light px-3 py-1 text-sm font-medium text-brand">
            {data.total} documentos
          </span>
        )}
      </div>

      {/* Toolbar */}
      <div className="space-y-3">
        <div className="relative">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por cuenta, emisor, NIF, nº factura…"
            className="w-full rounded-xl border-0 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm ring-1 ring-black/5 placeholder:text-gray-400 focus:ring-2 focus:ring-brand/30 focus:outline-none"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-gray-400 hover:text-gray-600"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5">
          {[
            { key: "", label: "Todos" },
            { key: "invoice_received", label: "Recibidas" },
            { key: "invoice_sent", label: "Emitidas" },
            { key: "expense_ticket", label: "Tickets" },
            { key: "payment_receipt", label: "Recibos" },
            { key: "administrative_notice", label: "Notificaciones" },
            { key: "bank_document", label: "Bancarios" },
            { key: "contract", label: "Contratos" },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => setTypeFilter(f.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                typeFilter === f.key
                  ? "bg-brand text-white shadow-sm"
                  : "bg-white text-muted ring-1 ring-black/5 hover:bg-gray-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {(search || typeFilter) && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">
              {filtered.length} de {documents.length} documentos
            </span>
            <button
              onClick={() => {
                setSearch("");
                setTypeFilter("");
              }}
              className="text-xs font-medium text-brand hover:text-brand-dark"
            >
              Limpiar filtros
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="animate-pulse rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5"
            >
              <div className="flex items-center gap-3">
                <div className="h-6 w-20 rounded-full bg-gray-200" />
                <div className="h-4 w-32 rounded bg-gray-200" />
                <div className="ml-auto h-4 w-16 rounded bg-gray-200" />
              </div>
              <div className="mt-3 h-4 w-48 rounded bg-gray-200" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
          <svg
            className="h-10 w-10 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H6.911a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661z"
            />
          </svg>
          <p className="mt-2 text-sm font-medium text-muted">
            {documents.length === 0
              ? "Aún no hay documentos"
              : "Sin resultados para estos filtros"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((doc) => {
            const n = doc.normalized as Record<string, unknown> | null;
            return (
              <div
                key={`${doc.cuenta_id}-${doc.doc_hash}`}
                className="group rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5 transition-shadow hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-1">
                    {/* Type badge + cuenta + time */}
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${
                          DOC_TYPE_COLORS[doc.document_type ?? ""] ??
                          "bg-gray-50 text-gray-600 ring-gray-200"
                        }`}
                      >
                        {DOC_TYPE_LABELS[doc.document_type ?? ""] ??
                          doc.document_type ??
                          "Desconocido"}
                      </span>
                      <Link
                        href={`/dashboard/cuentas/${doc.cuenta_id}?tab=documentos`}
                        className="text-xs font-medium text-brand hover:text-brand-dark"
                      >
                        {doc.cuenta_nombre}
                      </Link>
                      {doc.created_at && (
                        <span
                          className="text-xs text-gray-400"
                          title={new Date(doc.created_at).toLocaleString("es-ES")}
                        >
                          {relativeTime(doc.created_at)}
                        </span>
                      )}
                    </div>

                    {/* Filename */}
                    <p className="truncate font-medium text-foreground">
                      {doc.filename || doc.doc_hash.slice(0, 12)}
                    </p>

                    {/* Extracted info */}
                    {n && (
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                        {!!n.issuer_name && (
                          <span>
                            <span className="text-gray-400">Emisor:</span>{" "}
                            {String(n.issuer_name)}
                            {!!n.issuer_nif && (
                              <span className="ml-1 font-mono text-gray-400">
                                ({String(n.issuer_nif)})
                              </span>
                            )}
                          </span>
                        )}
                        {!!n.invoice_number && (
                          <span>
                            <span className="text-gray-400">Nº:</span>{" "}
                            {String(n.invoice_number)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Amount */}
                  {n?.total_amount != null && (
                    <span className="shrink-0 text-lg font-bold tracking-tight text-foreground">
                      {Number(n.total_amount).toLocaleString("es-ES", {
                        style: "currency",
                        currency: "EUR",
                      })}
                    </span>
                  )}
                </div>

                {/* Actions - Clean layout */}
                <div className="mt-3 flex items-center justify-between">
                  {/* Status badge */}
                  {doc.review_status && (
                    <span className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      doc.review_status === "reviewed"
                        ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                        : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
                    }`}>
                      {doc.review_status === "reviewed" ? (
                        <>
                          <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
                          </svg>
                          Revisada
                        </>
                      ) : (
                        <>
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Pendiente
                        </>
                      )}
                    </span>
                  )}
                  
                  {/* Primary action + menu */}
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/dashboard/review/${doc.cuenta_id}/${doc.doc_hash}`}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 active:bg-indigo-800"
                    >
                      Revisar
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                      </svg>
                    </Link>
                    
                    {/* Secondary actions menu */}
                    {doc.has_original && (
                      <button
                        onClick={() => handleViewOriginal(doc)}
                        disabled={downloadingDoc === doc.doc_hash}
                        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 disabled:hover:bg-white"
                        title="Descargar documento original"
                      >
                        {downloadingDoc === doc.doc_hash ? (
                          <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                          </svg>
                        ) : (
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                          </svg>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
