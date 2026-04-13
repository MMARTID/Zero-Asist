"use client";

import { getClients, createClient, type ClientSummary } from "@/lib/api";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

export default function ClientesPage() {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // New client form
  const [showForm, setShowForm] = useState(false);
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [creating, setCreating] = useState(false);

  function load() {
    setLoading(true);
    getClients()
      .then((res) => setClients(res.clientes))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await createClient(nombre, email);
      setNombre("");
      setEmail("");
      setShowForm(false);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al crear cliente");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Clientes</h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {showForm ? "Cancelar" : "Nuevo cliente"}
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded bg-red-50 p-2 text-sm text-red-600">
          {error}
        </p>
      )}

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="mb-6 flex gap-3 rounded border bg-white p-4"
        >
          <input
            placeholder="Nombre"
            required
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            className="flex-1 rounded border px-3 py-2 text-sm"
          />
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="flex-1 rounded border px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {creating ? "Creando…" : "Crear"}
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-gray-500">Cargando…</p>
      ) : clients.length === 0 ? (
        <p className="text-gray-500">No hay clientes aún.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 font-medium">Nombre</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Gmail</th>
                <th className="px-4 py-3 font-medium">Watch</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {clients.map((c) => (
                <tr key={c.cliente_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/dashboard/clientes/${c.cliente_id}`}
                      className="font-medium text-blue-600 hover:underline"
                    >
                      {c.nombre}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{c.email}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {c.gmail_email || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        c.gmail_watch_status === "active"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {c.gmail_watch_status || "sin conectar"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
