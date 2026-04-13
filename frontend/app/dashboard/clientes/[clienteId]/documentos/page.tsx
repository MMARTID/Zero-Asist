"use client";

import { getDocuments, type Document } from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function DocumentosPage() {
  const { clienteId } = useParams<{ clienteId: string }>();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (clienteId) {
      getDocuments(clienteId)
        .then((res) => setDocuments(res.documentos))
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }
  }, [clienteId]);

  return (
    <div>
      <Link
        href={`/dashboard/clientes/${clienteId}`}
        className="text-sm text-blue-600 hover:underline"
      >
        ← Volver al cliente
      </Link>
      <h2 className="mt-2 mb-6 text-2xl font-bold">Documentos</h2>

      {error && (
        <p className="mb-4 rounded bg-red-50 p-2 text-sm text-red-600">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-gray-500">Cargando…</p>
      ) : documents.length === 0 ? (
        <p className="text-gray-500">No hay documentos procesados aún.</p>
      ) : (
        <div className="space-y-3">
          {documents.map((doc) => (
            <div
              key={doc.doc_hash}
              className="rounded-lg border bg-white p-4"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">
                    {doc.filename || doc.doc_hash.slice(0, 12)}
                  </p>
                  <p className="text-sm text-gray-500">
                    Tipo:{" "}
                    <span className="font-medium">
                      {doc.document_type || "desconocido"}
                    </span>
                  </p>
                  {doc.created_at && (
                    <p className="text-xs text-gray-400">
                      {new Date(doc.created_at).toLocaleString("es-ES")}
                    </p>
                  )}
                </div>
              </div>

              {doc.normalized && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm text-blue-600">
                    Ver datos extraídos
                  </summary>
                  <pre className="mt-2 overflow-auto rounded bg-gray-50 p-3 text-xs">
                    {JSON.stringify(doc.normalized, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
