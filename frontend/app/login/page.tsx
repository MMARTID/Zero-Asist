"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const { user, loading, signIn, gestoria, gestoriaLoading } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && !gestoriaLoading && user) {
      router.replace(gestoria?.onboarding_complete ? "/dashboard" : "/onboarding");
    }
  }, [user, loading, gestoria, gestoriaLoading, router]);

  async function handleGoogleSignIn() {
    setError("");
    setSubmitting(true);
    try {
      await signIn();
    } catch (e) {
      console.error("Google sign-in error:", e);
      setError("No se pudo iniciar sesión con Google");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="w-full max-w-sm">
        {/* Brand card */}
        <div className="rounded-2xl bg-white p-8 shadow-lg ring-1 ring-black/5">
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white text-2xl font-bold shadow-md shadow-brand/25">
              Z
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Zero Asist
            </h1>
            <p className="mt-1 text-sm text-muted">
              Gestión automatizada de documentos
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

          <button
            onClick={handleGoogleSignIn}
            disabled={submitting}
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-foreground shadow-sm hover:bg-gray-50 hover:shadow disabled:opacity-50"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            {submitting ? "Entrando…" : "Continuar con Google"}
          </button>

          <p className="mt-6 text-center text-xs text-muted">
            Inicia sesión con tu cuenta de Google para acceder
          </p>
        </div>
      </div>
    </div>
  );
}
