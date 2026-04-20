"use client";

import {
  useClient,
  useDocuments,
  useContacts,
  useFiscalSummary,
  getGmailAuthorizeUrl,
  openDocumentOriginal,
  updateCuenta,
  deleteCuenta,
  type Document,
  type ContactSummary,
  type QuarterBucket,
} from "@/lib/api";
import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useState, useMemo, useEffect } from "react";
import { toast } from "sonner";

type Tab = "resumen" | "documentos" | "contactos" | "gmail" | "datos";

const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  {
    key: "resumen",
    label: "Resumen",
    icon: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
      </svg>
    ),
  },
  {
    key: "documentos",
    label: "Documentos",
    icon: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
      </svg>
    ),
  },
  {
    key: "contactos",
    label: "Contactos",
    icon: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
      </svg>
    ),
  },
  {
    key: "gmail",
    label: "Gmail",
    icon: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
  },
  {
    key: "datos",
    label: "Datos de la cuenta",
    icon: (
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

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

function ConfidenceBadge({ confidence, source }: { confidence: number; source: string | null }) {
  if (source === "user_verified") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200" title="Verificado por el usuario">
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </span>
    );
  }
  if (confidence < 0.7) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-200" title="Confianza baja — pendiente de verificación">
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      </span>
    );
  }
  return null;
}

/* ---------- NormalizedDataView ---------- */

const FIELD_LABELS: Record<string, string> = {
  issuer_name: "Emisor",
  issuer_nif: "NIF emisor",
  client_name: "Cliente",
  client_nif: "NIF cliente",
  invoice_number: "Nº factura",
  issue_date: "Fecha emisión",
  due_date: "Fecha vencimiento",
  concept: "Concepto",
  base_amount: "Base imponible",
  tax_rate: "Tipo IVA",
  tax_amount: "Cuota IVA",
  irpf_rate: "Tipo IRPF",
  irpf_amount: "Retención IRPF",
  total_amount: "Total",
  currency: "Moneda",
  payment_method: "Forma de pago",
  bank_account: "Cuenta bancaria",
  notes: "Notas",
  // expense ticket
  merchant_name: "Comercio",
  merchant_nif: "NIF comercio",
  // bank / admin
  entity_name: "Entidad",
  reference_number: "Referencia",
  description: "Descripción",
  authority_name: "Organismo",
  notification_date: "Fecha notificación",
  response_deadline: "Plazo respuesta",
  // contract
  parties: "Partes",
  effective_date: "Fecha efecto",
  end_date: "Fecha fin",
  contract_type: "Tipo contrato",
};

const CURRENCY_FIELDS = new Set([
  "base_amount",
  "tax_amount",
  "irpf_amount",
  "total_amount",
]);

