"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useModalParam } from "@/lib/use-modal-param";
import { updateGestoriaProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const SOFTWARE_OPTIONS = [
  {
    id: "holded",
    name: "Holded",
    description: "Software de facturación y gestión contable en la nube",
    icon: "📋",
  },
  {
    id: "A3",
    name: "A3",
    description: "Software de contabilidad profesional",
    icon: "📊",
  },
  {
    id: "sage",
    name: "Sage",
    description: "Solución de gestión empresarial integral",
    icon: "💼",
  },
];

export default function SoftwareSelectorModal() {
  const { isOpen, closeModal } = useModalParam("seleccionar-software");
  const { gestoria } = useAuth();

  const [selectedSoftware, setSelectedSoftware] = useState<string | null>(
    gestoria?.gestoria_software || null
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    if (!selectedSoftware) {
      setError("Por favor selecciona un software");
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      if (gestoria) {
        await updateGestoriaProfile(
          gestoria.nombre,
          gestoria.phone_number,
          selectedSoftware
        );
        
        toast.success("✅ Software actualizado correctamente");
        closeModal();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Error al guardar";
      setError(message);
      toast.error("❌ Error al guardar el software");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && closeModal()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Software Contable</DialogTitle>
          <DialogDescription>
            Selecciona el software que utiliza tu gestoría para una mejor integración
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Software Options */}
          <div className="grid grid-cols-1 gap-3">
            {SOFTWARE_OPTIONS.map((software) => (
              <button
                key={software.id}
                onClick={() => setSelectedSoftware(software.id)}
                className={`rounded-lg border-2 p-4 text-left transition-all ${
                  selectedSoftware === software.id
                    ? "border-brand bg-brand/5"
                    : "border-border hover:border-brand/50 bg-background hover:bg-muted/50"
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-2xl">{software.icon}</span>
                  <div>
                    <h4 className="font-semibold text-foreground">
                      {software.name}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      {software.description}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Error Message */}
          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 border border-red-200">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              onClick={closeModal}
              disabled={isSubmitting}
              className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={isSubmitting || !selectedSoftware}
              className="flex-1 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand/90 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
