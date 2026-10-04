import "./globals.css";
import { LanguageProvider } from "./lib/LanguageContext";
import { LanguageSelectorModal } from "./components/LanguageSelectorModal";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { ChatbotLoader } from "./components/ChatbotLoader";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const googleClientId =
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "YOUR_GOOGLE_CLIENT_ID";

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <GoogleOAuthProvider clientId={googleClientId}>
          <LanguageProvider>
            <LanguageSelectorModal />
            {children}
            <ChatbotLoader />
          </LanguageProvider>
        </GoogleOAuthProvider>
      </body>
    </html>
  );
}
