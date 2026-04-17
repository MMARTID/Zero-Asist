"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Link from "next/link";

export default function LandingPage() {
  const { user, loading, gestoria, gestoriaLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading || gestoriaLoading) return;
    if (user) {
      router.replace(gestoria?.onboarding_complete ? "/dashboard" : "/onboarding");
    }
  }, [user, loading, gestoria, gestoriaLoading, router]);

  // Authenticated user — show spinner while redirecting
  if (user) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="spinner" />
          <p className="text-sm text-muted">Redirigiendo…</p>
        </div>
      </div>
    );
  }

  if (loading) return null;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="flex flex-col items-center text-center px-6">
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand text-white text-3xl font-bold shadow-lg shadow-brand/25">
          Z
        </div>
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          Zero Asist
        </h1>
        <p className="mt-3 max-w-md text-lg text-muted">
          Gestión automatizada de documentos para tu gestoría
        </p>
        <Link
          href="/login"
          className="mt-8 inline-flex items-center gap-2 rounded-xl bg-brand px-6 py-3 text-sm font-semibold text-white shadow-md shadow-brand/25 hover:bg-brand/90 transition-colors"
        >
          Iniciar sesión
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
          </svg>
        </Link>
      </div>
    </div>
  );
}
