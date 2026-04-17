"use client";

import { useGestoriaProfile, updateGestoriaSettings } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useState, useEffect } from "react";
import { toast } from "sonner";

export default function ConfiguracionPage() {
  const { user } = useAuth();
  const { data: profile, isLoading } = useGestoriaProfile();

  const [nombre, setNombre] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setNombre(profile.nombre);
      setPhone(profile.phone_number);
    }
  }, [profile]);

  const dirty =
    profile != null &&
    (nombre !== profile.nombre || phone !== profile.phone_number);

  async function handleSave() {
    if (!nombre.trim()) {
      toast.error("El nombre no puede estar vacío");
      return;
    }
    setSaving(true);
    try {
      await updateGestoriaSettings(nombre.trim(), phone.trim());
      toast.success("Configuración guardada");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  if (isLoading || !profile) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">Configuración</h2>
        <div className="animate-pulse space-y-4">
          <div className="h-48 rounded-xl bg-white shadow-sm ring-1 ring-black/5" />
          <div className="h-32 rounded-xl bg-white shadow-sm ring-1 ring-black/5" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-foreground">Configuración</h2>

      {/* Gestoría profile */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">Datos de la gestoría</h3>
        </div>
        <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Nombre de la gestoría
            </label>
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              className="w-full rounded-lg border-0 bg-gray-50 px-3 py-2 text-sm text-foreground ring-1 ring-black/5 placeholder:text-gray-400 focus:bg-white focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Teléfono / WhatsApp
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+34 600 000 000"
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

      {/* Account info (read-only) */}
      <div className="rounded-xl bg-white shadow-sm ring-1 ring-black/5">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">Tu cuenta</h3>
        </div>
        <dl className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium text-muted">Email</dt>
            <dd className="mt-1 text-sm text-foreground">{user?.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted">Nombre</dt>
            <dd className="mt-1 text-sm text-foreground">{user?.displayName ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted">ID Gestoría</dt>
            <dd className="mt-1 font-mono text-xs text-muted">{profile.gestoria_id}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
