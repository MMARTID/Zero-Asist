"use client";

import { useClients, createClient, revalidatePrefix } from "@/lib/api";
import Link from "next/link";
import { FormEvent, useState, useMemo } from "react";
import { toast } from "sonner";

type SortKey = "nombre" | "tax_id" | "gmail_watch_status";
type SortDir = "asc" | "desc";

export default function ClientesPage() {
  const { data, error: swrError, isLoading } = useClients();
  const clients = data?.cuentas ?? [];
  const [error, setError] = useState("");

  // Search + sort
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("nombre");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const filteredClients = useMemo(() => {
    let result = clients;
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (c) =>
          c.nombre.toLowerCase().includes(q) ||
          (c.tax_id?.toLowerCase().includes(q)) ||
          (c.gmail_email?.toLowerCase().includes(q)) ||
          (c.phone_number?.toLowerCase().includes(q))
      );
    }
    return [...result].sort((a, b) => {
      const aVal = (a[sortKey] ?? "") as string;
      const bVal = (b[sortKey] ?? "") as string;
      const cmp = aVal.localeCompare(bVal, "es");
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [clients, search, sortKey, sortDir]);

  // New client form
  const [showForm, setShowForm] = useState(false);
  const [nombre, setNombre] = useState("");
  const [phone, setPhone] = useState("");
  const [taxId, setTaxId] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await createClient(nombre, phone, taxId);
      setNombre("");
      setPhone("");
      setTaxId("");
      setShowForm(false);
      revalidatePrefix("/dashboard");
      toast.success("Cuenta creada correctamente");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al crear cuenta");
    } finally {
      setCreating(false);
    }
  }

  const displayError = error || swrError?.message || "";

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Cuentas</h2>
          <p className="mt-1 text-sm text-muted">
            Gestiona las cuentas de tus clientes
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium shadow-sm ${
            showForm
              ? "bg-gray-100 text-muted hover:bg-gray-200"
              : "bg-brand text-white hover:bg-brand-dark shadow-brand/25"
          }`}
        >
          {showForm ? (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancelar
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              Nueva cuenta
            </>
          )}
        </button>
      </div>

      {displayError && (
        <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600 ring-1 ring-red-100">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {displayError}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="mb-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-black/5"
        >
          <p className="mb-4 text-sm font-medium text-foreground">Nueva cuenta</p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              placeholder="Nombre de la empresa"
              required
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              className="flex-1 rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            />
            <input
              placeholder="NIF / CIF"
              required
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              className="w-full sm:w-40 rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            />
            <input
              type="tel"
              placeholder="Teléfono de contacto"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="flex-1 rounded-lg border border-border bg-white px-3 py-2.5 text-sm placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            />
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
            >
              {creating ? "Creando…" : "Crear"}
            </button>
          </div>
        </form>
      )}

      {isLoading && !data ? (
        <div className="flex h-48 items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="spinner" />
            <p className="text-sm text-muted">Cargando cuentas…</p>
          </div>
        </div>
      ) : clients.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
          <svg className="h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0" />
          </svg>
          <p className="mt-3 text-sm font-medium text-muted">No hay cuentas aún</p>
          <p className="mt-1 text-xs text-gray-400">Crea tu primera cuenta para empezar</p>
        </div>
      ) : (
        <>
          {/* Search bar */}
          <div className="mb-4 relative">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nombre, NIF, email, teléfono…"
              className="w-full rounded-xl border-0 bg-white py-2.5 pl-10 pr-4 text-sm shadow-sm ring-1 ring-black/5 placeholder:text-gray-400 focus:ring-2 focus:ring-brand/30 focus:outline-none"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-gray-400 hover:text-gray-600"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {search && (
            <p className="mb-3 text-xs text-muted">
              {filteredClients.length} de {clients.length} cuentas
            </p>
          )}

          {filteredClients.length === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-black/5">
              <p className="text-sm font-medium text-muted">Sin resultados</p>
              <p className="text-xs text-gray-400">Prueba con otros términos de búsqueda</p>
            </div>
          ) : (
          <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-black/5">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-gray-50/50">
                  <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">
                    <button onClick={() => handleSort("nombre")} className="inline-flex items-center gap-1 hover:text-foreground">
                      Nombre
                      {sortKey === "nombre" && <span>{sortDir === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                  <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">
                    <button onClick={() => handleSort("tax_id")} className="inline-flex items-center gap-1 hover:text-foreground">
                      NIF/CIF
                      {sortKey === "tax_id" && <span>{sortDir === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                  <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">Teléfono</th>
                  <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">Gmail</th>
                  <th className="px-5 py-3.5 text-xs font-semibold uppercase tracking-wider text-muted">
                    <button onClick={() => handleSort("gmail_watch_status")} className="inline-flex items-center gap-1 hover:text-foreground">
                      Estado
                      {sortKey === "gmail_watch_status" && <span>{sortDir === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredClients.map((c) => (
                  <tr key={c.cuenta_id} className="hover:bg-gray-50/50">
                    <td className="px-5 py-4">
                      <Link
                        href={`/dashboard/cuentas/${c.cuenta_id}`}
                        className="font-medium text-foreground hover:text-brand"
                      >
                        {c.nombre}
                      </Link>
                    </td>
                    <td className="px-5 py-4 font-mono text-xs text-muted">{c.tax_id || <span className="text-gray-300">—</span>}</td>
                    <td className="px-5 py-4 text-muted">{c.phone_number || <span className="text-gray-300">—</span>}</td>
                    <td className="px-5 py-4 text-muted">
                      {c.gmail_email || <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                          c.gmail_watch_status === "active"
                            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                            : "bg-gray-50 text-gray-500 ring-1 ring-gray-200"
                        }`}
                      >
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                          c.gmail_watch_status === "active" ? "bg-emerald-500" : "bg-gray-400"
                        }`} />
                        {c.gmail_watch_status || "sin conectar"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </>
      )}
    </div>
  );
}