function NormalizedDataView({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(
    ([, v]) => v != null && v !== "" && v !== 0,
  );
  if (entries.length === 0) return <p className="mt-2 text-xs text-gray-400">Sin datos</p>;

  return (
    <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg bg-gray-50 p-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([key, value]) => {
        // skip internal/complex fields rendered below
        if (key === "tax_lines" || key === "line_items") return null;

        const label = FIELD_LABELS[key] ?? key.replace(/_/g, " ");
        let display: React.ReactNode;

        if (CURRENCY_FIELDS.has(key)) {
          display = Number(value).toLocaleString("es-ES", { style: "currency", currency: "EUR" });
        } else if (typeof value === "number" && key.includes("rate")) {
          display = `${value}%`;
        } else if (Array.isArray(value)) {
          display = value.join(", ");
        } else if (typeof value === "object" && value !== null) {
          display = JSON.stringify(value);
        } else {
          display = String(value);
        }

        return (
          <div key={key}>
            <dt className="text-xs font-medium text-muted capitalize">{label}</dt>
            <dd className="mt-0.5 text-foreground">{display}</dd>
          </div>
        );
      })}

      {/* Tax lines */}
      {Array.isArray(data.tax_lines) && data.tax_lines.length > 0 && (
        <div className="col-span-full mt-2">
          <dt className="text-xs font-medium text-muted">Líneas de impuestos</dt>
          <dd className="mt-1">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted">
                  <th className="text-left font-medium">Base</th>
                  <th className="text-left font-medium">Tipo</th>
                  <th className="text-left font-medium">Cuota</th>
                </tr>
              </thead>
              <tbody>
                {(data.tax_lines as Record<string, unknown>[]).map((tl, i) => (
                  <tr key={i}>
                    <td>{tl.base != null ? Number(tl.base).toLocaleString("es-ES", { style: "currency", currency: "EUR" }) : "—"}</td>
                    <td>{tl.rate != null ? `${tl.rate}%` : "—"}</td>
                    <td>{tl.amount != null ? Number(tl.amount).toLocaleString("es-ES", { style: "currency", currency: "EUR" }) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </dd>
        </div>
      )}
    </dl>
  );
}

const FISCAL_METRICS: {
  key: keyof QuarterBucket;
  label: string;
  icon: React.ReactNode;
  bgColor: string;
  textColor: string;
  iconBg: string;
}[] = [
  {
    key: "iva_soportado",
    label: "IVA Soportado",
    bgColor: "bg-blue-50",
    textColor: "text-blue-700",
    iconBg: "bg-blue-100 text-blue-600",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6L9 12.75l4.286-4.286a11.948 11.948 0 014.306 6.43l.776 2.898m0 0l3.182-5.511m-3.182 5.51l-5.511-3.181" />
      </svg>
    ),
  },
  {
    key: "iva_repercutido",
    label: "IVA Repercutido",
    bgColor: "bg-emerald-50",
    textColor: "text-emerald-700",
    iconBg: "bg-emerald-100 text-emerald-600",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
      </svg>
    ),
  },
  {
    key: "irpf_retenido",
    label: "IRPF Retenido",
    bgColor: "bg-amber-50",
    textColor: "text-amber-700",
    iconBg: "bg-amber-100 text-amber-600",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "total_facturado",
    label: "Total Facturado",
    bgColor: "bg-violet-50",
    textColor: "text-violet-700",
    iconBg: "bg-violet-100 text-violet-600",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
];

const QUARTER_LABELS = ["T1", "T2", "T3", "T4"] as const;

function formatEUR(n: number) {
  return n.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
}

function FiscalCards({
  fiscal,
  loading,
  year,
  onYearChange,
}: {
  fiscal: { year: number; quarters: Record<string, QuarterBucket>; annual: QuarterBucket } | null;
  loading: boolean;
  year: number;
  onYearChange: (y: number) => void;
}) {
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 6 }, (_, i) => currentYear - i);

  return (
    <div className="space-y-4">
      {/* Header with year selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Resumen Fiscal</h3>
        <select
          value={year}
          onChange={(e) => onYearChange(Number(e.target.value))}
          className="rounded-lg border border-border bg-white px-3 py-1.5 text-sm text-foreground shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        >
          {years.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {/* Metric cards */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
              <div className="h-4 w-24 rounded bg-gray-200" />
              <div className="mt-4 space-y-2">
                {[0, 1, 2, 3, 4].map((j) => (
                  <div key={j} className="flex justify-between">
                    <div className="h-3 w-8 rounded bg-gray-200" />
                    <div className="h-3 w-16 rounded bg-gray-200" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {FISCAL_METRICS.map((metric) => {
            const annualVal = fiscal?.annual[metric.key] ?? 0;
            const allZero = annualVal === 0;

            return (
              <div
                key={metric.key}
                className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5"
              >
                {/* Card header */}
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-muted">{metric.label}</p>
                  <div className={`rounded-lg p-2 ${metric.iconBg}`}>
                    {metric.icon}
                  </div>
                </div>

                {/* Annual total */}
                <p className="mt-3 text-2xl font-bold tracking-tight text-foreground">
                  {formatEUR(annualVal)}
                </p>

                {/* Quarterly breakdown */}
                <div className="mt-4 space-y-1.5">
                  {QUARTER_LABELS.map((q) => {
                    const val = fiscal?.quarters[q]?.[metric.key] ?? 0;
                    return (
                      <div key={q} className="flex items-center justify-between text-sm">
                        <span className="font-medium text-muted">{q}</span>
                        <span className={val > 0 ? "font-medium text-foreground" : "text-gray-300"}>
                          {formatEUR(val)}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {allZero && (
                  <p className="mt-3 text-center text-xs text-gray-400">
                    Sin datos para {year}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function CuentaDetailPage() {
  const { cuentaId } = useParams<{ cuentaId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const activeTab = (searchParams.get("tab") as Tab) || "resumen";

  const [contactFilter, setContactFilter] = useState<string>("");
  const [contactSearch, setContactSearch] = useState("");
  const [error, setError] = useState("");
  const [fiscalYear, setFiscalYear] = useState(new Date().getFullYear());

  // Document search state
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "amount">("date");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [downloadingDoc, setDownloadingDoc] = useState<string | null>(null);

  async function handleViewOriginal(docHash: string) {
    setDownloadingDoc(docHash);
    try {
      await openDocumentOriginal(cuentaId, docHash);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al abrir el documento");
    } finally {
      setDownloadingDoc(null);
    }
  }

  const { data: client, error: clientError } = useClient(cuentaId);
  const { data: docsData } = useDocuments(
    (activeTab === "documentos" || activeTab === "resumen") ? cuentaId : undefined,
    activeTab === "documentos" ? 200 : 50,
  );
  const { data: contactsData } = useContacts(
    (activeTab === "contactos" || activeTab === "resumen") ? cuentaId : undefined,
    contactFilter || undefined
  );

  const documents: Document[] = docsData?.documentos ?? [];
  const contacts: ContactSummary[] = contactsData?.contactos ?? [];

  const filteredContacts = useMemo(() => {
    if (!contactSearch.trim()) return contacts;
    const q = contactSearch.toLowerCase().trim();
    return contacts.filter((c) =>
      [c.nombre_fiscal, c.tax_id, ...c.roles].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [contacts, contactSearch]);

  // Filtered + sorted documents for the search view
  const filteredDocs = useMemo(() => {
    let result = documents;

    // Type filter
    if (typeFilter) {
      result = result.filter((d) => d.document_type === typeFilter);
    }

    // Text search (case-insensitive across multiple fields)
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((d) => {
        const n = d.normalized as Record<string, unknown> | null;
        const haystack = [
          d.filename,
          d.document_type ? DOC_TYPE_LABELS[d.document_type] : null,
          n?.issuer_name,
          n?.issuer_nif,
          n?.client_name,
          n?.client_nif,
          n?.invoice_number,
          n?.concept,
          n?.total_amount != null ? String(n.total_amount) : null,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }

    // Date range filters
    if (dateFrom) {
      const from = new Date(dateFrom);
      result = result.filter((d) => {
        const n = d.normalized as Record<string, unknown> | null;
        const raw = n?.issue_date ?? d.created_at;
        return raw ? new Date(String(raw)) >= from : false;
      });
    }
    if (dateTo) {
      const to = new Date(dateTo + "T23:59:59");
      result = result.filter((d) => {
        const n = d.normalized as Record<string, unknown> | null;
        const raw = n?.issue_date ?? d.created_at;
        return raw ? new Date(String(raw)) <= to : false;
      });
    }

    // Sort
    result = [...result].sort((a, b) => {
      if (sortBy === "amount") {
        const amtA = Number((a.normalized as Record<string, unknown>)?.total_amount ?? 0);
        const amtB = Number((b.normalized as Record<string, unknown>)?.total_amount ?? 0);
        return sortDir === "desc" ? amtB - amtA : amtA - amtB;
      }
      // date sort
      const na = a.normalized as Record<string, unknown> | null;
      const nb = b.normalized as Record<string, unknown> | null;
      const dA = new Date(String(na?.issue_date ?? a.created_at ?? 0)).getTime();
      const dB = new Date(String(nb?.issue_date ?? b.created_at ?? 0)).getTime();
      return sortDir === "desc" ? dB - dA : dA - dB;
    });

    return result;
  }, [documents, searchQuery, typeFilter, dateFrom, dateTo, sortBy, sortDir]);

  const hasActiveFilters = searchQuery || typeFilter || dateFrom || dateTo;

  const { data: fiscal, isLoading: fiscalLoading } = useFiscalSummary(
    activeTab === "resumen" ? cuentaId : undefined,
    fiscalYear,
  );

  function setTab(tab: Tab) {
    router.replace(`/dashboard/cuentas/${cuentaId}?tab=${tab}`);
  }

  const displayError = error || clientError?.message || "";

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

  if (!client) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="spinner" />
          <p className="text-sm text-muted">Cargando cuenta…</p>
        </div>
      </div>
    );
  }

  const proveedores = contacts.filter((c) => c.roles.includes("proveedor")).length;
  const clientes = contacts.filter((c) => c.roles.includes("cliente")).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/dashboard/cuentas"
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Cuentas
        </Link>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-foreground">{client.nombre}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          {client.tax_id && (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-2.5 py-1 font-mono text-sm text-foreground ring-1 ring-black/5">
              <svg className="h-3.5 w-3.5 text-muted" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 9h3.75M15 12h3.75M15 15h3.75M4.5 19.5h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5zm6-10.125a1.875 1.875 0 11-3.75 0 1.875 1.875 0 013.75 0zm1.294 6.336a6.721 6.721 0 01-3.17.789 6.721 6.721 0 01-3.168-.789 3.376 3.376 0 016.338 0z" />
              </svg>
              {client.tax_id}
            </span>
          )}
          {client.phone_number && (
            <span className="inline-flex items-center gap-1.5 text-sm text-muted">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
              </svg>
              {client.phone_number}
            </span>
          )}
          {client.gmail_email && (
            <span className="inline-flex items-center gap-1.5 text-sm text-muted">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
              </svg>
              {client.gmail_email}
            </span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="-mb-px flex space-x-1" role="tablist" aria-label="Secciones de la cuenta">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              role="tab"
              aria-selected={activeTab === t.key}
              aria-controls={`panel-${t.key}`}
              className={`inline-flex items-center gap-2 border-b-2 px-4 pb-3 text-sm font-medium ${
                activeTab === t.key
                  ? "border-brand text-brand"
                  : "border-transparent text-muted hover:border-gray-300 hover:text-foreground"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ===== RESUMEN ===== */}
      {activeTab === "resumen" && (
        <div className="space-y-6">
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
              <p className="mt-3 text-3xl font-bold tracking-tight">{documents.length}</p>
            </div>
            <div className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted">Proveedores</p>
                <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" />
                  </svg>
                </div>
              </div>
              <p className="mt-3 text-3xl font-bold tracking-tight">{proveedores}</p>
            </div>
            <div className="card-hover rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted">Clientes</p>
                <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                  </svg>
                </div>
              </div>
              <p className="mt-3 text-3xl font-bold tracking-tight">{clientes}</p>
            </div>
          </div>

          {/* Fiscal summary */}
          <FiscalCards
            fiscal={fiscal ?? null}
            loading={fiscalLoading}
            year={fiscalYear}
            onYearChange={setFiscalYear}
          />

          {/* Recent documents */}
          <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
            <div className="border-b border-border px-5 py-4">
              <h3 className="font-semibold text-foreground">Últimos documentos</h3>
            </div>
            <div className="p-5">
              {documents.length === 0 ? (
                <p className="text-center text-sm text-muted py-6">Sin documentos aún.</p>
              ) : (
                <div className="space-y-2">
                  {documents.slice(0, 5).map((doc) => (
                    <div
                      key={doc.doc_hash}
                      className="flex items-center justify-between rounded-lg bg-gray-50/50 px-4 py-3 text-sm ring-1 ring-black/5"
                    >
                      <div className="flex items-center gap-3">
                        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${DOC_TYPE_COLORS[doc.document_type ?? ""] ?? "bg-gray-50 text-gray-600 ring-gray-200"}`}>
                          {DOC_TYPE_LABELS[doc.document_type ?? ""] ?? doc.document_type ?? "Desconocido"}
                        </span>
                        {doc.normalized && (
                          <div className="flex items-center gap-2 text-muted">
                            <span>
                              {(doc.normalized as Record<string, unknown>).issuer_name as string ??
                                (doc.normalized as Record<string, unknown>).client_name as string ??
                                ""}
                            </span>
                            {!!((doc.normalized as Record<string, unknown>).issuer_nif ||
                              (doc.normalized as Record<string, unknown>).client_nif) && (
                              <span className="font-mono text-xs text-gray-400">
                                {((doc.normalized as Record<string, unknown>).issuer_nif as string) ??
                                  ((doc.normalized as Record<string, unknown>).client_nif as string) ??
                                  ""}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-right">
                        {doc.normalized?.total_amount != null && (
                          <span className="font-semibold text-foreground">
                            {Number(doc.normalized.total_amount).toLocaleString("es-ES", {
                              style: "currency",
                              currency: "EUR",
                            })}
                          </span>
                        )}
                        {doc.created_at && (
                          <span className="text-xs text-muted">
                            {new Date(doc.created_at).toLocaleDateString("es-ES")}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                  {documents.length > 5 && (
                    <button
                      onClick={() => setTab("documentos")}
                      className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark"
                    >
                      Ver todos ({documents.length})
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                      </svg>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===== DOCUMENTOS ===== */}
      {activeTab === "documentos" && (
        <div>
          {/* Search toolbar */}
          <div className="mb-5 space-y-3">
            {/* Search input */}
            <div className="relative">
              <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar por emisor, cliente, NIF, nº factura, concepto…"
                className="w-full rounded-xl border-0 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm ring-1 ring-black/5 placeholder:text-gray-400 focus:ring-2 focus:ring-brand/30 focus:outline-none"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            {/* Filter row */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Type filter chips */}
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

              <div className="ml-auto flex items-center gap-2">
                {/* Date range */}
                <div className="flex items-center gap-1.5">
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="rounded-lg border-0 bg-white px-2.5 py-1.5 text-xs text-muted shadow-sm ring-1 ring-black/5 focus:ring-2 focus:ring-brand/30 focus:outline-none"
                  />
                  <span className="text-xs text-gray-400">—</span>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="rounded-lg border-0 bg-white px-2.5 py-1.5 text-xs text-muted shadow-sm ring-1 ring-black/5 focus:ring-2 focus:ring-brand/30 focus:outline-none"
                  />
                </div>

                {/* Sort selector */}
                <button
                  onClick={() => {
                    if (sortBy === "date") {
                      if (sortDir === "desc") setSortDir("asc");
                      else { setSortBy("amount"); setSortDir("desc"); }
                    } else {
                      if (sortDir === "desc") setSortDir("asc");
                      else { setSortBy("date"); setSortDir("desc"); }
                    }
                  }}
                  className="flex items-center gap-1 rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-muted shadow-sm ring-1 ring-black/5 hover:bg-gray-50"
                  title={`Ordenar por ${sortBy === "date" ? "fecha" : "importe"} ${sortDir === "desc" ? "↓" : "↑"}`}
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 7.5L7.5 3m0 0L12 7.5M7.5 3v13.5m13.5 0L16.5 21m0 0L12 16.5m4.5 4.5V7.5" />
                  </svg>
                  {sortBy === "date" ? "Fecha" : "Importe"} {sortDir === "desc" ? "↓" : "↑"}
                </button>
              </div>
            </div>

            {/* Active filters summary */}
            {hasActiveFilters && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted">
                  {filteredDocs.length} de {documents.length} documentos
                </span>
                <button
                  onClick={() => { setSearchQuery(""); setTypeFilter(""); setDateFrom(""); setDateTo(""); }}
                  className="text-xs font-medium text-brand hover:text-brand-dark"
                >
                  Limpiar filtros
                </button>
              </div>
            )}
          </div>

          {/* Results */}
          {documents.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
              <svg className="h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <p className="mt-2 text-sm text-muted">No hay documentos procesados aún.</p>
            </div>
          ) : filteredDocs.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
              <svg className="h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <p className="mt-2 text-sm font-medium text-muted">Sin resultados</p>
              <p className="text-xs text-gray-400">Prueba con otros términos o filtros</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredDocs.map((doc) => {
                const n = doc.normalized as Record<string, unknown> | null;
                const issueDate = n?.issue_date ? new Date(String(n.issue_date)) : null;
                return (
                  <div
                    key={doc.doc_hash}
                    className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5 transition-shadow hover:shadow-md"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${DOC_TYPE_COLORS[doc.document_type ?? ""] ?? "bg-gray-50 text-gray-600 ring-gray-200"}`}>
                            {DOC_TYPE_LABELS[doc.document_type ?? ""] ?? doc.document_type ?? "Desconocido"}
                          </span>
                          {!!n?.invoice_number && (
                            <span className="text-xs font-medium text-muted">Nº {String(n.invoice_number)}</span>
                          )}
                          {issueDate && (
                            <span className="text-xs text-gray-400">
                              {issueDate.toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" })}
                            </span>
                          )}
                        </div>
                        <p className="truncate font-medium text-foreground">
                          {doc.filename || doc.doc_hash.slice(0, 12)}
                        </p>
                        {n && (
                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                            {!!n.issuer_name && (
                              <span>
                                <span className="text-gray-400">Emisor:</span>{" "}
                                {String(n.issuer_name)}
                                {!!n.issuer_nif && (
                                  <span className="ml-1 font-mono text-gray-400">({String(n.issuer_nif)})</span>
                                )}
                              </span>
                            )}
                            {!!n.client_name && (
                              <span>
                                <span className="text-gray-400">Cliente:</span>{" "}
                                {String(n.client_name)}
                                {!!n.client_nif && (
                                  <span className="ml-1 font-mono text-gray-400">({String(n.client_nif)})</span>
                                )}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      {n?.total_amount != null && (
                        <span className="shrink-0 text-xl font-bold tracking-tight text-foreground">
                          {Number(n.total_amount).toLocaleString("es-ES", {
                            style: "currency",
                            currency: "EUR",
                          })}
                        </span>
                      )}
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      {doc.review_status && (
                        <span className={`inline-block px-2 py-1 rounded text-xs font-semibold ${
                          doc.review_status === "reviewed"
                            ? "bg-green-100 text-green-800"
                            : "bg-orange-100 text-orange-800"
                        }`}>
                          {doc.review_status === "reviewed" ? "✓ Revisada" : "Pendiente"}
                        </span>
                      )}
                      <Link
                        href={`/dashboard/review/${cuentaId}/${doc.doc_hash}`}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-100 px-3 py-1.5 text-sm font-medium text-indigo-700 transition-colors hover:bg-indigo-200"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Revisar
                      </Link>
                      {doc.has_original && (
                        <button
                          onClick={() => handleViewOriginal(doc.doc_hash)}
                          disabled={downloadingDoc === doc.doc_hash}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand transition-colors hover:bg-brand/20 disabled:opacity-50"
                        >
                          {downloadingDoc === doc.doc_hash ? (
                            <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                            </svg>
                          ) : (
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                            </svg>
                          )}
                          Ver original
                        </button>
                      )}
                      {n && (
                        <details className="group">
                          <summary className="inline-flex cursor-pointer items-center gap-1 text-sm font-medium text-brand hover:text-brand-dark">
                            <svg className="h-3.5 w-3.5 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                            </svg>
                            Ver datos extraídos
                          </summary>
                          <NormalizedDataView data={n} />
                        </details>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ===== CONTACTOS ===== */}
      {activeTab === "contactos" && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold text-foreground">
              Contactos
              <span className="ml-2 text-sm font-normal text-muted">({contacts.length})</span>
            </h3>
            <div className="flex gap-1.5">
              {["", "proveedor", "cliente"].map((f) => (
                <button
                  key={f}
                  onClick={() => setContactFilter(f)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                    contactFilter === f
                      ? "bg-brand text-white shadow-sm"
                      : "bg-gray-100 text-muted hover:bg-gray-200"
                  }`}
                >
                  {f === "" ? "Todos" : f === "proveedor" ? "Proveedores" : "Clientes"}
                </button>
              ))}
            </div>
          </div>

          {/* Contact search */}
          <div className="relative mb-4">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <input
              type="text"
              value={contactSearch}
              onChange={(e) => setContactSearch(e.target.value)}
              placeholder="Buscar contacto por nombre o NIF…"
              className="w-full rounded-xl border-0 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm ring-1 ring-black/5 placeholder:text-gray-400 focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
            {contactSearch && (
              <button
                onClick={() => setContactSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-gray-400 hover:text-gray-600"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {filteredContacts.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
              <svg className="h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
              </svg>
              <p className="mt-2 text-sm text-muted">No hay contactos aún.</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-black/5">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-gray-50/50">
                    <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">Nombre</th>
                    <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">NIF</th>
                    <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">Rol</th>
                    <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted text-right">Docs</th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredContacts.map((c) => (
                    <tr key={c.contacto_id} className="hover:bg-gray-50/50">
                      <td className="px-5 py-4">
                        <Link
                          href={`/dashboard/cuentas/${cuentaId}/contactos/${c.contacto_id}`}
                          className="font-medium text-foreground hover:text-brand"
                        >
                          {c.nombre_fiscal}
                        </Link>
                      </td>
                      <td className="px-5 py-4">
                        {c.tax_id
                          ? <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 font-mono text-xs text-foreground ring-1 ring-black/5">{c.tax_id}</span>
                          : <span className="text-gray-300">—</span>
                        }
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex gap-1.5">
                          {c.roles.map((r) => (
                            <RoleBadge key={r} role={r} />
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-right text-muted">
                        {c.total_documentos}
                      </td>
                      <td className="px-5 py-4">
                        <ConfidenceBadge confidence={c.confidence} source={c.source} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ===== GMAIL ===== */}
      {activeTab === "gmail" && (
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-black/5">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2.5 text-red-500">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-foreground">Conexión Gmail</h3>
          </div>
          {client.gmail_email ? (
            <div className="space-y-3">
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <div className="rounded-lg bg-gray-50 p-3">
                  <dt className="text-xs font-medium text-muted">Cuenta conectada</dt>
                  <dd className="mt-1 font-medium text-foreground">{client.gmail_email}</dd>
                </div>
                <div className="rounded-lg bg-gray-50 p-3">
                  <dt className="text-xs font-medium text-muted">Estado del Watch</dt>
                  <dd className="mt-1">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                        client.gmail_watch_status === "active"
                          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                          : "bg-gray-100 text-gray-500 ring-1 ring-gray-200"
                      }`}
                    >
                      <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                        client.gmail_watch_status === "active" ? "bg-emerald-500" : "bg-gray-400"
                      }`} />
                      {client.gmail_watch_status || "inactivo"}
                    </span>
                  </dd>
                </div>
              </dl>
              {client.gmail_watch_state && (
                <div className="rounded-lg bg-gray-50 p-3 text-sm">
                  <dt className="text-xs font-medium text-muted">History ID</dt>
                  <dd className="mt-1 font-mono text-foreground">
                    {String(client.gmail_watch_state.history_id ?? "—")}
                  </dd>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Gmail no está conectado para esta cuenta. Conecta para recibir documentos automáticamente.
              </p>
              <button
                onClick={async () => {
                  try {
                    const url = await getGmailAuthorizeUrl(cuentaId);
                    window.location.href = url;
                  } catch (e) {
                    setError(
                      e instanceof Error ? e.message : "Error desconocido"
                    );
                  }
                }}
                className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-dark shadow-brand/25"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.86-2.036a4.5 4.5 0 00-1.242-7.244l4.5-4.5a4.5 4.5 0 016.364 6.364l-1.757 1.757" />
                </svg>
                Conectar Gmail
              </button>
            </div>
          )}
        </div>
      )}

      {/* ===== DATOS DE LA CUENTA ===== */}
      {activeTab === "datos" && (
        <DatosTab client={client} cuentaId={cuentaId} />
      )}
    </div>
  );
}


function DatosTab({ client, cuentaId }: { client: { nombre: string; tax_id: string | null; tax_country: string | null; phone_number: string; gmail_email: string | null; min_income: number | null; max_income: number | null }; cuentaId: string }) {
  const router = useRouter();
  const [nombre, setNombre] = useState(client.nombre ?? "");
  const [taxId, setTaxId] = useState(client.tax_id ?? "");
  const [phone, setPhone] = useState(client.phone_number ?? "");
  const [minIncome, setMinIncome] = useState<string>(client.min_income != null ? String(client.min_income) : "");
  const [maxIncome, setMaxIncome] = useState<string>(client.max_income != null ? String(client.max_income) : "");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    setNombre(client.nombre ?? "");
    setTaxId(client.tax_id ?? "");
    setPhone(client.phone_number ?? "");
    setMinIncome(client.min_income != null ? String(client.min_income) : "");
    setMaxIncome(client.max_income != null ? String(client.max_income) : "");
  }, [client.nombre, client.tax_id, client.phone_number, client.min_income, client.max_income]);

  const dirty =
    nombre !== (client.nombre ?? "") ||
    taxId !== (client.tax_id ?? "") ||
    phone !== (client.phone_number ?? "") ||
    (minIncome === "" ? null : Number(minIncome)) !== client.min_income ||
    (maxIncome === "" ? null : Number(maxIncome)) !== client.max_income;

  async function handleSave() {
    setSaving(true);
    try {
      await updateCuenta(cuentaId, {
        nombre: nombre || undefined,
        tax_id: taxId || undefined,
        phone_number: phone || undefined,
        min_income: minIncome === "" ? null : Number(minIncome),
        max_income: maxIncome === "" ? null : Number(maxIncome),
      });
      toast.success("Datos guardados");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteCuenta(cuentaId);
      toast.success("Cuenta eliminada");
      router.push("/dashboard/cuentas");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al eliminar");
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Editable fields */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">Datos de la cuenta</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Nombre</label>
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">NIF / CIF</label>
            <input
              type="text"
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              placeholder="B12345678"
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm font-mono text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Teléfono</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+34 600 000 000"
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Gmail</label>
            <p className="px-3 py-2 text-sm text-muted truncate">{client.gmail_email || "No conectado"}</p>
          </div>
          {client.tax_country && (
            <div>
              <label className="block text-xs font-medium text-muted mb-1">País fiscal</label>
              <p className="px-3 py-2 text-sm text-foreground">{client.tax_country}</p>
            </div>
          )}
        </div>
      </div>

      {/* Income range */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">Rango de ingresos</h3>
        </div>
        <div className="grid grid-cols-2 gap-4 p-5">
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Ingresos mínimos (€)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={minIncome}
              onChange={(e) => setMinIncome(e.target.value)}
              placeholder="Sin mínimo"
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Ingresos máximos (€)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={maxIncome}
              onChange={(e) => setMaxIncome(e.target.value)}
              placeholder="Sin máximo"
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-3 border-t border-border px-5 py-3">
          <button
            onClick={handleSave}
            disabled={!dirty || saving}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      </div>

      {/* Danger zone */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-red-200">
        <div className="border-b border-red-100 px-5 py-3">
          <h3 className="text-sm font-semibold text-red-600">Zona peligrosa</h3>
        </div>
        <div className="p-5">
          {!confirmDelete ? (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Eliminar esta cuenta</p>
                <p className="text-xs text-muted">Se eliminarán todos los documentos y contactos asociados. Esta acción no se puede deshacer.</p>
              </div>
              <button
                onClick={() => setConfirmDelete(true)}
                className="shrink-0 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
              >
                Eliminar cuenta
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg bg-red-50 p-4">
              <svg className="h-5 w-5 shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              <p className="flex-1 text-sm text-red-700">¿Seguro que quieres eliminar esta cuenta y todos sus datos?</p>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:bg-white"
              >
                Cancelar
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? "Eliminando…" : "Confirmar eliminación"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
