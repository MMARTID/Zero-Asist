"use client";

import { Component, ReactNode } from "react";
import { logError } from "@/lib/logger";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * Global error boundary to catch and handle component errors gracefully
 * Prevents entire app crash from component failures
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: { componentStack: string }) {
    // Log error with context
    logError("ErrorBoundary", error);
    logError("ErrorBoundary.componentStack", errorInfo.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100 p-4">
          <div className="w-full max-w-md rounded-lg border border-red-200 bg-white shadow-lg">
            {/* Header */}
            <div className="border-b border-red-200 bg-gradient-to-r from-red-50 to-red-100 px-6 py-4">
              <h2 className="text-lg font-bold text-red-900">Error inesperado</h2>
              <p className="mt-1 text-sm text-red-700">
                Ha ocurrido un problema. Por favor recarga la página.
              </p>
            </div>

            {/* Content */}
            <div className="px-6 py-4">
              {process.env.NODE_ENV === "development" && (
                <div className="mb-4 rounded-md bg-red-50 p-3 text-xs font-mono text-red-800">
                  <p className="font-bold">Detalles (Dev Mode):</p>
                  <p className="mt-1 break-words">{this.state.error?.message}</p>
                </div>
              )}

              <p className="text-sm text-slate-600">
                Por favor intenta recargar la página. Si el problema persiste, contacta con soporte.
              </p>
            </div>

            {/* Actions */}
            <div className="border-t border-red-200 bg-slate-50 px-6 py-4">
              <div className="flex gap-3">
                <button
                  onClick={this.handleReset}
                  className="flex-1 rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-300 transition"
                >
                  Intentar de nuevo
                </button>
                <button
                  onClick={() => window.location.href = "/"}
                  className="flex-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition"
                >
                  Ir a inicio
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
