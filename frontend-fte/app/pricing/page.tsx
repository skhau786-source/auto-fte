"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { Footer } from "../components/Footer";
import { useLanguage } from "../lib/LanguageContext";
import {
  CheckCircle2,
  Zap,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  HelpCircle,
  ChevronDown,
} from "lucide-react";

const freeTrialFeatures = [
  "f1",
  "f2",
  "f3",
  "f4",
  "f5",
  "f6",
  "f7",
];

const proFeatures = [
  "f1",
  "f2",
  "f3",
  "f4",
  "f5",
  "f6",
];

const faqs = [
  { q: "q1", a: "a1" },
  { q: "q2", a: "a2" },
  { q: "q3", a: "a3" },
];

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

export default function PricingPage() {
  const { t } = useLanguage();
  const [isYearly, setIsYearly] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-[#02040d] text-white relative overflow-hidden select-none">
      {/* Background Glows */}
      <motion.div
        className="pointer-events-none fixed -top-40 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-amber-500/10 rounded-full blur-[120px]"
        animate={{ opacity: [0.25, 0.45, 0.25], scale: [1, 1.05, 1] }}
        transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Grid Pattern */}
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.12]"
        style={{
          backgroundImage: "radial-gradient(rgba(251,191,36,0.35) 1px, transparent 1px)",
          backgroundSize: "36px 36px",
          maskImage: "radial-gradient(ellipse 60% 50% at 50% 20%, black 40%, transparent 100%)",
        }}
      />

      {/* FIXED NAVBAR */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="fixed top-0 left-0 right-0 z-50 border-b border-white/10 bg-[#04090f]/90 backdrop-blur-xl px-6 sm:px-12 py-4 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-500 flex items-center justify-center text-[#06111b] font-extrabold shadow-lg shadow-amber-500/20">
            FTE
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-white">Digital FTE</h1>
            <p className="text-[10px] font-bold text-amber-300 tracking-widest uppercase">AI E-Commerce Employee</p>
          </div>
        </div>
        <SiteNav />
      </motion.header>

      <main className="max-w-6xl mx-auto px-6 sm:px-12 pt-32 pb-20 relative z-10">
        {/* Hero Section */}
        <motion.section initial="hidden" animate="show" variants={container} className="text-center mb-12">
          <motion.p
            variants={fadeUp}
            className="text-xs font-bold text-amber-300 tracking-widest uppercase bg-amber-500/10 border border-amber-500/20 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full cursor-default"
          >
            <Zap className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
            {t("pricing.badge")}
          </motion.p>
          <motion.h2 variants={fadeUp} className="mt-6 text-4xl sm:text-6xl font-extrabold tracking-tight text-white leading-tight">
            {t("pricing.headline1")} <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-amber-200 via-amber-400 to-yellow-500 bg-clip-text text-transparent">
              {t("pricing.headline2")}
            </span>
          </motion.h2>
          <motion.p variants={fadeUp} className="mt-4 text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
            {t("pricing.sub")}
          </motion.p>

          {/* Billing Cycle Toggle */}
          <motion.div variants={fadeUp} className="mt-8 inline-flex items-center gap-3 bg-[#071121] border border-white/10 rounded-full p-1.5">
            <button
              onClick={() => setIsYearly(false)}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all ${
                !isYearly ? "bg-amber-400 text-[#06111b] shadow-md" : "text-slate-400 hover:text-white"
              }`}
            >
              {t("pricing.monthly")}
            </button>
            <button
              onClick={() => setIsYearly(true)}
              className={`px-5 py-2 rounded-full text-xs font-bold transition-all flex items-center gap-1.5 ${
                isYearly ? "bg-amber-400 text-[#06111b] shadow-md" : "text-slate-400 hover:text-white"
              }`}
            >
              {t("pricing.yearly")}
              <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
                {t("pricing.save20")}
              </span>
            </button>
          </motion.div>
        </motion.section>

        {/* Pricing Cards Grid */}
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-50px" }}
          variants={container}
          className="grid gap-8 md:grid-cols-2 items-stretch max-w-5xl mx-auto"
        >
          {/* Free Trial Card */}
          <motion.div
            variants={fadeUp}
            className="rounded-3xl border border-white/10 bg-[#071121]/80 backdrop-blur-xl p-8 shadow-2xl flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-bold uppercase tracking-widest text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-full">
                  {t("pricing.trialBadge")}
                </span>
                <ShieldCheck className="w-5 h-5 text-slate-400" />
              </div>

              <h3 className="text-3xl font-extrabold text-white">{t("pricing.trialTitle")}</h3>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                {t("pricing.trialDesc")}
              </p>

              <div className="mt-8 space-y-3.5 border-t border-white/5 pt-6">
                {freeTrialFeatures.map((item, index) => (
                  <div key={index} className="text-xs sm:text-sm text-slate-300 flex items-center gap-3">
                    <CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>{t(`pricing.trialFeatures.${item}`)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <Link
                href="/"
                className="inline-flex items-center justify-center w-full rounded-full border border-white/10 bg-white/5 px-6 py-3.5 text-sm font-bold text-white hover:bg-white/10 transition-colors"
              >
                {t("pricing.trialBtn")}
              </Link>
            </div>
          </motion.div>

          {/* Pro Plan Card */}
          <motion.div
            variants={fadeUp}
            className="rounded-3xl border-2 border-amber-400 bg-gradient-to-b from-[#0e2038] to-[#071121] p-8 shadow-2xl shadow-amber-500/10 flex flex-col justify-between relative overflow-hidden"
          >
            {/* Ribbon Badge */}
            <div className="absolute top-0 right-0 bg-amber-400 text-[#06111b] font-extrabold text-[10px] tracking-widest uppercase px-4 py-1.5 rounded-bl-2xl">
              {t("pricing.mostPopular")}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-4">
                <Sparkles className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-bold uppercase tracking-widest text-amber-300">
                  {t("pricing.proBadge")}
                </span>
              </div>

              <div className="flex items-baseline gap-2">
                <h3 className="text-4xl sm:text-5xl font-extrabold text-white">
                  {isYearly ? "$32" : "$40"}
                </h3>
                <span className="text-sm font-bold text-slate-400">{t("pricing.proPerMonth")}</span>
              </div>
              <p className="mt-2 text-xs text-amber-200/80">
                {isYearly ? t("pricing.proBilledYearly") : t("pricing.proBilledMonthly")}
              </p>

              <div className="mt-8 space-y-3.5 border-t border-white/10 pt-6">
                {proFeatures.map((feat, idx) => (
                  <div key={idx} className="rounded-2xl bg-white/5 border border-white/5 p-3 flex items-start gap-3">
                    <CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-bold text-white">{t(`pricing.proFeatures.${feat}.title`)}</p>
                      <p className="text-[11px] text-slate-400">{t(`pricing.proFeatures.${feat}.desc`)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <Link
                href="/"
                className="inline-flex items-center justify-center gap-2 w-full rounded-full bg-amber-400 px-6 py-3.5 text-sm font-bold text-[#06111b] hover:bg-amber-300 transition-colors shadow-lg shadow-amber-500/20"
              >
                <span>{t("pricing.proBtn")}</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </motion.div>
        </motion.div>

        {/* FAQs Section */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.6 }}
          className="mt-24 max-w-3xl mx-auto"
        >
          <div className="text-center mb-10">
            <HelpCircle className="w-8 h-8 text-amber-400 mx-auto mb-3" />
            <h3 className="text-2xl font-extrabold text-white">{t("pricing.faqTitle")}</h3>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, index) => {
              const isOpen = openFaq === index;
              return (
                <div
                  key={index}
                  onClick={() => setOpenFaq(isOpen ? null : index)}
                  className="rounded-2xl border border-white/10 bg-[#071121]/90 backdrop-blur-xl p-5 cursor-pointer transition-colors hover:border-amber-500/30"
                >
                  <div className="flex items-center justify-between gap-4">
                    <h4 className="text-sm font-bold text-white">{t(`pricing.faqs.${faq.q}`)}</h4>
                    <ChevronDown
                      className={`w-4 h-4 text-amber-400 transition-transform duration-300 ${
                        isOpen ? "rotate-180" : ""
                      }`}
                    />
                  </div>
                  <AnimatePresence>
                    {isOpen && (
                      <motion.p
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="mt-3 text-xs text-slate-400 leading-relaxed border-t border-white/5 pt-3"
                      >
                        {t(`pricing.faqs.${faq.a}`)}
                      </motion.p>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </motion.div>
      </main>
      <Footer />
    </div>
  );
}