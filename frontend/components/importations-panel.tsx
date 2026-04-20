import { useImports, type ImportNotification } from "@/lib/use-imports";
import { useModalParam } from "@/lib/use-modal-param";

function formatTime(isoStr: string | null): string {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 2) return "ahora mismo";
  if (mins < 60) return `hace ${mins} min`;
  if (hours < 24) return `hace ${hours} h`;
  if (days < 30) return `hace ${days} d`;
  return new Date(isoStr).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

function ImportRow({ 
  notification, 
  onDismiss,
  onSelectAndOpen,
}: { 
  notification: ImportNotification; 
  onDismiss: (id: string) => void;
  onSelectAndOpen: (id: string) => void;
}) {
  const isError = notification.status === "error";
  const isAnalyzing = notification.status === "analyzing";
  const isReview = notification.status === "review";
  const isCreating = notification.status === "creating";

  const bgColor = isError ? "bg-red-50 hover:bg-red-100/60" : isAnalyzing ? "bg-blue-50 hover:bg-blue-100/60" : isReview ? "bg-amber-50 hover:bg-amber-100/60" : isCreating ? "bg-blue-50 hover:bg-blue-100/60" : "bg-emerald-50 hover:bg-emerald-100/60";
  const iconBg = isError ? "bg-red-100" : isAnalyzing ? "bg-blue-100" : isReview ? "bg-amber-100" : isCreating ? "bg-blue-100" : "bg-emerald-100";
  const iconColor = isError ? "text-red-600" : isAnalyzing ? "text-blue-600" : isReview ? "text-amber-600" : isCreating ? "text-blue-600" : "text-emerald-600";
  const statusText = isError ? "Error" : isAnalyzing ? "Analizando..." : isReview ? "Pendiente" : isCreating ? "Creando..." : "Completado";

  return (
    <div 
      onClick={() => onSelectAndOpen(notification.id)}
      className={`group flex cursor-pointer items-start gap-4 rounded-xl px-4 py-3.5 transition-colors ${bgColor}`}
    >
      <div className="flex flex-1 items-start gap-4">
        {/* Status dot */}
        <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
          {isAnalyzing ? (
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : isError ? (
            <svg className={`h-4 w-4 ${iconColor}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className={`h-4 w-4 ${iconColor}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${
              isError ? "bg-red-200 text-red-800" : isAnalyzing ? "bg-blue-200 text-blue-800" : "bg-emerald-200 text-emerald-800"
            }`}>
              {statusText}
            </span>
            <span className="text-sm font-medium text-foreground">
              {isAnalyzing ? "Analizando archivo..." : isReview ? "Verificar y crear" : isCreating ? "Creando contactos..." : isError ? `Error en importación` : `Importación completada`}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
            <span>
              {isError ? (
                `${notification.error_count} de ${notification.total_count} contactos fallaron`
              ) : isAnalyzing ? (
                `Procesando ${notification.total_count} contacto${notification.total_count !== 1 ? "s" : ""}...`
              ) : isReview ? (
                `${notification.total_count} contacto${notification.total_count !== 1 ? "s" : ""} listo${notification.total_count !== 1 ? "s" : ""} para crear • Haz click para continuar`
              ) : isCreating ? (
                `Creando ${notification.total_count} contactos...`
              ) : (
                `Se crearon ${notification.created_count} de ${notification.total_count} contacto${notification.total_count !== 1 ? "s" : ""}`
              )}
            </span>
            {notification.error_count > 0 && !isAnalyzing && (
              <>
                <span>·</span>
                <span className="text-red-600 font-medium">{notification.error_count} error{notification.error_count !== 1 ? "es" : ""}</span>
              </>
            )}
          </div>
        </div>

        {/* Date + arrow */}
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
          {formatTime(notification.created_at)}
          <svg className="h-4 w-4 text-muted" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </div>
      </div>

      {/* Dismiss button */}
      <button
        onClick={(e) => { e.stopPropagation(); onDismiss(notification.id); }}
        title="Descartar notificación"
        className="mt-0.5 shrink-0 rounded-lg p-1.5 text-gray-400 opacity-0 transition-opacity hover:bg-gray-100 hover:text-gray-600 group-hover:opacity-100"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export default function ImportationsPanel() {
  const { imports, dismissImport } = useImports();
  const { openModal } = useModalParam("crear-cuenta");

  const handleSelectAndOpen = (importId: string) => {
    openModal({ importId });
  };

  if (imports.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <svg className="h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-foreground">Importaciones</h3>
          <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-800">
            {imports.length}
          </span>
        </div>
      </div>

      {/* Body */}
      <div>
        <div className="divide-y divide-border">
          {imports.map((imp) => (
            <ImportRow 
              key={imp.id} 
              notification={imp} 
              onDismiss={dismissImport}
              onSelectAndOpen={handleSelectAndOpen}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
