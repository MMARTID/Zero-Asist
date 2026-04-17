"use client";

import { redirect } from "next/navigation";

export default function ClientesRedirect() {
  redirect("/dashboard/cuentas");
}
