/**
 * Secure logging utility for production vs development
 * In development: logs to console
 * In production: sends to error tracking service
 */

interface ErrorTracking {
  context: string;
  error: string;
  timestamp: string;
  userAgent?: string;
}

// Initialize Sentry in production (optional - for now just structured logging)
function getErrorTrackerUrl(): string | null {
  // Can be replaced with actual Sentry DSN
  return process.env.NEXT_PUBLIC_ERROR_TRACKING_DSN || null;
}

/**
 * Secure error logging - doesn't expose stack traces to users
 */
export function logError(context: string, error: unknown): void {
  const errorMessage = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error ? error.stack : undefined;

  if (process.env.NODE_ENV === "development") {
    // Development: full stack trace
    console.error(`[${context}]`, error);
  } else {
    // Production: only message, send to tracking
    console.error(`[${context}] ${errorMessage}`);

    // Send to error tracking service
    const errorTracking: ErrorTracking = {
      context,
      error: errorMessage.substring(0, 500), // Truncate to 500 chars
      timestamp: new Date().toISOString(),
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : undefined,
    };

    // Attempt to send to backend for logging
    if (typeof window !== "undefined") {
      // sendBeacon returns boolean, not a promise
      navigator.sendBeacon("/api/logs", JSON.stringify(errorTracking));
    }
  }
}

/**
 * Safe console logging for non-errors
 */
export function logInfo(context: string, message: string, data?: unknown): void {
  if (process.env.NODE_ENV === "development") {
    console.log(`[${context}]`, message, data);
  }
}

/**
 * Parse error from API responses safely
 */
export function parseApiError(error: unknown): string {
  if (error instanceof Error && error.message.includes("HTTP")) {
    return "Error de servidor. Por favor intenta de nuevo.";
  }
  if (error instanceof Error) {
    return error.message.substring(0, 200);
  }
  return "Error inesperado";
}
