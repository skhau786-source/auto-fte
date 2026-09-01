"use client";

import React from "react";
import { Globe } from "lucide-react";
import { LOCALES, useTranslation } from "@/app/lib/i18n";

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useTranslation();

  return (
    <label className={`flex items-center gap-1.5 ${className}`}>
      <Globe className="w-4 h-4 text-slate-400" />
      <span className="sr-only">{t("common.language")}</span>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as typeof locale)}
        aria-label={t("common.language")}
        className="text-xs font-semibold text-slate-600 bg-transparent border-none outline-none cursor-pointer hover:text-violet-600 transition-colors"
      >
        {LOCALES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.nativeLabel}
          </option>
        ))}
      </select>
    </label>
  );
}
