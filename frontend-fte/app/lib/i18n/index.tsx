"use client";

/**
 * Lightweight i18n for the Phase 3 "Multi-language" requirement.
 *
 * Why not next-intl / a [locale] route segment: this app is a single
 * client-rendered page (app/page.tsx) that switches views by React
 * state, not by URL — there are no per-page routes to localize.
 * Restructuring routing to add locale segments would touch the entire
 * app for a roadmap item that only asks for a language-selection
 * mechanism and translated Phase 3 UI. A plain React context with
 * JSON-style dictionaries covers that without a new framework
 * dependency or a routing rewrite, and any component elsewhere in the
 * app can adopt it later via useTranslation() without extra wiring.
 *
 * Falls back to English for any key missing from a non-English
 * dictionary, and for a `locale` value it doesn't recognize (e.g. a
 * stale localStorage value from an older build) — never throws, never
 * renders a raw key to the user.
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en, { type TranslationKey } from "./locales/en";
import es from "./locales/es";

export type Locale = "en" | "es";

export const LOCALES: { code: Locale; label: string; nativeLabel: string }[] = [
  { code: "en", label: "English", nativeLabel: "English" },
  { code: "es", label: "Spanish", nativeLabel: "Español" },
];

const DEFAULT_LOCALE: Locale = "en";
const STORAGE_KEY = "digitalfte_locale";

const dictionaries: Record<Locale, Partial<Record<TranslationKey, string>>> = { en, es };

type Vars = Record<string, string | number>;

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (match, key) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : match
  );
}

function isLocale(value: string | null): value is Locale {
  return value === "en" || value === "es";
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, vars?: Vars) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (isLocale(stored)) setLocaleState(stored);
    } catch {
      // localStorage unavailable (private mode, etc.) — stay on the default.
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Best-effort persistence only.
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Vars) => {
      const template = dictionaries[locale]?.[key] ?? en[key] ?? key;
      return interpolate(template, vars);
    },
    [locale]
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

/** Falls back to English-only, no-op-setter behavior if used outside a LocaleProvider. */
export function useTranslation(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (ctx) return ctx;
  return {
    locale: DEFAULT_LOCALE,
    setLocale: () => {},
    t: (key, vars) => interpolate(en[key] ?? key, vars),
  };
}
