"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { InteractiveRobot } from "../components/site/InteractiveRobot";
import { Footer } from "../components/Footer";
import { useLanguage } from "../lib/LanguageContext";
import {
  Store,
  Share2,
  Cpu,
  Zap,
  BarChart3,
  Rocket,
  TrendingUp,
  ArrowRight,
  CheckCircle2,
  Sparkles,
  Bot,
  Activity,
} from "lucide-react";

const steps = [
  {
    key: "s1",
    step: "01",
    title: "Connect Your Store",
    desc: "Link your Shopify or e-commerce website securely so the AI can sync products, inventory, and orders.",
    icon: Store,
    badge: "1-Click Sync",
    previewText: "Shopify API Connected • 2,410 SKUs Processed",
  },
  {
    key: "s2",
    step: "02",
    title: "Connect Social Channels",
    desc: "Authorize Instagram, Facebook, TikTok, YouTube, and Twitter to let the AI publish posts and reply to comments.",
    icon: Share2,
    badge: "Multi-Platform",
    previewText: "Meta & TikTok Tokens Granted • Auto-Reply Active",
  },
  {
    key: "s3",
    step: "03",
    title: "Train Your AI Roles",
    desc: "Choose the roles your Digital FTE should perform: inventory, support, content, analytics, and automation.",
    icon: Cpu,
    badge: "Role Config",
    previewText: "Roles: Support (Agent #1), Inventory (Agent #2)",
  },
  {
    key: "s4",
    step: "04",
    title: "Activate Auto Posting",
    desc: "Set daily social posting cadence and auto-reply rules for comment management.",
    icon: Zap,
    badge: "Automated Engine",
    previewText: "Posting Schedule: 2x Daily • Sentiment Filter Active",
  },
  {
    key: "s5",
    step: "05",
    title: "Review Revenue Signals",
    desc: "Monitor revenue, orders and inventory health from the same AI dashboard.",
    icon: BarChart3,
    badge: "Real-time Metrics",
    previewText: "Live P&L Stream Connected • 99.4% Forecast Accuracy",
  },
  {
    key: "s6",
    step: "06",
    title: "Launch the Agent",
    desc: "Deploy your AI employee and let it start working 24/7 on your store and social campaigns.",
    icon: Rocket,
    badge: "24/7 Live Deployment",
    previewText: "Agent Online • Avg Response Time: 0.8s",
  },
  {
    key: "s7",
    step: "07",
    title: "Grow with AI",
    desc: "Scale faster with fewer mistakes, better engagement, and automated store operations.",
    icon: TrendingUp,
    badge: "Continuous Growth",
    previewText: "Weekly Revenue Lift: +18.4% Average",
  },
];

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

