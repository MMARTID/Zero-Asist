import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
    ],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // Prevent MIME-sniffing attacks
          { key: "X-Content-Type-Options", value: "nosniff" },
          
          // Prevent clickjacking attacks
          { key: "X-Frame-Options", value: "DENY" },
          
          // Content Security Policy - restrict resource loading
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; " +
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net https://apis.google.com; " +
              "style-src 'self' 'unsafe-inline'; " +
              "img-src 'self' data: https:; " +
              "font-src 'self' data:; " +
              "connect-src 'self' http://localhost:8000 https://*.firebaseio.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://gmail.googleapis.com https://www.googleapis.com https://apis.google.com; " +
              "frame-src 'self' https://*.firebaseapp.com; " +
              "frame-ancestors 'none'; " +
              "base-uri 'self'; " +
              "form-action 'self';",
          },
          
          // Force HTTPS and cache HSTS policy
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          
          // Disable referrer information
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          
          // Restrict feature permissions
          {
            key: "Permissions-Policy",
            value:
              "geolocation=(), " +
              "microphone=(), " +
              "camera=(), " +
              "payment=(), " +
              "usb=(), " +
              "magnetometer=(), " +
              "gyroscope=(), " +
              "accelerometer=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
