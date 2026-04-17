"use client";

import { useParams } from "next/navigation";
import { redirect } from "next/navigation";

export default function DocumentosRedirect() {
  const { clienteId } = useParams<{ clienteId: string }>();
  redirect(`/dashboard/cuentas/${clienteId}?tab=documentos`);
}
