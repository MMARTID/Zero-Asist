"use client";

import { getStats, type Stats } from "@/lib/api";
import { useEffect, useState } from "react";

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return <p className="text-red-600">Error: {error}</p>;
  }

  if (!stats) {
    return <p className="text-gray-500">Cargando estadísticas…</p>;
  }

  const cards = [
    { label: "Clientes", value: stats.total_clients },
    { label: "Gmail conectado", value: stats.connected_gmail },
    { label: "Watches activos", value: stats.active_watches },
    { label: "Documentos", value: stats.total_documents },
  ];

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Dashboard</h2>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-lg border bg-white p-4 shadow-sm"
          >
            <p className="text-sm text-gray-500">{c.label}</p>
            <p className="mt-1 text-3xl font-semibold">{c.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
