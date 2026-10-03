"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { Footer } from "../components/Footer";
import { useLanguage } from "../lib/LanguageContext";
import {
  Package,
  LineChart,
  Sparkles,
  Send,
  Image as ImageIcon,
  MessageCircle,
  MessagesSquare,
  Megaphone,
  ArrowRight,
  CheckCircle2,
  Clock,
  Zap,
} from "lucide-react";

const categories = ["All", "Operations", "Marketing", "Engagement"];

const features = [
  {
    key: "inventory",
    title: "Inventory Management",
    category: "Operations",
    desc: "Manage stock, sync catalogs, and automate replenishment checks in real time.",
    icon: Package,
    badge: "Saves 5 hrs/wk",
    preview: "Real-time stock sync active",
  },
  {
    key: "revenue",
    title: "Revenue Dashboard",
    category: "Operations",
    desc: "See your sales, order volume, and revenue trends without manual reporting.",
    icon: LineChart,
    badge: "Instant Metrics",
    preview: "Automated daily P&L reports",
  },
  {
    key: "caption",
    title: "Caption Generation",
    category: "Marketing",
    desc: "Create social captions, product descriptions and ad copy instantly.",
    icon: Sparkles,
    badge: "10x Faster",
    preview: "AI copy crafted in 2 seconds",
  },
  {
    key: "social",
    title: "Social Posting",
    category: "Marketing",
    desc: "Publish 1-2 high-quality social posts per day across your connected channels.",
    icon: Send,
    badge: "24/7 Active",
    preview: "Auto-scheduled post queues",
  },
  {
    key: "image",
    title: "Image Generation",
    category: "Marketing",
    desc: "Generate product and lifestyle images using AI guidance for better engagement.",
    icon: ImageIcon,
    badge: "Studio Quality",
    preview: "4K lifestyle render engine",
  },
  {
    key: "chatbot",
    title: "Chatbot Integration",
    category: "Engagement",
    desc: "Handle customer messages and auto-reply to comments from one dashboard.",
    icon: MessageCircle,
    badge: "< 1s Response",
    preview: "Instant order lookup AI",
  },
  {
    key: "comments",
    title: "Comment Insights",
    category: "Engagement",
    desc: "Show comments in a dashboard and reply automatically to keep conversations moving.",
    icon: MessagesSquare,
    badge: "Zero Spam",
    preview: "Sentiment filtering engine",
  },
  {
    key: "atAll",
    title: "@all Support",
    category: "Engagement",
    desc: "Trigger broad social engagement commands and manage audience interactions faster.",
    icon: Megaphone,
    badge: "High Reach",
    preview: "Bulk community broadcaster",
  },
];

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

const container: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.1 },
  },
};

