"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback } from "react";

export function useModalParam(modalName: string) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const isOpen = searchParams.get("modal") === modalName;
  const importId = searchParams.get("importId");

  const openModal = useCallback((options?: { importId?: string }) => {
    const params = new URLSearchParams(searchParams);
    params.set("modal", modalName);
    if (options?.importId) {
      params.set("importId", options.importId);
    }
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  }, [router, pathname, searchParams, modalName]);

  const closeModal = useCallback(() => {
    router.back();
  }, [router]);

  return {
    isOpen,
    openModal,
    closeModal,
    importId,
  };
}
