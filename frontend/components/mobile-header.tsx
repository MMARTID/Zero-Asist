"use client";

import { useSidebar } from "@/lib/sidebar-context";

export default function MobileHeader() {
  const { toggle } = useSidebar();

  return (
    <header className="flex items-center border-b border-border bg-white px-4 py-3 lg:hidden">
      <button
        onClick={toggle}
        className="rounded-lg p-2 text-muted hover:bg-gray-100"
        aria-label="Abrir menú"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        </svg>
      </button>
      <div className="ml-3 flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand text-white text-xs font-bold">
          Z
        </div>
        <span className="text-sm font-bold tracking-tight text-foreground">Zero Asist</span>
      </div>
    </header>
  );
}