export default function FeaturesPage() {
  const { t } = useLanguage();
  const [activeCategory, setActiveCategory] = useState("All");

  const filteredFeatures =
    activeCategory === "All"
      ? features
      : features.filter((f) => f.category === activeCategory);

  return (
    <div className="min-h-screen bg-[#02040d] text-white relative overflow-hidden select-none">
      {/* Background Glows */}
      <motion.div
        className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[520px] w-[520px] rounded-full bg-amber-500/10 blur-3xl sm:h-[700px] sm:w-[700px]"
        animate={{ opacity: [0.3, 0.6, 0.3], scale: [1, 1.05, 1] }}
        transition={{ duration: 7, repeat: Infinity }}
      />
      <div className="pointer-events-none absolute top-1/2 -right-40 hidden h-[500px] w-[500px] rounded-full bg-yellow-500/5 blur-3xl sm:block" />

      {/* Grid Texture */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage: "radial-gradient(rgba(251,191,36,0.35) 1px, transparent 1px)",
          backgroundSize: "36px 36px",
          maskImage: "radial-gradient(ellipse 60% 50% at 50% 20%, black 40%, transparent 100%)",
        }}
      />

      {/* Fixed Sticky Header */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="fixed left-0 right-0 top-0 z-50 flex items-center justify-between border-b border-white/10 bg-[#04090f]/90 px-4 py-3 backdrop-blur-xl sm:px-12 sm:py-4"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-yellow-500 text-sm font-bold text-[#06111b] shadow-lg shadow-amber-500/20 sm:h-10 sm:w-10 sm:text-base">
            FTE
          </div>
          <div>
            <h1 className="text-base font-extrabold tracking-tight text-white sm:text-xl">Digital FTE</h1>
            <p className="hidden text-[10px] font-bold uppercase tracking-widest text-amber-300 sm:block">AI E-Commerce Employee</p>
          </div>
        </div>
        <SiteNav />
      </motion.header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-16 pt-28 sm:px-12 sm:pb-20 sm:pt-32">
        {/* Hero Section */}
        <motion.section initial="hidden" animate="show" variants={container} className="mb-10 text-center sm:mb-12">
          <motion.p
            variants={fadeUp}
            className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-amber-300 sm:px-3.5 sm:text-xs"
          >
            <Zap className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
            {t("features.badge")}
          </motion.p>
          <motion.h2 variants={fadeUp} className="mt-5 text-3xl font-extrabold leading-tight tracking-tight text-white sm:mt-6 sm:text-5xl">
            {t("features.headline")}
          </motion.h2>
          <motion.p variants={fadeUp} className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-slate-400 sm:mt-5 sm:text-base">
            {t("features.sub")}
          </motion.p>
        </motion.section>

        {/* Category Filter Tabs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mb-10 flex flex-wrap items-center justify-center gap-2 sm:mb-12"
        >
          {categories.map((cat) => {
            const isActive = activeCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className="relative px-4 py-2 rounded-full text-xs font-bold transition-colors duration-200"
              >
                {isActive && (
                  <motion.div
                    layoutId="activeFeatureTab"
                    className="absolute inset-0 bg-amber-400 rounded-full shadow-lg shadow-amber-500/20"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <span className={`relative z-10 ${isActive ? "text-[#06111b]" : "text-slate-400"}`}>
                  {t(`features.categories.${cat === "All" ? "all" : cat.toLowerCase()}`)}
                </span>
              </button>
            );
          })}
        </motion.div>

        {/* Features Grid with Scroll Trigger Reveal */}
        <motion.div
          layout
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-50px" }}
          variants={container}
          className="grid min-h-[400px] gap-4 sm:gap-6 md:grid-cols-2 xl:grid-cols-3"
        >
          <AnimatePresence mode="popLayout">
            {filteredFeatures.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <motion.div
                  layout
                  key={feature.title}
                  variants={fadeUp}
                  initial={{ opacity: 0, y: 35 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ duration: 0.5, delay: index * 0.05 }}
                  className="relative flex min-w-0 flex-col justify-between overflow-hidden rounded-3xl border border-white/10 bg-[#071121]/90 p-5 shadow-2xl backdrop-blur-xl sm:p-6"
                >
                  <div>
                    <div className="mb-5 flex items-start justify-between gap-3">
                      <div className="w-11 h-11 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                        <Icon className="w-5 h-5" strokeWidth={2} />
                      </div>

                      <span className="flex max-w-[62%] items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-right text-[9px] font-bold text-amber-300 sm:px-2.5 sm:text-[10px]">
                        <Clock className="w-3 h-3 text-amber-400" />
                        {t(`features.items.${feature.key}.badge`)}
                      </span>
                    </div>

                    <h3 className="text-lg font-bold text-white mb-2">{t(`features.items.${feature.key}.title`)}</h3>
                    <p className="text-sm text-slate-400 leading-relaxed">{t(`features.items.${feature.key}.desc`)}</p>
                  </div>

                  {/* Status Indicator */}
                  <div className="mt-6 pt-4 border-t border-white/5 flex items-center gap-2 text-[11px] text-slate-400">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                    </span>
                    <span>{t(`features.items.${feature.key}.preview`)}</span>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </motion.div>

        {/* Scroll-Triggered Value Section */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="relative mt-16 overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-[#06111d] to-[#0a1626] p-5 shadow-2xl sm:mt-20 sm:p-10"
        >
           <span className="text-[11px] font-bold text-amber-400 tracking-widest uppercase">{t("features.valueTitle")}</span>
           <h3 className="mt-2 text-2xl sm:text-3xl font-extrabold text-white">{t("features.whyMatters")}</h3>
          <p className="mt-4 text-sm sm:text-base text-slate-400 leading-relaxed max-w-3xl">
             {t("features.whyDesc")}
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 flex items-start gap-3"
            >
              <CheckCircle2 className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-300 leading-relaxed">
                 {t("features.bullet1")}
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 flex items-start gap-3"
            >
              <CheckCircle2 className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-300 leading-relaxed">
                 {t("features.bullet2")}
              </p>
            </motion.div>
          </div>
        </motion.div>

        {/* Scroll-Triggered CTA Section */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ duration: 0.5 }}
          className="mt-16 text-center"
        >
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-full bg-amber-400 px-8 py-3.5 text-sm font-bold text-[#06111b] hover:bg-amber-300 transition-colors shadow-lg shadow-amber-500/10"
          >
             <span>{t("features.ctaBtn")}</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </motion.div>
      </main>
      <Footer />
    </div>
  );
}