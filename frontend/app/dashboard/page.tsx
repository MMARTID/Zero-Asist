"use client";

import Link from "next/link";
import { useState } from "react";
import { useStats, useAlerts, dismissAlert, type Alert } from "@/lib/api";
import { toast } from "sonner";
import { useModalParam } from "@/lib/use-modal-param";
import CreateCuentaModal from "@/components/create-cuenta-modal";

const CARD_CONFIG = [
  {
    label: "Cuentas",
    key: "total_clients" as const,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0" />
      </svg>
    ),
  },
  {
    label: "Gmail conectado",
    key: "connected_gmail" as const,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
  },
  {
    label: "Watches activos",
    key: "active_watches" as const,
    color: "text-amber-600",
    bg: "bg-amber-50",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.808-3.808-9.98 0-13.788m13.788 0c3.808 3.808 3.808 9.98 0 13.788M12 12h.008v.008H12V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
      </svg>
    ),
  },
  {
    label: "Documentos",
    key: "total_documents" as const,
    color: "text-violet-600",
    bg: "bg-violet-50",
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    ),
  },
];

export default function DashboardPage() {
  const { data: stats, error: swrError } = useStats();
  const { openModal } = useModalParam("crear-cuenta");
  const error = swrError?.message ?? "";

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-50 p-4 text-red-600 ring-1 ring-red-100">
        <svg className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
        <p className="text-sm">Error: {error}</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="space-y-8">
        <div>
          <div className="h-8 w-48 animate-pulse rounded-lg bg-gray-200" />
          <div className="mt-2 h-4 w-64 animate-pulse rounded bg-gray-100" />
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
              <div className="flex items-center justify-between">
                <div className="h-4 w-24 animate-pulse rounded bg-gray-200" />
                <div className="h-9 w-9 animate-pulse rounded-lg bg-gray-100" />
              </div>
              <div className="mt-3 h-9 w-16 animate-pulse rounded-lg bg-gray-200" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Dashboard
          </h2>
          <p className="mt-1 text-sm text-muted">
            Resumen general de tu gestoría
          </p>
        </div>
        <button
          onClick={() => openModal()}
          className="flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-dark shadow-brand/25 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Nueva cuenta
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {CARD_CONFIG.map((c) => (
          <div
            key={c.key}
            className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted">{c.label}</p>
              <div className={`rounded-lg ${c.bg} p-2 ${c.color}`}>
                {c.icon}
              </div>
            </div>
            <p className="mt-3 text-3xl font-bold tracking-tight text-foreground">
              {stats[c.key]}
            </p>
          </div>
        ))}
      </div>

      <AlertsPanel />

      <CreateCuentaModal />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alerts panel
// ---------------------------------------------------------------------------

const DOC_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  invoice_received:      { label: "Factura recibida",  color: "bg-blue-50 text-blue-700" },
  invoice_sent:          { label: "Factura emitida",   color: "bg-emerald-50 text-emerald-700" },
  expense_ticket:        { label: "Ticket de gasto",   color: "bg-orange-50 text-orange-700" },
  payment_receipt:       { label: "Justificante",      color: "bg-violet-50 text-violet-700" },
  bank_document:         { label: "Extracto bancario", color: "bg-cyan-50 text-cyan-700" },
  contract:              { label: "Contrato",          color: "bg-slate-100 text-slate-700" },
  administrative_notice: { label: "Notificación",      color: "bg-red-50 text-red-700" },
  other:                 { label: "Otro documento",    color: "bg-gray-100 text-gray-700" },
};

function relativeTime(isoStr: string | null): string {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins  < 2)  return "ahora mismo";
  if (mins  < 60) return `hace ${mins} min`;
  if (hours < 24) return `hace ${hours} h`;
  if (days  < 30) return `hace ${days} d`;
  return new Date(isoStr).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

const PREVIEW_COUNT = 5;

