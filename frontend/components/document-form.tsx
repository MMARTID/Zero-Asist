"use client";

import { useMemo, useState, useCallback } from "react";
import { validateField } from "@/lib/validation-schemas";
import { toast } from "sonner";

interface DocumentFormProps {
  documentType: string;
  normalizedData: Record<string, unknown>;
  extractedData?: Record<string, unknown>;
  onDocumentTypeChange?: (newType: string) => void;
  onChange?: (data: Record<string, unknown>) => void;
  isReadOnly?: boolean;
}

// Define editable fields per document type based on extraction schemas
const FIELD_CONFIG: Record<string, Array<{ label: string; type: string; required?: boolean }>> = {
  invoice_received: [
    { label: "Emisor", type: "text", required: true },
    { label: "NIF/CIF Emisor", type: "text" },
    { label: "Dirección Emisor", type: "text" },
    { label: "Cliente", type: "text", required: true },
    { label: "NIF/CIF Cliente", type: "text" },
    { label: "Dirección Cliente", type: "text" },
    { label: "Número de Factura", type: "text" },
    { label: "Fecha", type: "date" },
    { label: "Concepto", type: "textarea" },
    { label: "Base Imponible", type: "number" },
    { label: "Total", type: "number", required: true },
    { label: "Moneda", type: "text" },
    { label: "Forma de Pago", type: "text" },
  ],
  invoice_sent: [
    { label: "Emisor", type: "text", required: true },
    { label: "NIF/CIF Emisor", type: "text" },
    { label: "Cliente", type: "text", required: true },
    { label: "NIF/CIF Cliente", type: "text" },
    { label: "Número de Factura", type: "text" },
    { label: "Fecha", type: "date" },
    { label: "Base Imponible", type: "number" },
    { label: "Total", type: "number", required: true },
    { label: "Estado de Pago", type: "text" },
    { label: "Forma de Pago", type: "text" },
  ],
  payment_receipt: [
    { label: "Fecha", type: "date" },
    { label: "Cantidad", type: "number" },
    { label: "Moneda", type: "text" },
    { label: "Método de Pago", type: "text" },
    { label: "Referencia", type: "text" },
    { label: "Emisor", type: "text" },
  ],
  expense_ticket: [
    { label: "Establecimiento", type: "text" },
    { label: "Fecha", type: "date" },
    { label: "Base Imponible", type: "number" },
    { label: "Total", type: "number", required: true },
    { label: "Moneda", type: "text" },
    { label: "Concepto", type: "textarea" },
  ],
  administrative_notice: [
    { label: "Organismo", type: "text" },
    { label: "Tipo", type: "text" },
    { label: "Fecha", type: "date" },
    { label: "Plazo", type: "date" },
    { label: "Número de Expediente", type: "text" },
    { label: "Resumen", type: "textarea" },
  ],
  bank_document: [
    { label: "Banco", type: "text" },
    { label: "Fecha", type: "date" },
    { label: "IBAN", type: "text" },
  ],
  contract: [
    { label: "Fecha", type: "date" },
    { label: "Asunto", type: "text" },
    { label: "Duración", type: "text" },
    { label: "Términos Económicos", type: "textarea" },
    { label: "Firmado", type: "checkbox" },
  ],
  other: [
    { label: "Descripción", type: "textarea" },
  ],
};

