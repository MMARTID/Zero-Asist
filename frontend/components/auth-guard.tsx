"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

interface AuthGuardProps {
  children: ReactNode;
  requireOnboarding?: boolean;
}

export default function AuthGuard({ children, requireOnboarding = true }: AuthGuardProps) {
  const { user, loading, gestoria, gestoriaLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (requireOnboarding && !loading && !gestoriaLoading && user && gestoria && !gestoria.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [requireOnboarding, user, loading, gestoria, gestoriaLoading, router]);

  if (loading || (requireOnboarding && gestoriaLoading)) {
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
  if (requireOnboarding && gestoria && !gestoria.onboarding_complete) return null;

  return <>{children}</>;
}