function AlertRow({ alert, onDismiss }: { alert: Alert; onDismiss: (a: Alert) => void }) {
  const type = DOC_TYPE_LABELS[alert.document_type] ?? { label: alert.document_type, color: "bg-gray-100 text-gray-700" };
  const primary = alert.issues[0];
  const extra   = alert.issues.length - 1;

  return (
    <div className="group flex items-start gap-4 rounded-xl px-4 py-3.5 transition-colors hover:bg-amber-50/60">
      <Link
        href={`/dashboard/review/${alert.cuenta_id}/${alert.doc_hash}`}
        className="flex flex-1 items-start gap-4"
      >
        {/* Warning dot */}
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100">
          <svg className="h-4 w-4 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.008v.008H12v-.008z" />
          </svg>
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${type.color}`}>
              {type.label}
            </span>
            <span className="text-sm font-medium text-foreground">{primary.message}</span>
            {extra > 0 && (
              <span className="text-xs text-muted">+{extra} más</span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted">
            <span className="truncate max-w-[200px]">{alert.filename ?? alert.doc_hash.slice(0, 12)}</span>
            <span>·</span>
            <span className="font-medium text-foreground/70">{alert.cuenta_nombre}</span>
          </div>
        </div>

        {/* Date + arrow */}
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
          {relativeTime(alert.created_at)}
          <svg className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </div>
      </Link>

      {/* Dismiss button */}
      <button
        onClick={(e) => { e.stopPropagation(); onDismiss(alert); }}
        title="Descartar alerta"
        className="mt-0.5 shrink-0 rounded-lg p-1.5 text-gray-400 opacity-0 transition-opacity hover:bg-gray-100 hover:text-gray-600 group-hover:opacity-100"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

function AlertsSkeleton() {
  return (
    <div className="divide-y divide-border">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex items-start gap-4 px-4 py-3.5">
          <div className="mt-0.5 h-8 w-8 shrink-0 animate-pulse rounded-full bg-gray-100" />
          <div className="flex-1 space-y-2">
            <div className="flex gap-2">
              <div className="h-5 w-28 animate-pulse rounded-md bg-gray-100" />
              <div className="h-5 w-48 animate-pulse rounded-md bg-gray-100" />
            </div>
            <div className="h-3.5 w-64 animate-pulse rounded bg-gray-100" />
          </div>
          <div className="h-3.5 w-16 animate-pulse rounded bg-gray-100" />
        </div>
      ))}
    </div>
  );
}

function AlertsPanel() {
  const { data, isLoading, mutate } = useAlerts(20);
  const [expanded, setExpanded] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>("");

  const alerts = data?.alerts ?? [];

  const filteredAlerts = typeFilter
    ? alerts.filter((a) => a.document_type === typeFilter)
    : alerts;

  const visible = expanded ? filteredAlerts : filteredAlerts.slice(0, PREVIEW_COUNT);
  const hiddenCount = filteredAlerts.length - PREVIEW_COUNT;

  // Unique doc types in alerts for filter chips
  const alertTypes = [...new Set(alerts.map((a) => a.document_type))];

  async function handleDismiss(alert: Alert) {
    try {
      await dismissAlert(alert.cuenta_id, alert.doc_hash);
      mutate();
      toast.success("Alerta descartada");
    } catch {
      toast.error("Error al descartar la alerta");
    }
  }

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <h3 className="text-base font-semibold text-foreground">Alertas de documentos</h3>
          {!isLoading && data && data.total > 0 && (
            <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
              {data.total}
            </span>
          )}
          {!isLoading && data && data.total === 0 && (
            <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
              Todo en orden
            </span>
          )}
        </div>
        <p className="text-xs text-muted">Campos críticos sin detectar</p>
      </div>

      {/* Filter chips */}
      {!isLoading && alertTypes.length > 1 && (
        <div className="flex flex-wrap gap-1.5 border-b border-border px-5 py-2.5">
          <button
            onClick={() => setTypeFilter("")}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
              !typeFilter ? "bg-brand text-white" : "bg-gray-100 text-muted hover:bg-gray-200"
            }`}
          >
            Todas
          </button>
          {alertTypes.map((t) => {
            const label = DOC_TYPE_LABELS[t]?.label ?? t;
            return (
              <button
                key={t}
                onClick={() => setTypeFilter(typeFilter === t ? "" : t)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                  typeFilter === t ? "bg-brand text-white" : "bg-gray-100 text-muted hover:bg-gray-200"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {/* Body */}
      {isLoading ? (
        <AlertsSkeleton />
      ) : alerts.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
            <svg className="h-6 w-6 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">Todos los documentos están completos</p>
            <p className="mt-1 text-xs text-muted">No hay campos críticos sin detectar</p>
          </div>
        </div>
      ) : (
        /* Alert list */
        <div>
          <div className="divide-y divide-border">
            {visible.map((alert) => (
              <AlertRow key={`${alert.cuenta_id}-${alert.doc_hash}`} alert={alert} onDismiss={handleDismiss} />
            ))}
          </div>

          {/* Expand / collapse footer */}
          {hiddenCount > 0 && (
            <div className="border-t border-border px-5 py-3">
              <button
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
              >
                {expanded ? (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
                    </svg>
                    Ver menos
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                    Ver {hiddenCount} alerta{hiddenCount !== 1 ? "s" : ""} más
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