export default function HowItWorksPage() {
  const { t } = useLanguage();
  const [activeStepIndex, setActiveStepIndex] = useState(0);

  return (
    <div className="min-h-screen bg-[#02040d] text-white relative overflow-hidden select-none">
      {/* Background Ambient Glows */}
      <motion.div
        className="pointer-events-none fixed -top-40 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-amber-500/10 rounded-full blur-[120px]"
        animate={{ opacity: [0.25, 0.45, 0.25], scale: [1, 1.08, 1] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="pointer-events-none fixed bottom-0 right-0 w-[500px] h-[500px] bg-yellow-500/5 rounded-full blur-[100px]" />

      {/* Grid Pattern Background */}
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
        <motion.section initial="hidden" animate="show" variants={container} className="text-center mb-20">
          <motion.p
            variants={fadeUp}
            className="text-xs font-bold text-amber-300 tracking-widest uppercase bg-amber-500/10 border border-amber-500/20 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full cursor-default"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
            {t("howItWorks.badge")}
          </motion.p>
          <motion.h2 variants={fadeUp} className="mt-6 text-4xl sm:text-6xl font-extrabold tracking-tight text-white leading-tight">
            {t("howItWorks.headline1")} <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-amber-200 via-amber-400 to-yellow-500 bg-clip-text text-transparent">
              {t("howItWorks.headline2")}
            </span>
          </motion.h2>
          <motion.p variants={fadeUp} className="mt-5 text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
            {t("howItWorks.sub")}
          </motion.p>
        </motion.section>

        {/* Timeline & Interactive Display Section */}
        <div className="grid gap-12 lg:grid-cols-12 items-start">
          {/* Left Column: Interactive Timeline List */}
          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-50px" }}
            variants={container}
            className="lg:col-span-7 space-y-6 relative"
          >
            {/* Timeline Vertical Connector Line */}
            <div className="absolute left-8 top-10 bottom-10 w-[2px] bg-gradient-to-b from-amber-500/40 via-amber-500/20 to-transparent hidden sm:block" />

            {steps.map((item, idx) => {
              const Icon = item.icon;
              const isSelected = activeStepIndex === idx;

              return (
                <motion.div
                  key={item.title}
                  variants={fadeUp}
                  onClick={() => setActiveStepIndex(idx)}
                  className={`group rounded-3xl border p-6 transition-all duration-300 cursor-pointer relative overflow-hidden ${
                    isSelected
                      ? "bg-[#0a172c] border-amber-500/50 shadow-2xl shadow-amber-500/10"
                      : "bg-[#071121]/80 border-white/10 hover:border-amber-500/30 hover:bg-[#071121]"
                  }`}
                >
                  <div className="flex items-start gap-4 sm:gap-6 relative z-10">
                    {/* Step Icon Badge */}
                    <div
                      className={`w-12 h-12 rounded-2xl flex items-center justify-center font-bold shrink-0 transition-colors duration-300 ${
                        isSelected
                          ? "bg-amber-400 text-[#06111b] shadow-lg shadow-amber-400/20"
                          : "bg-amber-500/10 border border-amber-500/20 text-amber-400 group-hover:bg-amber-500/20"
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                    </div>

                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-mono font-bold text-amber-400 uppercase tracking-widest">
                          {t("common.step")} {item.step}
                        </span>
                        <span className="text-[10px] font-bold text-amber-300/80 bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 rounded-full">
                          {t(`howItWorks.steps.${item.key}.badge`)}
                        </span>
                      </div>

                      <h3 className="text-lg font-bold text-white group-hover:text-amber-300 transition-colors">
                        {t(`howItWorks.steps.${item.key}.title`)}
                      </h3>
                      <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                        {t(`howItWorks.steps.${item.key}.desc`)}
                      </p>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>

          {/* Right Column: Sticky Active Step Visualizer Box */}
          <div className="lg:col-span-5 lg:sticky lg:top-28">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5 }}
              className="rounded-3xl border border-white/10 bg-gradient-to-b from-[#091527] to-[#040a14] p-6 shadow-2xl relative overflow-hidden"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
                <div className="flex items-center gap-2">
                  <Bot className="w-5 h-5 text-amber-400" />
                  <span className="text-xs font-bold text-white tracking-wider uppercase">
                    {t("howItWorks.stepMonitor")}
                  </span>
                </div>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                </span>
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={activeStepIndex}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ duration: 0.3 }}
                  className="space-y-6"
                >
                  <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4 flex items-center gap-3">
                    <Activity className="w-5 h-5 text-amber-400 animate-pulse shrink-0" />
                    <p className="text-xs font-mono text-amber-200">
                      {t(`howItWorks.steps.${steps[activeStepIndex].key}.preview`)}
                    </p>
                  </div>

                  <div>
                    <h4 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-2">
                      {t("howItWorks.activeStage")}
                    </h4>
                    <p className="text-xl font-extrabold text-white">
                      {t(`howItWorks.steps.${steps[activeStepIndex].key}.title`)}
                    </p>
                    <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                      {t(`howItWorks.steps.${steps[activeStepIndex].key}.desc`)}
                    </p>
                  </div>

                  <div className="pt-4 border-t border-white/5 space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>{t("howItWorks.automatedConfig")}</span>
                      <span className="text-emerald-400 font-bold flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> {t("howItWorks.ready")}
                      </span>
                    </div>
                    <div className="w-full bg-white/5 rounded-full h-1.5 overflow-hidden">
                      <motion.div
                        className="bg-gradient-to-r from-amber-500 to-yellow-400 h-full rounded-full"
                        initial={{ width: "0%" }}
                        animate={{ width: `${((activeStepIndex + 1) / 7) * 100}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  </div>
                </motion.div>
              </AnimatePresence>
            </motion.div>
          </div>
        </div>

        {/* Scroll-Triggered Bottom CTA */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mt-24 rounded-3xl border border-white/10 bg-gradient-to-br from-[#06111d] to-[#0a1626] p-8 sm:p-12 shadow-2xl text-center relative overflow-hidden"
        >
          <h3 className="text-2xl sm:text-4xl font-extrabold text-white">
            {t("howItWorks.ctaHeadline")}
          </h3>
          <p className="mt-4 text-sm sm:text-base text-slate-400 leading-relaxed max-w-2xl mx-auto">
            {t("howItWorks.ctaDesc")}
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/pricing"
              className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-8 py-3.5 text-sm font-bold text-[#06111b] hover:bg-amber-300 transition-colors shadow-lg shadow-amber-500/10"
            >
              <span>{t("howItWorks.ctaBtn")}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/home-new"
              className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-8 py-3.5 text-sm font-bold text-white hover:bg-white/10 transition-colors"
            >
              {t("howItWorks.backBtn")}
            </Link>
          </div>
        </motion.div>

        {/* Floating Robot */}
        <div className="fixed left-6 bottom-6 w-24 h-24 hidden md:block pointer-events-none z-30">
          <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
        </div>
      </main>
      <Footer />
    </div>
  );
} 