"use client";

import { getClient, getGmailAuthorizeUrl, type ClientDetail } from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function ClienteDetailPage() {
  const { clienteId } = useParams<{ clienteId: string }>();
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (clienteId) {
      getClient(clienteId)
        .then(setClient)
        .catch((e) => setError(e.message));
    }
  }, [clienteId]);

  if (error) return <p className="text-red-600">Error: {error}</p>;
  if (!client) return <p className="text-gray-500">Cargando…</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/dashboard/clientes"
          className="text-sm text-blue-600 hover:underline"
        >
          ← Volver a clientes
        </Link>
        <h2 className="mt-2 text-2xl font-bold">{client.nombre}</h2>
        <p className="text-gray-500">{client.email}</p>
      </div>

      {/* Gmail status */}
      <div className="rounded-lg border bg-white p-4">
        <h3 className="mb-3 font-semibold">Gmail</h3>

        {client.gmail_email ? (
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-gray-500">Cuenta:</span>{" "}
              {client.gmail_email}
            </p>
            <p>
              <span className="text-gray-500">Watch:</span>{" "}
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                  client.gmail_watch_status === "active"
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {client.gmail_watch_status || "inactivo"}
              </span>
            </p>
            {client.gmail_watch_state && (
              <p>
                <span className="text-gray-500">History ID:</span>{" "}
                {String(client.gmail_watch_state.history_id ?? "—")}
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">
              Gmail no conectado para este cliente.
            </p>
            <button
              onClick={async () => {
                try {
                  const url = await getGmailAuthorizeUrl(clienteId);
                  window.location.href = url;
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Error desconocido");
                }
              }}
              className="inline-block rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Conectar Gmail
            </button>
          </div>
        )}
      </div>

      {/* Documents link */}
      <div className="rounded-lg border bg-white p-4">
        <h3 className="mb-3 font-semibold">Documentos</h3>
        <Link
          href={`/dashboard/clientes/${clienteId}/documentos`}
          className="text-sm text-blue-600 hover:underline"
        >
          Ver documentos procesados →
        </Link>
      </div>
    </div>
  );
}
