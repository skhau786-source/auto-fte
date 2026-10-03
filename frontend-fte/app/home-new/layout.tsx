import { LanguageProvider } from "../lib/LanguageContext";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>;
}
