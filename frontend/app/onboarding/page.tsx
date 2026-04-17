"use client";

import { useAuth } from "@/lib/auth-context";
import { updateGestoriaProfile } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function OnboardingPage() {
  const { user, loading, gestoria, gestoriaLoading, refreshGestoria } = useAuth();
  const router = useRouter();

  const [nombre, setNombre] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Pre-fill nombre from auto-registration
  useEffect(() => {
    if (gestoria && !nombre) {
      setNombre(gestoria.nombre || "");
    }
  }, [gestoria, nombre]);

  // Redirect: not authenticated → login
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  // Redirect: already onboarded → dashboard
  useEffect(() => {
    if (!gestoriaLoading && gestoria?.onboarding_complete) {
      router.replace("/dashboard");
    }
  }, [gestoria, gestoriaLoading, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedNombre = nombre.trim();
    const trimmedPhone = phone.trim();

    if (!trimmedNombre) {
      setError("El nombre de la gestoría es obligatorio");
      return;
    }
    if (!trimmedPhone) {
      setError("El número de WhatsApp Business es obligatorio");
      return;
    }

    setSubmitting(true);
    try {
      await updateGestoriaProfile(trimmedNombre, trimmedPhone);
      await refreshGestoria();
      router.replace("/dashboard");
    } catch (err) {
      console.error("Onboarding error:", err);
      setError("No se pudo guardar. Inténtalo de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || gestoriaLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="spinner" />
          <p className="text-sm text-muted">Cargando…</p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="w-full max-w-md">
        <div className="rounded-2xl bg-white p-8 shadow-lg ring-1 ring-black/5">
          {/* Header */}
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white text-2xl font-bold shadow-md shadow-brand/25">
              Z
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Configura tu gestoría
            </h1>
            <p className="mt-1 text-sm text-muted">
              Solo necesitamos un par de datos para empezar
            </p>
          </div>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
              <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Nombre de la gestoría */}
            <div>
              <label htmlFor="nombre" className="mb-1.5 block text-sm font-medium text-foreground">
                Nombre de la gestoría
              </label>
              <input
                id="nombre"
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Ej: Gestoría López & Asociados"
                className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-foreground shadow-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
              />
            </div>

            {/* WhatsApp Business */}
            <div>
              <label htmlFor="phone" className="mb-1.5 block text-sm font-medium text-foreground">
                Número WhatsApp Business
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+34 600 000 000"
                className="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-foreground shadow-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
              />
              <p className="mt-1.5 text-xs text-muted">
                Este número se usará para enviar enlaces a tus clientes por WhatsApp
              </p>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white shadow-md shadow-brand/25 hover:bg-brand/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? "Guardando…" : "Continuar"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
