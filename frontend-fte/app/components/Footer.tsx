"use client";

import React from "react";
import Link from "next/link";
import { TrendingUp, ShieldCheck } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";

export function Footer() {
  const { t } = useLanguage();

  return (
    <footer id="app-footer" className="relative border-t border-white/10 bg-[#02040d]/95 text-slate-400 overflow-hidden pt-16 pb-12">
      {/* Subtle top glow */}
      <div className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 w-[600px] h-24 bg-amber-500/10 rounded-full blur-[80px]" />

      <div className="max-w-7xl mx-auto px-6 sm:px-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-10 pb-12 border-b border-white/10">
          
          {/* Brand Info */}
          <div className="lg:col-span-2 space-y-4">
            <Link href="/home-new" className="flex items-center gap-3 group inline-flex">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-400 flex items-center justify-center text-[#06111b] font-extrabold shadow-lg shadow-amber-500/20 group-hover:scale-105 transition-transform">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xl font-extrabold tracking-tight text-white">Digital FTE</span>
                <p className="text-[10px] font-bold text-amber-300 tracking-widest uppercase">
                  Autonomous AI Employee
                </p>
              </div>
            </Link>

            <p className="text-sm text-slate-400 max-w-sm leading-relaxed">
              {t("footer.description") || "Empowering 24/7 E-Commerce growth with secure, autonomous AI employee containers."}
            </p>

            <div className="flex items-center gap-3 pt-2">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[11px] font-semibold text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <span>All 7 AI Agents Active</span>
              </div>
              <span className="text-xs text-slate-500">FastAPI • Gemini 2.5 • Redis</span>
            </div>
          </div>

          {/* Product Links */}
          <div className="space-y-3">
            <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">Platform</p>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/features" className="hover:text-amber-300 transition-colors">
                  {t("nav.features") || "Features"}
                </Link>
              </li>
              <li>
                <Link href="/how-it-works" className="hover:text-amber-300 transition-colors">
                  {t("nav.howItWorks") || "How It Works"}
                </Link>
              </li>
              <li>
                <Link href="/pricing" className="hover:text-amber-300 transition-colors">
                  {t("nav.pricing") || "Pricing"}
                </Link>
              </li>
              <li>
                <Link href="/home-new#ai-workforce" className="hover:text-amber-300 transition-colors flex items-center gap-1">
                  <span>AI Agents</span>
                  <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded-md font-mono">7</span>
                </Link>
              </li>
              <li>
                <Link href="/home-new#integrations" className="hover:text-amber-300 transition-colors">
                  Ecosystem & Integrations
                </Link>
              </li>
            </ul>
          </div>

          {/* Company Links */}
          <div className="space-y-3">
            <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">Company</p>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/about" className="hover:text-amber-300 transition-colors">
                  {t("nav.about") || "About Us"}
                </Link>
              </li>
              <li>
                <Link href="/contact" className="hover:text-amber-300 transition-colors">
                  Contact & Support
                </Link>
              </li>
              <li>
                <span className="inline-flex items-center gap-1.5 text-slate-500 cursor-not-allowed">
                  Careers <span className="text-[9px] bg-white/10 text-slate-400 px-1.5 py-0.5 rounded">Hiring</span>
                </span>
              </li>
              <li>
                <Link href="/home-new#faq" className="hover:text-amber-300 transition-colors">
                  FAQs
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal & Security */}
          <div className="space-y-3">
            <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">Legal & Security</p>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/privacy" className="hover:text-amber-300 transition-colors flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Privacy Policy</span>
                </Link>
              </li>
              <li>
                <Link href="/terms" className="hover:text-amber-300 transition-colors">
                  Terms & Conditions
                </Link>
              </li>
              <li>
                <Link href="/privacy#data-security" className="hover:text-amber-300 transition-colors">
                  Security & Zero-Training
                </Link>
              </li>
              <li>
                <Link href="/terms#refund" className="hover:text-amber-300 transition-colors">
                  Cancellation & Refund
                </Link>
              </li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <p>© 2026 Digital FTE. All rights reserved.</p>
          <div className="flex items-center gap-4 text-slate-400">
            <Link href="/privacy" className="hover:text-amber-300 transition-colors">Privacy</Link>
            <span>•</span>
            <Link href="/terms" className="hover:text-amber-300 transition-colors">Terms</Link>
            <span>•</span>
            <Link href="/contact" className="hover:text-amber-300 transition-colors">Support</Link>
            <span>•</span>
            <span className="text-amber-400/90 font-medium">Bilingual EN / اردو</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
