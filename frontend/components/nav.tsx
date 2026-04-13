"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/dashboard/clientes", label: "Clientes" },
];

export default function Nav() {
  const pathname = usePathname();
  const { signOut } = useAuth();

  return (
    <nav className="flex h-screen w-56 flex-col border-r bg-gray-50 p-4">
      <h1 className="mb-6 text-lg font-bold">Zero Asist</h1>

      <ul className="flex-1 space-y-1">
        {links.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className={`block rounded px-3 py-2 text-sm ${
                pathname === l.href
                  ? "bg-blue-100 font-medium text-blue-700"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>

      <button
        onClick={() => signOut()}
        className="mt-auto rounded px-3 py-2 text-sm text-gray-500 hover:bg-gray-100"
      >
        Cerrar sesión
      </button>
    </nav>
  );
}
