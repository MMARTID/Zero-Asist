"use client";

import { useParams } from "next/navigation";
import { redirect } from "next/navigation";

export default function ClienteRedirect() {
  const { clienteId } = useParams<{ clienteId: string }>();
  redirect(`/dashboard/cuentas/${clienteId}`);
}
