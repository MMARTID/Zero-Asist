"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { toast } from "sonner";
import { logError } from "@/lib/logger";
import {
  getDocument,
  getReviewQueue,
  updateDocument,
  reviewDocument,
  type DocumentDetail,
  type ReviewQueueItem,
} from "@/lib/api";
import DocumentForm from "@/components/document-form";
import ReviewToolbar from "@/components/review-toolbar";

const PDFViewer = dynamic(() => import("@/components/pdf-viewer"), { ssr: false });

export default function ReviewPage() {
  const params = useParams();
  const router = useRouter();
  const cuentaId = params.cuentaId as string;
  const docHash = params.docHash as string;

  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [pdfData, setPdfData] = useState<{ data: Uint8Array } | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [documentType, setDocumentType] = useState<string>("");
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  // Queue for prev/next navigation
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [queueIndex, setQueueIndex] = useState(-1);

  // Load document + queue in parallel on mount
  useEffect(() => {
    loadDocument();
    loadQueue();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cuentaId, docHash]);

  // Load PDF once document loaded
  useEffect(() => {
    if (document?.has_original) loadPDF();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document?.doc_hash]);

  const loadDocument = async () => {
    try {
      setLoading(true);
      const doc = await getDocument(cuentaId, docHash);
      setDocument(doc);
      setFormData(doc.normalized || {});
      setDocumentType(doc.document_type || "other");
      setHasChanges(false);
    } catch (error) {
      logError("Error loading document", error);
      toast.error("Error al cargar el documento");
    } finally {
      setLoading(false);
    }
  };

  const loadQueue = async () => {
    try {
      const res = await getReviewQueue(200);
      setQueue(res.queue);
      const idx = res.queue.findIndex(
        (item) => item.cuenta_id === cuentaId && item.doc_hash === docHash
      );
      setQueueIndex(idx);
    } catch {
      // queue is optional, silent fail
    }
  };

  const loadPDF = async () => {
    try {
      setPdfLoading(true);
      const user = await import("@/lib/firebase").then((m) => m.getFirebaseAuth().currentUser);
      if (!user) throw new Error("Not authenticated");
      const token = await user.getIdToken();
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/dashboard/cuentas/${cuentaId}/documentos/${docHash}/original`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const arrayBuffer = await res.arrayBuffer();
        setPdfData({ data: new Uint8Array(arrayBuffer) });
      }
    } catch (error) {
      logError("Error loading PDF", error);
      toast.error("Error al cargar el PDF");
    } finally {
      setPdfLoading(false);
    }
  };

  const navigateTo = (item: ReviewQueueItem) => {
    router.push(`/dashboard/review/${item.cuenta_id}/${item.doc_hash}`);
  };

  const prevItem = queueIndex > 0 ? queue[queueIndex - 1] : null;
  const nextItem = queueIndex >= 0 && queueIndex < queue.length - 1 ? queue[queueIndex + 1] : null;

  const handleFormChange = (data: Record<string, unknown>) => {
    setFormData(data);
    setHasChanges(true);
  };

  const handleDocumentTypeChange = (newType: string) => {
    setDocumentType(newType);
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!document) return;
    try {
      setIsSaving(true);
      await updateDocument(cuentaId, docHash, {
        normalized_data: formData,
        document_type: documentType !== document.document_type ? documentType : undefined,
      });
      setHasChanges(false);
      toast.success("Cambios guardados");
    } catch (error) {
      logError("Error saving", error);
      throw error;
    } finally {
      setIsSaving(false);
    }
  };

  const handleReview = async () => {
    if (!document) return;
    try {
      setIsReviewing(true);
      await reviewDocument(cuentaId, docHash, {});
      setDocument((prev) => (prev ? { ...prev, review_status: "reviewed" } : null));
      // Remove from local queue
      setQueue((q) => q.filter((i) => !(i.cuenta_id === cuentaId && i.doc_hash === docHash)));
      toast.success("Documento marcado como revisado");
    } catch (error) {
      logError("Error reviewing", error);
      throw error;
    } finally {
      setIsReviewing(false);
    }
  };

  const handleReviewNext = async () => {
    if (!document) return;
    try {
      setIsReviewing(true);
      // Save pending changes first
      if (hasChanges) {
        await updateDocument(cuentaId, docHash, {
          normalized_data: formData,
          document_type: documentType !== document.document_type ? documentType : undefined,
        });
      }
      const result = await reviewDocument(cuentaId, docHash, {});
      // Remove current from local queue
      const updatedQueue = queue.filter((i) => !(i.cuenta_id === cuentaId && i.doc_hash === docHash));
      setQueue(updatedQueue);
      const target = result.next ?? (updatedQueue.length > 0 ? updatedQueue[0] : null);
      if (target) {
        router.push(`/dashboard/review/${target.cuenta_id}/${target.doc_hash}`);
      } else {
        toast.success("¡Sin más documentos pendientes!");
        router.push("/dashboard");
      }
    } catch (error) {
      logError("Error reviewing and navigating", error);
      throw error;
    } finally {
      setIsReviewing(false);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const inInput = () => {
      const el = window.document.activeElement;
      return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement;
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      // ← → navigate queue (not when typing in a field)
      if (!inInput()) {
        if (e.key === "ArrowLeft" && prevItem) {
          e.preventDefault();
          navigateTo(prevItem);
          return;
        }
        if (e.key === "ArrowRight" && nextItem) {
          e.preventDefault();
          navigateTo(nextItem);
          return;
        }
      }
      // ⌘/Ctrl+S: Save
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (document?.review_status !== "reviewed" && hasChanges) handleSave();
        return;
      }
      // ⌘/Ctrl+Enter: Review & next
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        if (document?.review_status !== "reviewed") handleReviewNext();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document, hasChanges, prevItem, nextItem]);

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="spinner" />
          <p className="text-sm text-muted">Cargando documento…</p>
        </div>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center bg-background">
        <p className="mb-4 text-sm text-muted">Documento no encontrado</p>
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90"
        >
          ← Volver
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full flex-col bg-white">
      {/* Top Bar - Refined */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3 shadow-sm">
        <div className="flex items-center gap-4 min-w-0 flex-1">
          {/* Back button */}
          <button
            onClick={() => router.push("/dashboard")}
            className="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-all"
            title="Volver al dashboard"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          {/* Navigation pills */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => prevItem && navigateTo(prevItem)}
              disabled={!prevItem}
              title="Anterior (←)"
              className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-25 disabled:cursor-not-allowed disabled:hover:bg-transparent transition-all"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            
            {queue.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gray-100 text-xs font-semibold text-gray-600 tabular-nums">
                <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.566.034-1.08.16-1.539.34m-5.403 1.712A2.25 2.25 0 006.75 12m0 0h12m-8.25 6h4.5" />
                </svg>
                {queueIndex >= 0 ? queueIndex + 1 : "—"}/{queue.length}
              </span>
            )}
            
            <button
              onClick={() => nextItem && navigateTo(nextItem)}
              disabled={!nextItem}
              title="Siguiente (→)"
              className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-25 disabled:cursor-not-allowed disabled:hover:bg-transparent transition-all"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>

        {/* Center: Document info */}
        <div className="flex-1 px-6 min-w-0 text-center">
          <p className="truncate text-sm font-semibold text-foreground">
            {document.filename || document.doc_hash.slice(0, 20)}
          </p>
          <p className="truncate text-xs text-gray-500">{document.cuenta_id}</p>
        </div>

        {/* Right: Status + hints */}
        <div className="flex items-center gap-3 shrink-0">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all ${
              document.review_status === "reviewed"
                ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                : "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
            }`}
          >
            {document.review_status === "reviewed" ? (
              <>
                <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
                </svg>
                Revisado
              </>
            ) : (
              <>
                <span className="h-2 w-2 rounded-full bg-amber-400" />
                Pendiente
              </>
            )}
          </span>

          <div className="hidden xl:flex items-center gap-1.5 text-[11px] text-gray-400 font-mono">
            <kbd className="rounded bg-gray-100 px-1.5 py-0.5 border border-gray-300">⌘S</kbd>
            <span>•</span>
            <kbd className="rounded bg-gray-100 px-1.5 py-0.5 border border-gray-300">⌘↵</kbd>
          </div>
        </div>
      </div>

      {/* Main Content: Split View */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: PDF Viewer (58%) */}
        <div className="flex-1 overflow-hidden bg-gray-50 border-r border-gray-200">
          {pdfData ? (
            <PDFViewer file={pdfData} filename={document.filename ?? ""} loading={pdfLoading} />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
              <div className="flex flex-col items-center gap-3 text-gray-400">
                <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 7.5h-.75A2.25 2.25 0 004.5 9.75v10.5A2.25 2.25 0 006.75 22.5h10.5A2.25 2.25 0 0019.5 20.25V9.75a2.25 2.25 0 00-2.25-2.25h-.75m-6 3.75l2.25-2.25m0 0l2.25 2.25m-2.25-2.25v6.75m6-6h.008v.008h-.008v-.008zm-6 0h.008v.008h-.008v-.008z" />
                </svg>
                <p className="text-sm">No hay documento original disponible</p>
              </div>
            </div>
          )}
        </div>

        {/* Right: Form + Toolbar (42%) */}
        <div className="w-5/12 overflow-hidden flex flex-col bg-white">
          {/* Form */}
          <div className="flex-1 overflow-y-auto p-5">
            <DocumentForm
              documentType={documentType}
              normalizedData={formData}
              extractedData={document.extracted_data ?? undefined}
              onDocumentTypeChange={handleDocumentTypeChange}
              onChange={handleFormChange}
              isReadOnly={document.review_status === "reviewed"}
            />
          </div>

          {/* Toolbar - Sticky bottom */}
          <div className="border-t border-gray-200 bg-white p-4 shadow-lg">
            <ReviewToolbar
              isReadOnly={document.review_status === "reviewed"}
              isSaving={isSaving}
              isReviewing={isReviewing}
              hasChanges={hasChanges}
              nextItem={nextItem}
              onSave={handleSave}
              onReview={handleReview}
              onReviewNext={handleReviewNext}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
