import AuthGuard from "@/components/auth-guard";
import Nav from "@/components/nav";
import MobileHeader from "@/components/mobile-header";
import { SidebarProvider } from "@/lib/sidebar-context";
import type { ReactNode } from "react";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <SidebarProvider>
        <div className="flex h-screen bg-background">
          <Nav />
          <div className="flex flex-1 flex-col overflow-hidden">
            <MobileHeader />
            <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">{children}</main>
          </div>
        </div>
      </SidebarProvider>
    </AuthGuard>
  );
}
