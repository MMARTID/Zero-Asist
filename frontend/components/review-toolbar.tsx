"use client";

import { toast } from "sonner";
import type { ReviewQueueItem } from "@/lib/api";

interface ReviewToolbarProps {
  isReadOnly?: boolean;
  isSaving?: boolean;
  isReviewing?: boolean;
  hasChanges?: boolean;
  nextItem?: ReviewQueueItem | null;
  onSave?: () => Promise<void>;
  onReview?: () => Promise<void>;
  onReviewNext?: () => Promise<void>;
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export default function ReviewToolbar({
  isReadOnly = false,
  isSaving = false,
  isReviewing = false,
  hasChanges = false,
  nextItem,
  onSave,
  onReview,
  onReviewNext,
}: ReviewToolbarProps) {
  const handleSave = async () => {
    try {
      await onSave?.();
    } catch {
      toast.error("Error al guardar cambios");
    }
  };

  const handleReview = async () => {
    try {
      await onReview?.();
    } catch {
      toast.error("Error al marcar como revisado");
    }
  };

  const handleReviewNext = async () => {
    try {
      await onReviewNext?.();
    } catch {
      toast.error("Error al revisar y continuar");
    }
  };

  const busy = isSaving || isReviewing;

  if (isReadOnly) {
    return (
      <div className="border-t border-gray-200 bg-emerald-50 px-4 py-3 text-center">
        <p className="text-xs font-medium text-emerald-700">
          ✓ Documento revisado y bloqueado para edición
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Next document hint - elegant */}
      {nextItem && (
        <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2 ring-1 ring-indigo-200">
          <svg className="h-3.5 w-3.5 shrink-0 text-indigo-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-indigo-900">
              {nextItem.filename || nextItem.doc_hash.slice(0, 14)}
            </p>
            <p className="truncate text-[11px] text-indigo-700 opacity-75">
              {nextItem.cuenta_nombre}
            </p>
          </div>
        </div>
      )}

      {/* Action buttons grid */}
      <div className="grid grid-cols-3 gap-2">
        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={!hasChanges || busy}
          title="Guardar cambios (⌘S)"
          className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-xs font-semibold transition-all active:scale-95 ${
            hasChanges && !busy
              ? "bg-amber-500 text-white hover:bg-amber-600 shadow-sm hover:shadow-md"
              : "bg-gray-200 text-gray-400 cursor-not-allowed"
          }`}
        >
          {isSaving ? <Spinner /> : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 19H2v-1a6 6 0 0112 0v1h3m-6-4a3 3 0 100-6 3 3 0 000 6zm6-8a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
          <span className="hidden sm:inline">Guardar</span>
        </button>

        {/* Mark reviewed */}
        <button
          onClick={handleReview}
          disabled={busy}
          title="Marcar como revisada sin avanzar"
          className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 text-white px-3 py-2.5 text-xs font-semibold transition-all hover:bg-emerald-700 active:scale-95 disabled:opacity-50 shadow-sm hover:shadow-md"
        >
          {isReviewing ? <Spinner /> : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
          <span className="hidden sm:inline">Revisar</span>
        </button>

        {/* Review & Next — Primary CTA */}
        <button
          onClick={handleReviewNext}
          disabled={busy}
          title="Revisar y pasar al siguiente (⌘↵)"
          className="flex items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-600 to-blue-600 text-white px-3 py-2.5 text-xs font-semibold transition-all hover:shadow-lg hover:from-indigo-700 hover:to-blue-700 active:scale-95 disabled:opacity-50 shadow-md"
        >
          {isReviewing ? <Spinner /> : (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              <span className="hidden sm:inline">Siguiente</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
