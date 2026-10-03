"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { Globe, ChevronDown, Check, Menu, X } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";

export function SiteNav() {
  const pathname = usePathname() || "/";
  const { language, setLanguage, t } = useLanguage();
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const navLinks = [
    { href: "/home-new", labelKey: "nav.home" },
    { href: "/features", labelKey: "nav.features" },
    { href: "/how-it-works", labelKey: "nav.howItWorks" },
    { href: "/pricing", labelKey: "nav.pricing" },
    { href: "/about", labelKey: "nav.about" },
    { href: "/contact", labelKey: "nav.contact" },
    { href: "/", labelKey: "nav.dashboard" },
  ];

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setLangDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const renderLinks = (mobile = false) => (
    <>
      {navLinks.map((link) => {
        const isActive =
          link.href === "/"
            ? pathname === "/"
            : pathname.startsWith(link.href);

        return (
          <Link
            key={link.href}
            href={link.href}
            prefetch={true}
            aria-current={isActive ? "page" : undefined}
            onClick={() => mobile && setMobileMenuOpen(false)}
            className={`${mobile ? "block rounded-xl px-4 py-3" : "relative"} transition-colors ${
              isActive
                ? "text-amber-300 after:absolute after:left-0 after:-bottom-2 after:h-[2px] after:w-full after:rounded-full after:bg-amber-400"
                : "hover:text-amber-400"
            }`}
          >
            {t(link.labelKey)}
          </Link>
        );
      })}
    </>
  );

  return (
    <>
      <div className="hidden lg:flex items-center gap-6 text-sm font-semibold text-slate-300">
        {renderLinks()}

      {/* Language Switcher */}
      <div className="relative" ref={dropdownRef}>
        <button
          id="lang-switcher-btn"
          onClick={() => setLangDropdownOpen((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-amber-400/10 hover:border-amber-400/30 transition-all duration-200 text-slate-300 hover:text-amber-300"
          aria-label="Select Language"
        >
          <Globe className="w-4 h-4" />
          <span className="text-xs font-bold">
            {language === "ur" ? "اردو" : "EN"}
          </span>
          <ChevronDown
            className={`w-3 h-3 transition-transform duration-200 ${
              langDropdownOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {langDropdownOpen && (
          <div className="absolute right-0 top-full mt-2 w-44 rounded-2xl border border-white/10 bg-[#07111d]/95 backdrop-blur-xl shadow-2xl shadow-black/50 overflow-hidden z-50 animate-fade-in">
            <div className="p-1.5 space-y-0.5">
              {/* English option */}
              <button
                id="lang-option-en"
                onClick={() => {
                  setLanguage("en");
                  setLangDropdownOpen(false);
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/10 transition-all text-left cursor-pointer group"
              >
                <span className="text-xl">🇬🇧</span>
                <div className="flex-1">
                  <p className="text-sm font-bold text-white group-hover:text-amber-300 transition-colors">
                    English
                  </p>
                  <p className="text-[10px] text-slate-400">English</p>
                </div>
                {language === "en" && (
                  <Check className="w-4 h-4 text-amber-400 shrink-0" />
                )}
              </button>

              {/* Urdu option */}
              <button
                id="lang-option-ur"
                onClick={() => {
                  setLanguage("ur");
                  setLangDropdownOpen(false);
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/10 transition-all text-left cursor-pointer group"
                dir="rtl"
              >
                <span className="text-xl">🇵🇰</span>
                <div className="flex-1" dir="rtl">
                  <p className="text-sm font-bold text-white group-hover:text-amber-300 transition-colors">
                    اردو
                  </p>
                  <p className="text-[10px] text-slate-400">Urdu</p>
                </div>
                {language === "ur" && (
                  <Check className="w-4 h-4 text-amber-400 shrink-0" />
                )}
              </button>
            </div>

            {/* Divider + brand note */}
            <div className="border-t border-white/5 px-3 py-2">
              <p className="text-[9px] text-slate-500 text-center">
                Digital FTE • Bilingual Support
              </p>
            </div>
          </div>
        )}
      </div>
      </div>

      <div className="lg:hidden relative">
        <button
          type="button"
          onClick={() => setMobileMenuOpen((open) => !open)}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-200"
          aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileMenuOpen}
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>

        {mobileMenuOpen && (
          <div className="absolute right-0 top-12 z-50 w-[min(17rem,calc(100vw-2rem))] rounded-2xl border border-white/10 bg-[#07111d]/95 p-2 shadow-2xl backdrop-blur-xl">
            <nav className="text-sm font-semibold text-slate-300">{renderLinks(true)}</nav>
            <div className="mt-2 border-t border-white/10 pt-2">
              <button
                type="button"
                onClick={() => setLangDropdownOpen((open) => !open)}
                className="flex w-full items-center gap-2 rounded-xl px-4 py-3 text-left text-sm font-semibold text-slate-300 hover:bg-white/10"
                aria-expanded={langDropdownOpen}
              >
                <Globe className="h-4 w-4" />
                {language === "ur" ? "اردو" : "English"}
                <ChevronDown className={`ml-auto h-4 w-4 ${langDropdownOpen ? "rotate-180" : ""}`} />
              </button>
              {langDropdownOpen && (
                <div className="space-y-1 px-2 pb-2">
                  <button type="button" onClick={() => { setLanguage("en"); setLangDropdownOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-slate-300 hover:bg-white/10">English {language === "en" && <Check className="ml-auto h-3 w-3 text-amber-400" />}</button>
                  <button type="button" onClick={() => { setLanguage("ur"); setLangDropdownOpen(false); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-slate-300 hover:bg-white/10">اردو {language === "ur" && <Check className="ml-auto h-3 w-3 text-amber-400" />}</button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
