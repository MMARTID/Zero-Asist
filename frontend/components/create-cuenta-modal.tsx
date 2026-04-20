"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useModalParam } from "@/lib/use-modal-param";
import { useImports } from "@/lib/use-imports";
import { createClient, revalidatePrefix, analyzeImport } from "@/lib/api";
import { parseFile } from "@/lib/file-parser";

type Tab = "import" | "manual";

interface NormalizedContact {
  nombre_fiscal: string;
  tax_id: string;
  phone_number: string;
  email_contacto?: string;
  direccion_fiscal?: string;
  codigo_postal?: string;
  confidence?: Record<string, number>;
}

export default function CreateCuentaModal() {
  const router = useRouter();
  const { isOpen, closeModal } = useModalParam("crear-cuenta");
  const { addImport, updateImport, getImport } = useImports();

  // Tab state
  const [activeTab, setActiveTab] = useState<Tab>("import");

  // Manual creation form
  const [nombre, setNombre] = useState("");
  const [phone, setPhone] = useState("");
  const [taxId, setTaxId] = useState("");
  const [creating, setCreating] = useState(false);
  const [manualError, setManualError] = useState("");

  // Import flow state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importError, setImportError] = useState("");
  const [currentImportId, setCurrentImportId] = useState<string | null>(null);
  const [analysisToastId, setAnalysisToastId] = useState<string | number | null>(null);

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      // Always allow closing
      closeModal();

      // Check if still analyzing - show notification
      const isAnalyzing = currentImportId && getImport(currentImportId)?.status === "analyzing";
      if (isAnalyzing) {
        toast.info("El análisis continúa en background. Ver notificación cuando termine.");
      }

      // Close any active toast
      if (analysisToastId) {
        toast.dismiss(analysisToastId);
        setAnalysisToastId(null);
      }

      // Reset local state
      setSelectedFile(null);
      setImportError("");
      setCurrentImportId(null);
    }
  };

  const handleCreateManual = async (e: React.FormEvent) => {
    e.preventDefault();
    setManualError("");
    setCreating(true);

    try {
      await createClient(nombre, phone, taxId);
      setNombre("");
      setPhone("");
      setTaxId("");
      revalidatePrefix("/dashboard");
      toast.success("Cuenta creada correctamente");
      closeModal();
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Error al crear cuenta";
      setManualError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const handleFileSelect = async (file: File | null) => {
    if (!file) {
      setSelectedFile(null);
      return;
    }

    setImportError("");
    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleAnalyzeFile = () => {
    if (!selectedFile) {
      setImportError("Por favor selecciona un archivo");
      return;
    }

    // Prevent double-click if already analyzing
    if (currentImportId) {
      const currentImport = getImport(currentImportId);
      if (currentImport?.status === "analyzing") {
        return;
      }
    }

    const importId = `import_${Date.now()}`;
    setCurrentImportId(importId);

    // Create notification in sidebar
    addImport({
      id: importId,
      status: "analyzing",
      created_count: 0,
      error_count: 0,
      total_count: 0,
      created_at: new Date().toISOString(),
    });

    // Show toast
    const toastId = toast.info("Analizando CSV. Puedes cerrar el modal con ESC");
    setAnalysisToastId(toastId);

    // Parse and analyze in background WITHOUT await
    (async () => {
      try {
        // Parse file on frontend
        const parsed = await parseFile(selectedFile);

        // Send to backend for LLM analysis
        const analyzed = await analyzeImport(parsed.headers, parsed.rows);

        const normalized = {
          headers: analyzed.mapping ? Object.values(analyzed.mapping) : parsed.headers,
          rows: analyzed.normalized_rows,
        };

        // Select all rows by default
        const allRows: Set<number> = new Set(analyzed.normalized_rows.map((_, i) => i));

        // Close the analysis toast
        if (analysisToastId) {
          toast.dismiss(analysisToastId);
          setAnalysisToastId(null);
        }

        // Update notification with data and "review" status
        updateImport(importId, {
          status: "review",
          total_count: analyzed.normalized_rows.length,
          normalizedData: normalized,
          selectedRows: allRows,
        });

        toast.success("Análisis completado. Abriendo revisión…");

        // Close modal and navigate to review page
        closeModal();
        setTimeout(() => {
          router.push(`/dashboard/importaciones/${importId}`);
        }, 500);
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Error al analizar archivo";
        setImportError(errorMsg);

        // Close the analysis toast
        if (analysisToastId) {
          toast.dismiss(analysisToastId);
          setAnalysisToastId(null);
        }

        toast.error(errorMsg);

        // Update notification to error
        updateImport(importId, {
          status: "error",
          error_count: 1,
          total_count: 1,
          errors: [{ index: 0, message: errorMsg }],
          completed_at: new Date().toISOString(),
        });
      }
    })();
  };

  const handleRetryAnalysis = () => {
    setImportError("");
    handleAnalyzeFile();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Crear Cuenta</DialogTitle>
          <DialogDescription>
            Añade una nueva cuenta a tu gestoría manualmente o importando desde un archivo
          </DialogDescription>
        </DialogHeader>

        {/* Tab buttons */}
        <div className="flex gap-2 border-b border-border">
          <button
            onClick={() => {
              setActiveTab("import");
              setManualError("");
            }}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "import"
                ? "border-b-2 border-brand text-brand"
                : "text-muted hover:text-foreground"
            }`}
          >
            Importar
          </button>
          <button
            onClick={() => {
              setActiveTab("manual");
              setImportError("");
            }}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === "manual"
                ? "border-b-2 border-brand text-brand"
                : "text-muted hover:text-foreground"
            }`}
          >
            Crear manualmente
          </button>
        </div>

        {/* Content */}
        <div className="mt-4">
          {/* Manual Tab */}
          {activeTab === "manual" && (
            <form onSubmit={handleCreateManual} className="space-y-4">
              {manualError && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
                  <svg
                    className="h-4 w-4 shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                    />
                  </svg>
                  {manualError}
                </div>
              )}

              <div>
                <label className="text-sm font-medium text-foreground">Nombre de la empresa</label>
                <input
                  type="text"
                  placeholder="Ej: Acme Corp S.L."
                  required
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-foreground">NIF / CIF</label>
                  <input
                    type="text"
                    placeholder="Ej: ES12345678A"
                    required
                    value={taxId}
                    onChange={(e) => setTaxId(e.target.value.toUpperCase())}
                    className="mt-1.5 w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground">Teléfono</label>
                  <input
                    type="tel"
                    placeholder="Ej: +34 600 123 456"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-gray-50 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {creating ? "Creando…" : "Crear cuenta"}
                </button>
              </div>
            </form>
          )}

          {/* Import Tab - Upload ONLY */}
          {activeTab === "import" && (
            <div className="space-y-4">
              {importError && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
                  <svg
                    className="h-4 w-4 shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                    />
                  </svg>
                  {importError}
                </div>
              )}

              {(() => {
                const isAnalyzing = !!(currentImportId && getImport(currentImportId)?.status === "analyzing");
                return isAnalyzing ? (
                  <div className="rounded-lg bg-blue-50 p-4 border border-blue-100 flex items-start gap-3">
                    <svg className="h-5 w-5 animate-spin text-blue-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
                    </svg>
                    <div>
                      <p className="font-medium text-blue-900">Analizando archivo en segundo plano...</p>
                      <p className="text-xs text-blue-700 mt-1">La IA está procesando tus datos. Esto puede tomar algunos segundos. Puedes cerrar este modal.</p>
                    </div>
                  </div>
                ) : null;
              })()}

              <div
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                className="rounded-lg border-2 border-dashed border-border bg-gray-50 p-8 text-center transition-colors hover:border-brand hover:bg-blue-50/30"
              >
                <svg
                  className="mx-auto h-12 w-12 text-gray-300"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <p className="mt-3 text-sm font-medium text-foreground">
                  Arrastra un archivo o{" "}
                  <label className="cursor-pointer text-brand hover:underline">
                    selecciona uno
                    <input
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                      className="hidden"
                    />
                  </label>
                </p>
                <p className="mt-1 text-xs text-muted">CSV o Excel (máx 5MB, 500 filas)</p>
              </div>

              {selectedFile && (
                <div className="flex items-center justify-between rounded-lg bg-blue-50 p-3 ring-1 ring-blue-100">
                  <div className="flex items-center gap-2">
                    <svg className="h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <div>
                      <p className="text-sm font-medium text-blue-900">{selectedFile.name}</p>
                      <p className="text-xs text-blue-700">
                        {(selectedFile.size / 1024).toFixed(2)} KB
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={!!(currentImportId && getImport(currentImportId)?.status === "analyzing")}
                    onClick={() => handleFileSelect(null)}
                    className="text-xs text-blue-600 hover:text-blue-700 hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Quitar
                  </button>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-4">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-gray-50 transition-colors"
                >
                  Cancelar
                </button>
                {(() => {
                  const isAnalyzing = !!(currentImportId && getImport(currentImportId)?.status === "analyzing");
                  const hasError = !!importError && !isAnalyzing;

                  if (hasError) {
                    return (
                      <button
                        onClick={handleRetryAnalysis}
                        className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 transition-colors"
                      >
                        Reintentar análisis
                      </button>
                    );
                  }

                  return (
                    <button
                      onClick={handleAnalyzeFile}
                      disabled={!selectedFile || isAnalyzing}
                      className="rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {isAnalyzing ? (
                        <span className="flex items-center gap-2">
                          <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
                          </svg>
                          Analizando…
                        </span>
                      ) : (
                        "Analizar archivo"
                      )}
                    </button>
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
