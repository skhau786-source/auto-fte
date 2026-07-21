import type { Metadata, Viewport } from "next";
import { GoogleOAuthProvider } from "@react-oauth/google";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1.0,
};

export const metadata: Metadata = {
  title: "Digital FTE - AI-Powered E-Commerce Employee",
  description: "Your AI Digital FTE, working 24/7 for your e-commerce store. Autonomous agent managing catalogs, customers, and revenue growth.",
  keywords: "AI, E-Commerce, Digital Employee, Autonomous Agent, Shopify",
  authors: [{ name: "Digital FTE Team" }],
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%237c3aed'/><text x='50' y='55' font-size='50' font-weight='bold' fill='white' text-anchor='middle'>FTE</text></svg>",
  },
};

const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "1234567890-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if (typeof window !== 'undefined') {
                if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.documentElement.classList.add('dark')
                } else {
                  document.documentElement.classList.remove('dark')
                }
              }
            `,
          }}
        />
      </head>
      <body className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 antialiased">
        <GoogleOAuthProvider clientId={googleClientId}>
          {children}
        </GoogleOAuthProvider>
      </body>
    </html>
  );
}