// ---- Confidence indicator ----
// Derived purely from extractedData (what Gemini actually found):
//   "found"   → green dot  (AI extracted a non-empty value)
//   "absent"  → gray dot   (AI did not extract this field)
function ConfidenceDot({
  fieldKey,
  extractedData,
}: {
  fieldKey: string;
  extractedData?: Record<string, unknown>;
}) {
  if (!extractedData) return null;
  const raw = extractedData[fieldKey];
  const found = raw !== undefined && raw !== null && raw !== "";
  return (
    <span
      title={found ? "Extraído automáticamente por IA" : "No detectado por IA"}
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
        found
          ? "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200"
          : "bg-gray-100 text-gray-500 ring-1 ring-gray-200"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${found ? "bg-emerald-500" : "bg-gray-400"}`} />
      {found ? "IA" : "—"}
    </span>
  );
}

// Map field labels to normalized_data keys (snake_case)
const FIELD_KEY_MAP: Record<string, string> = {
  "Emisor": "issuer_name",
  "NIF/CIF Emisor": "issuer_nif",
  "Dirección Emisor": "issuer_address",
  "Cliente": "client_name",
  "NIF/CIF Cliente": "client_nif",
  "Dirección Cliente": "client_address",
  "Número de Factura": "invoice_number",
  "Fecha": "issue_date",
  "Concepto": "concept",
  "Base Imponible": "base_amount",
  "Total": "total_amount",
  "Moneda": "currency",
  "Forma de Pago": "payment_method",
  "Estado de Pago": "payment_status",
  "Cantidad": "amount",
  "Método de Pago": "payment_method",
  "Referencia": "operation_reference",
  "Establecimiento": "issuer_name",
  "Organismo": "issuer_name",
  "Tipo": "notice_type",
  "Plazo": "deadline",
  "Número de Expediente": "expedient_number",
  "Resumen": "summary",
  "Banco": "bank_name",
  "IBAN": "iban",
  "Asunto": "subject",
  "Duración": "duration",
  "Términos Económicos": "economic_terms",
  "Firmado": "signed",
  "Descripción": "summary",
};

export default function DocumentForm({
  documentType,
  normalizedData,
  extractedData,
  onDocumentTypeChange,
  onChange,
  isReadOnly = false,
}: DocumentFormProps) {
  const [formData, setFormData] = useState<Record<string, unknown>>(normalizedData);
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const documentTypes = [
    { value: "invoice_received", label: "Factura Recibida" },
    { value: "invoice_sent", label: "Factura Emitida" },
    { value: "payment_receipt", label: "Recibo de Pago" },
    { value: "expense_ticket", label: "Ticket de Gasto" },
    { value: "administrative_notice", label: "Notificación Administrativa" },
    { value: "bank_document", label: "Documento Bancario" },
    { value: "contract", label: "Contrato" },
    { value: "other", label: "Otro" },
  ];

  const fields = useMemo(() => {
    return FIELD_CONFIG[documentType] || FIELD_CONFIG["other"];
  }, [documentType]);

  const handleFieldChange = useCallback(
    (fieldLabel: string, value: unknown) => {
      const key = FIELD_KEY_MAP[fieldLabel] || fieldLabel;

      // Validate field value
      const validation = validateField(documentType, key, value);
      
      if (!validation.valid) {
        setValidationErrors((prev) => ({
          ...prev,
          [key]: validation.error || "Valor inválido",
        }));
        toast.error(`${fieldLabel}: ${validation.error}`);
        return;
      }

      // Clear error for this field if validation passed
      setValidationErrors((prev) => {
        const updated = { ...prev };
        delete updated[key];
        return updated;
      });

      setFormData((prev) => ({ ...prev, [key]: value }));
      setDirtyFields((prev) => new Set([...prev, fieldLabel]));
      onChange?.({ ...formData, [key]: value });
    },
    [formData, onChange, documentType]
  );

  const handleDocumentTypeSelect = (newType: string) => {
    onDocumentTypeChange?.(newType);
    setDirtyFields(new Set());
    setValidationErrors({});
  };

  return (
    <div className="space-y-1">
      {/* Header: Document Type Selector */}
      <div className="sticky top-0 z-10 bg-white pb-4 pt-1">
        <label className="block text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">Tipo de Documento</label>
        <select
          value={documentType}
          onChange={(e) => handleDocumentTypeSelect(e.target.value)}
          disabled={isReadOnly}
          className={`w-full rounded-lg border-2 px-3 py-2.5 text-sm font-semibold transition-all ${
            isReadOnly
              ? "cursor-not-allowed border-gray-200 bg-gray-50 text-gray-500"
              : "border-gray-300 bg-white hover:border-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
          }`}
        >
          {documentTypes.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
      </div>

      {/* Form Fields - Grouped */}
      <div className="space-y-3 pt-2">
        {fields.map((field, idx) => {
          const key = FIELD_KEY_MAP[field.label] || field.label;
          const value = formData[key];
          const isDirtyField = dirtyFields.has(field.label);

          return (
            <div key={idx} className={`rounded-lg border transition-all ${
              isDirtyField 
                ? "border-amber-200 bg-amber-50" 
                : "border-gray-200 bg-white hover:bg-gray-50"
            } p-3`}>
              <div className="flex items-center justify-between gap-3 mb-2">
                <label className="text-sm font-semibold text-foreground">
                  {field.label}
                  {field.required && <span className="ml-0.5 text-red-500">*</span>}
                </label>
                <div className="flex items-center gap-2 shrink-0">
                  {isDirtyField && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                      EDITADO
                    </span>
                  )}
                  <ConfidenceDot fieldKey={key} extractedData={extractedData} />
                </div>
              </div>

              {field.type === "textarea" ? (
                <>
                  <textarea
                    value={String(value || "")}
                    onChange={(e) => handleFieldChange(field.label, e.target.value)}
                    disabled={isReadOnly}
                    rows={2}
                    className={`w-full rounded-md border px-3 py-2 text-sm transition-all ${
                      validationErrors[key]
                        ? "border-red-400 bg-red-50 focus:border-red-500 focus:ring-red-200"
                        : isReadOnly
                          ? "border-gray-200 bg-gray-50 text-gray-500 cursor-not-allowed"
                          : "border-gray-300 bg-white focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                    }`}
                  />
                  {validationErrors[key] && (
                    <p className="text-xs text-red-600 mt-1 font-medium">{validationErrors[key]}</p>
                  )}
                </>
              ) : field.type === "checkbox" ? (
                <>
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(e) => handleFieldChange(field.label, e.target.checked)}
                    disabled={isReadOnly}
                    className={`h-5 w-5 rounded border-gray-300 text-brand focus:ring-2 focus:ring-brand/20 ${
                      isReadOnly ? "cursor-not-allowed opacity-50" : ""
                    }`}
                  />
                  {validationErrors[key] && (
                    <p className="text-xs text-red-600 mt-1 font-medium">{validationErrors[key]}</p>
                  )}
                </>
              ) : field.type === "date" ? (
                <>
                  <input
                    type="date"
                    value={value ? new Date(String(value)).toISOString().split("T")[0] : ""}
                    onChange={(e) => handleFieldChange(field.label, e.target.value)}
                    disabled={isReadOnly}
                    className={`w-full rounded-md border px-3 py-2 text-sm transition-all ${
                      validationErrors[key]
                        ? "border-red-400 bg-red-50 focus:border-red-500 focus:ring-red-200"
                        : isReadOnly
                          ? "border-gray-200 bg-gray-50 text-gray-500 cursor-not-allowed"
                          : "border-gray-300 bg-white focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                    }`}
                  />
                  {validationErrors[key] && (
                    <p className="text-xs text-red-600 mt-1 font-medium">{validationErrors[key]}</p>
                  )}
                </>
              ) : field.type === "number" ? (
                <>
                  <input
                    type="number"
                    step="0.01"
                    value={String(value || "")}
                    onChange={(e) => handleFieldChange(field.label, parseFloat(e.target.value) || null)}
                    disabled={isReadOnly}
                    placeholder="0.00"
                    className={`w-full rounded-md border px-3 py-2 text-sm font-semibold transition-all tabular-nums ${
                      validationErrors[key]
                        ? "border-red-400 bg-red-50 focus:border-red-500 focus:ring-red-200"
                        : isReadOnly
                          ? "border-gray-200 bg-gray-50 text-gray-500 cursor-not-allowed"
                          : "border-gray-300 bg-white focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                    }`}
                  />
                  {validationErrors[key] && (
                    <p className="text-xs text-red-600 mt-1 font-medium">{validationErrors[key]}</p>
                  )}
                </>
              ) : (
                <>
                  <input
                    type="text"
                    value={String(value || "")}
                    onChange={(e) => handleFieldChange(field.label, e.target.value)}
                    disabled={isReadOnly}
                    className={`w-full rounded-md border px-3 py-2 text-sm transition-all ${
                      validationErrors[key]
                        ? "border-red-400 bg-red-50 focus:border-red-500 focus:ring-red-200"
                        : isReadOnly
                          ? "border-gray-200 bg-gray-50 text-gray-500 cursor-not-allowed"
                          : "border-gray-300 bg-white focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                    }`}
                  />
                  {validationErrors[key] && (
                    <p className="text-xs text-red-600 mt-1 font-medium">{validationErrors[key]}</p>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
