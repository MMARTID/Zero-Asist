"use client";

import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";

export interface NormalizedContactData {
  nombre_fiscal?: string | null;
  tax_id?: string | null;
  phone_number?: string | null;
  email_contacto?: string | null;
  direccion_fiscal?: string | null;
  codigo_postal?: string | null;
  confidence?: Record<string, number>;
}

export interface ImportNotification {
  id: string;
  status: "analyzing" | "review" | "error" | "creating" | "completed";
  created_count: number;
  error_count: number;
  total_count: number;
  errors?: Array<{ index: number; message: string }>;
  normalizedData?: {
    headers: string[];
    rows: NormalizedContactData[];
  };
  selectedRows?: Set<number>;
  created_at: string;
  completed_at?: string;
}

interface ImportsContextType {
  imports: ImportNotification[];
  addImport: (notification: ImportNotification) => void;
  updateImport: (id: string, updates: Partial<ImportNotification>) => void;
  dismissImport: (id: string) => void;
  clearImports: () => void;
  getImport: (id: string) => ImportNotification | undefined;
  selectedImportId: string | null;
  setSelectedImportId: (id: string | null) => void;
}

const ImportsContext = createContext<ImportsContextType | undefined>(undefined);

// Helper functions for localStorage serialization
function serializeImports(imports: ImportNotification[]): string {
  return JSON.stringify(
    imports.map((imp) => ({
      ...imp,
      selectedRows: imp.selectedRows ? Array.from(imp.selectedRows) : undefined,
    }))
  );
}

function deserializeImports(data: string): ImportNotification[] {
  try {
    const parsed: unknown[] = JSON.parse(data);
    return parsed.map((imp) => {
      const impRecord = (imp as Record<string, unknown>) || {};
      return {
        id: String(impRecord.id || ""),
        status: (impRecord.status as ImportNotification["status"]) || "error",
        created_count: Number(impRecord.created_count) || 0,
        error_count: Number(impRecord.error_count) || 0,
        total_count: Number(impRecord.total_count) || 0,
        created_at: String(impRecord.created_at || ""),
        errors: Array.isArray(impRecord.errors) ? impRecord.errors : undefined,
        normalizedData: (impRecord.normalizedData as any) || undefined,
        selectedRows: Array.isArray(impRecord.selectedRows) 
          ? new Set(impRecord.selectedRows as number[]) 
          : undefined,
        completed_at: impRecord.completed_at ? String(impRecord.completed_at) : undefined,
      } as ImportNotification;
    });
  } catch {
    return [];
  }
}

export function ImportsProvider({ children }: { children: React.ReactNode }) {
  const { gestoria } = useAuth();
  const storageKey = gestoria?.gestoria_id ? `imports_state_${gestoria.gestoria_id}` : null;

  const [imports, setImports] = useState<ImportNotification[]>([]);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);

  // Load from localStorage when gestoria is known (scoped per gestoria ID)
  useEffect(() => {
    if (!storageKey || storageKey === loadedKey) return;
    try {
      const stored = localStorage.getItem(storageKey);
      setImports(stored ? deserializeImports(stored) : []);
    } catch (error) {
      console.error("Failed to load imports from localStorage:", error);
      setImports([]);
    }
    setLoadedKey(storageKey);
  }, [storageKey, loadedKey]);

  // Persist to localStorage whenever imports change (only after initial load)
  useEffect(() => {
    if (!storageKey || loadedKey !== storageKey) return;
    try {
      localStorage.setItem(storageKey, serializeImports(imports));
    } catch (error) {
      console.error("Failed to save imports to localStorage:", error);
    }
  }, [imports, storageKey, loadedKey]);

  const addImport = useCallback((notification: ImportNotification) => {
    setImports((prev) => [notification, ...prev]);
  }, []);

  const updateImport = useCallback((id: string, updates: Partial<ImportNotification>) => {
    setImports((prev) =>
      prev.map((imp) => (imp.id === id ? { ...imp, ...updates } : imp))
    );
  }, []);

  const dismissImport = useCallback((id: string) => {
    setImports((prev) => prev.filter((imp) => imp.id !== id));
  }, []);

  const clearImports = useCallback(() => {
    setImports([]);
  }, []);

  const getImport = useCallback((id: string) => {
    return imports.find((imp) => imp.id === id);
  }, [imports]);

  return (
    <ImportsContext.Provider value={{ imports, addImport, updateImport, dismissImport, clearImports, getImport, selectedImportId, setSelectedImportId }}>
      {children}
    </ImportsContext.Provider>
  );
}

export function useImports() {
  const context = useContext(ImportsContext);
  if (!context) {
    throw new Error("useImports must be used within ImportsProvider");
  }
  return context;
}
