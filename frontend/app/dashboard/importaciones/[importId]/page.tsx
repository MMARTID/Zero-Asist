"use client";

import { useParams, useRouter } from "next/navigation";
import { useImports } from "@/lib/use-imports";
import { bulkCreateClients, revalidatePrefix } from "@/lib/api";
import { useState, useEffect } from "react";
import Link from "next/link";
import { toast } from "sonner";

interface NormalizedContact {
  nombre_fiscal: string;
  tax_id: string;
  phone_number: string;
  email_contacto?: string;
  direccion_fiscal?: string;
  codigo_postal?: string;
  confidence?: Record<string, number>;
}

export default function ImportReviewPage() {
  const params = useParams<{ importId: string }>();
  const router = useRouter();
  const { getImport, updateImport, dismissImport } = useImports();
  
  const importId = params.importId;
  const importData = getImport(importId);
  
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [normalizedData, setNormalizedData] = useState<{
    headers: string[];
    rows: NormalizedContact[];
  } | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  // Hydrate state from import data
  useEffect(() => {
    if (importData?.normalizedData) {
      const typedData = importData.normalizedData as any;
      setNormalizedData(typedData);
      const rowsToSelect = (importData.selectedRows 
        ? (importData.selectedRows as Set<number>)
        : new Set(typedData.rows.map((_: any, i: number) => i))) as Set<number>;
      setSelectedRows(rowsToSelect);
    }
  }, [importData]);

  if (!importData) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/cuentas"
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Volver a Cuentas
        </Link>
        <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
          <svg className="h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="mt-3 text-sm font-medium text-muted">Importación no encontrada</p>
          <p className="mt-1 text-xs text-gray-400">La importación ha expirado o fue eliminada</p>
        </div>
      </div>
    );
  }

  if (!normalizedData) {
    return (
      <div className="space-y-6">
        <Link
          href="/dashboard/cuentas"
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-brand"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Volver a Cuentas
        </Link>
        <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
          <div className="spinner" />
          <p className="mt-3 text-sm text-muted">Cargando datos de importación…</p>
        </div>
      </div>
    );
  }

  const isFieldUncertain = (
    value: string | undefined | null,
    confidence: Record<string, number> | undefined,
    field: string
  ): boolean => {
    if (!value || value.trim() === "") return true;
    if (confidence && confidence[field] !== undefined) {
      return confidence[field] < 0.7;
    }
    return false;
  };

  const getConfidenceColor = (confidence: number | undefined): string => {
    if (!confidence) return "text-gray-500";
    if (confidence >= 0.85) return "text-emerald-600";
    if (confidence >= 0.7) return "text-blue-600";
    if (confidence >= 0.5) return "text-amber-600";
    return "text-red-600";
  };

  const getConfidenceLabel = (confidence: number | undefined): string => {
    if (!confidence) return "Sin valor";
    if (confidence >= 0.85) return `Muy confiable (${(confidence * 100).toFixed(0)}%)`;
    if (confidence >= 0.7) return `Confiable (${(confidence * 100).toFixed(0)}%)`;
    if (confidence >= 0.5) return `Baja confianza (${(confidence * 100).toFixed(0)}%)`;
    return `No confiable (${(confidence * 100).toFixed(0)}%)`;
  };

  const updateRowField = (rowIdx: number, field: keyof NormalizedContact, value: string) => {
    if (!normalizedData) return;
    const updatedRows = [...normalizedData.rows];
    updatedRows[rowIdx] = {
      ...updatedRows[rowIdx],
      [field]: value || null,
    };
    setNormalizedData({
      ...normalizedData,
      rows: updatedRows,
    });
  };

  const toggleRowSelection = (index: number) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedRows(newSelected);
    updateImport(importId, { selectedRows: newSelected });
  };

  const toggleAllRows = () => {
    if (selectedRows.size === normalizedData.rows.length) {
      setSelectedRows(new Set());
      updateImport(importId, { selectedRows: new Set() });
    } else {
      const all = new Set(normalizedData.rows.map((_, i) => i));
      setSelectedRows(all);
      updateImport(importId, { selectedRows: all });
    }
  };

  const handleBulkCreate = async () => {
    if (selectedRows.size === 0) {
      setError("Por favor selecciona al menos una fila");
      return;
    }

    const rowsToCreate = Array.from(selectedRows).map((i) => normalizedData.rows[i]);
    setCreating(true);
    setError("");

    updateImport(importId, {
      status: "creating",
      created_count: 0,
      error_count: 0,
      total_count: rowsToCreate.length,
    });

    try {
      const result = await bulkCreateClients(rowsToCreate);
      
      updateImport(importId, {
        status: "completed",
        created_count: result.created,
        error_count: result.skipped,
        total_count: rowsToCreate.length,
        completed_at: new Date().toISOString(),
      });

      revalidatePrefix("/dashboard");
      const skippedMsg = result.skipped > 0 ? `, ${result.skipped} omitido${result.skipped !== 1 ? "s" : ""} por duplicado` : "";
      toast.success(`Se crearon ${result.created} cuenta${result.created !== 1 ? "s" : ""} correctamente${skippedMsg}`);
      
      // Eliminar notificación del sidebar después de completar exitosamente
      dismissImport(importId);
      
      setTimeout(() => {
        router.push("/dashboard/cuentas");
      }, 1000);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Error desconocido";
      setError(errorMsg);
      
      updateImport(importId, {
        status: "error",
        created_count: 0,
        error_count: rowsToCreate.length,
        completed_at: new Date().toISOString(),
      });

      toast.error(errorMsg);
    } finally {
      setCreating(false);
    }
  };

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
          Volver a Cuentas
        </Link>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-foreground">Revisar importación</h2>
        <p className="mt-1 text-sm text-muted">
          Verifica y edita los datos antes de crear las cuentas
        </p>
      </div>

      {/* Error alert */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {error}
        </div>
      )}

      {/* Info alert */}
      <div className="rounded-lg bg-blue-50 p-4 border border-blue-100 flex items-start gap-3">
        <svg className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
        </svg>
        <div>
          <p className="font-medium text-blue-900">Celdas destacadas en ámbar</p>
          <p className="text-xs text-blue-700 mt-1">Los campos sin datos o con baja confianza (IA &lt;70%) están marcados. Puedes editarlos directamente.</p>
        </div>
      </div>

      {/* Selection info */}
      <div className="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3 ring-1 ring-black/5">
        <p className="text-sm text-muted">
          <strong>{selectedRows.size}</strong> de <strong>{normalizedData.rows.length}</strong> filas seleccionadas
        </p>
        <button
          onClick={toggleAllRows}
          className="text-xs text-brand hover:underline font-medium"
        >
          {selectedRows.size === normalizedData.rows.length ? "Deseleccionar todas" : "Seleccionar todas"}
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border ring-1 ring-black/5 overflow-hidden bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-gray-50/50">
                <th className="px-4 py-3 text-left w-12">
                  <input
                    type="checkbox"
                    checked={selectedRows.size === normalizedData.rows.length}
                    onChange={toggleAllRows}
                    className="rounded border-border cursor-pointer"
                  />
                </th>
                <th className="px-4 py-3 text-left font-semibold text-foreground text-xs uppercase tracking-wider">
                  <span className="flex items-center gap-1">Nombre <span className="text-red-500">*</span></span>
                </th>
                <th className="px-4 py-3 text-left font-semibold text-foreground text-xs uppercase tracking-wider border-l border-border">
                  <span className="flex items-center gap-1">NIF/CIF <span className="text-red-500">*</span></span>
                </th>
                <th className="px-4 py-3 text-left font-semibold text-foreground text-xs uppercase tracking-wider border-l border-border">
                  <span className="flex items-center gap-1">Teléfono <span className="text-red-500">*</span></span>
                </th>
                <th className="px-4 py-3 text-left font-semibold text-muted text-xs uppercase tracking-wider border-l border-border">Email</th>
                <th className="px-4 py-3 text-left font-semibold text-muted text-xs uppercase tracking-wider border-l border-border">Dirección</th>
                <th className="px-4 py-3 text-left font-semibold text-muted text-xs uppercase tracking-wider border-l border-border">Código Postal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {normalizedData.rows.map((row, idx) => (
                <tr
                  key={idx}
                  className={`hover:bg-blue-50/30 ${
                    selectedRows.has(idx) ? "bg-blue-50" : ""
                  }`}
                >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selectedRows.has(idx)}
                      onChange={() => toggleRowSelection(idx)}
                      className="rounded border-border cursor-pointer"
                    />
                  </td>
                  <td className={`px-4 py-3 border-r border-border ${
                    isFieldUncertain(row.nombre_fiscal, row.confidence, "nombre_fiscal")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        value={row.nombre_fiscal || ""}
                        onChange={(e) => updateRowField(idx, "nombre_fiscal", e.target.value)}
                        className={`flex-1 px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                          isFieldUncertain(row.nombre_fiscal, row.confidence, "nombre_fiscal")
                            ? "text-amber-900 font-medium"
                            : "text-foreground"
                        }`}
                      />
                      {row.confidence?.nombre_fiscal !== undefined && (
                        <span
                          className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${getConfidenceColor(
                            row.confidence.nombre_fiscal
                          )} flex-shrink-0`}
                          title={getConfidenceLabel(row.confidence.nombre_fiscal)}
                        >
                          {(row.confidence.nombre_fiscal * 100).toFixed(0).charAt(0)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className={`px-4 py-3 border-r border-border ${
                    isFieldUncertain(row.tax_id, row.confidence, "tax_id")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <input
                      type="text"
                      value={row.tax_id || ""}
                      onChange={(e) => updateRowField(idx, "tax_id", e.target.value)}
                      className={`w-full px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                        isFieldUncertain(row.tax_id, row.confidence, "tax_id")
                          ? "text-amber-900 font-medium"
                          : "text-foreground"
                      }`}
                    />
                  </td>
                  <td className={`px-4 py-3 border-r border-border ${
                    isFieldUncertain(row.phone_number, row.confidence, "phone_number")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <input
                      type="text"
                      value={row.phone_number || ""}
                      onChange={(e) => updateRowField(idx, "phone_number", e.target.value)}
                      className={`w-full px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                        isFieldUncertain(row.phone_number, row.confidence, "phone_number")
                          ? "text-amber-900 font-medium"
                          : "text-foreground"
                      }`}
                    />
                  </td>
                  <td className={`px-4 py-3 border-r border-border ${
                    isFieldUncertain(row.email_contacto, row.confidence, "email_contacto")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <input
                      type="text"
                      value={row.email_contacto || ""}
                      onChange={(e) => updateRowField(idx, "email_contacto", e.target.value)}
                      className={`w-full px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                        isFieldUncertain(row.email_contacto, row.confidence, "email_contacto")
                          ? "text-amber-900 font-medium"
                          : "text-foreground"
                      }`}
                    />
                  </td>
                  <td className={`px-4 py-3 border-r border-border ${
                    isFieldUncertain(row.direccion_fiscal, row.confidence, "direccion_fiscal")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <input
                      type="text"
                      value={row.direccion_fiscal || ""}
                      onChange={(e) => updateRowField(idx, "direccion_fiscal", e.target.value)}
                      className={`w-full px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                        isFieldUncertain(row.direccion_fiscal, row.confidence, "direccion_fiscal")
                          ? "text-amber-900 font-medium"
                          : "text-foreground"
                      }`}
                    />
                  </td>
                  <td className={`px-4 py-3 ${
                    isFieldUncertain(row.codigo_postal, row.confidence, "codigo_postal")
                      ? "bg-amber-50 ring-1 ring-amber-200"
                      : "hover:bg-gray-50"
                  }`}>
                    <input
                      type="text"
                      value={row.codigo_postal || ""}
                      onChange={(e) => updateRowField(idx, "codigo_postal", e.target.value)}
                      className={`w-full px-2 py-1 rounded border-0 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-brand/50 ${
                        isFieldUncertain(row.codigo_postal, row.confidence, "codigo_postal")
                          ? "text-amber-900 font-medium"
                          : "text-foreground"
                      }`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center justify-between gap-3 border-t border-border pt-6">
        <Link
          href="/dashboard/cuentas"
          className="rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-gray-50 transition-colors"
        >
          Cancelar
        </Link>
        <button
          onClick={handleBulkCreate}
          disabled={selectedRows.size === 0 || creating}
          className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {creating ? (
            <span className="flex items-center gap-2">
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
              </svg>
              Creando {selectedRows.size} cuenta{selectedRows.size !== 1 ? "s" : ""}…
            </span>
          ) : (
            `Crear ${selectedRows.size} cuenta${selectedRows.size !== 1 ? "s" : ""}`
          )}
        </button>
      </div>
    </div>
  );
}
