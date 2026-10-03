"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { Footer } from "../components/Footer";
import { 
  Sparkles, 
  Bot, 
  ShieldCheck, 
  ArrowRight, 
  Users, 
  Globe2, 
  Cpu, 
  HeartHandshake,
  Zap
} from "lucide-react";

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-[#02040d] text-white relative overflow-hidden selection:bg-amber-400 selection:text-black">
      {/* Background Glows */}
      <div className="pointer-events-none fixed -top-40 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-amber-500/10 rounded-full blur-[120px]" />
      
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
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-white/10 bg-[#04090f]/90 backdrop-blur-xl px-6 sm:px-12 py-4 flex items-center justify-between">
        <Link href="/home-new" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-500 flex items-center justify-center text-[#06111b] font-extrabold shadow-lg shadow-amber-500/20">
            FTE
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-white">Digital FTE</h1>
            <p className="text-[10px] font-bold text-amber-300 tracking-widest uppercase">AI E-Commerce Employee</p>
          </div>
        </Link>

        <SiteNav />

        <div className="flex items-center gap-3">
          <Link
            href="/home-new"
            className="px-4 py-2 text-sm font-bold rounded-xl bg-gradient-to-r from-amber-500 to-yellow-400 text-[#06111b] shadow-md shadow-amber-500/20 hover:shadow-lg transition-all"
          >
            Get Started
          </Link>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="pt-32 pb-20 px-6 sm:px-12 max-w-6xl mx-auto relative z-10">
        
        {/* Hero Banner */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-3xl mx-auto mb-20"
        >
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-300 text-xs font-bold uppercase tracking-wider mb-4">
            <Sparkles className="w-4 h-4" />
            Our Vision & Mission
          </div>
          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-white leading-tight">
            Pioneering the World's First <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-yellow-300 to-amber-500">Autonomous AI Employee</span> for E-Commerce.
          </h1>
          <p className="mt-6 text-slate-300 text-base sm:text-lg leading-relaxed">
            Online merchants shouldn't have to spend 14 hours a day juggling 7 different browser tabs, checking inventory, drafting social posts, and answering repetitious messages. We engineered <strong className="text-white">Digital FTE</strong> to solve e-commerce founder burnout forever.
          </p>
        </motion.div>

        {/* 3 Pillar Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-20">
          <div className="p-8 rounded-3xl bg-[#07111d]/90 border border-white/10 backdrop-blur-sm relative group hover:border-amber-400/40 transition-all">
            <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mb-6">
              <Bot className="w-6 h-6" />
            </div>
            <h3 className="text-xl font-bold text-white mb-2">Not a Tool. An Employee.</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Traditional SaaS apps require you to do the work. Digital FTE is an autonomous agentic system that proactively executes tasks, monitors stock, and publishes marketing on autopilot.
            </p>
          </div>

          <div className="p-8 rounded-3xl bg-[#07111d]/90 border border-white/10 backdrop-blur-sm relative group hover:border-violet-400/40 transition-all">
            <div className="w-12 h-12 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 mb-6">
              <Cpu className="w-6 h-6" />
            </div>
            <h3 className="text-xl font-bold text-white mb-2">Multi-Agent Architecture</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Seven specialized AI agents work in unison: Inventory Sync, Content Studio, Social Scheduler, Comment Engagement, Bilingual Support, Analytics Rollup, and Orchestrator.
            </p>
          </div>

          <div className="p-8 rounded-3xl bg-[#07111d]/90 border border-white/10 backdrop-blur-sm relative group hover:border-emerald-400/40 transition-all">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mb-6">
              <Globe2 className="w-6 h-6" />
            </div>
            <h3 className="text-xl font-bold text-white mb-2">Bilingual by Design</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Built for modern international commerce with native bilingual support in English and Urdu, enabling frictionless customer communication across regional and global markets.
            </p>
          </div>
        </div>

        {/* The Digital FTE Story */}
        <div className="bg-[#07111d]/95 border border-white/10 rounded-3xl p-8 sm:p-12 mb-20 relative overflow-hidden">
          <div className="max-w-3xl">
            <span className="text-xs font-bold text-amber-400 uppercase tracking-widest block mb-2">Our Origin</span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white mb-6">
              Why We Built Digital FTE
            </h2>
            <div className="space-y-4 text-slate-300 text-sm sm:text-base leading-relaxed">
              <p>
                Every growing e-commerce store hits the same invisible ceiling. As order volumes increase, store owners find themselves bogged down in low-level administrative churn: manual catalog synchronization, crafting endless daily social media captions, handling repetitive order tracking messages, and recalculating daily P&L.
              </p>
              <p>
                Hiring a human full-time employee for each of these tasks costs thousands of dollars a month and requires constant supervision. Existing software plugins only created more disconnected dashboards.
              </p>
              <p>
                We asked a simple question: <strong className="text-white">What if you could hire a single digital employee that never sleeps, never forgets stock levels, generates studio-grade social posts, and talks to customers 24/7?</strong>
              </p>
              <p>
                That is <span className="text-amber-300 font-semibold">Digital FTE</span>. Powered by FastAPI, Google Gemini 2.5, and resilient Redis event streams, our platform acts as your tireless co-pilot, driving growth while giving you your time back.
              </p>
            </div>
          </div>
        </div>

        {/* Core Principles */}
        <div className="mb-20">
          <div className="text-center mb-12">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white">Our Engineering Principles</h2>
            <p className="text-sm text-slate-400 mt-2">What sets our autonomous systems apart</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 flex items-start gap-4">
              <ShieldCheck className="w-6 h-6 text-emerald-400 shrink-0 mt-1" />
              <div>
                <h4 className="text-base font-bold text-white">Data Sovereignty & Privacy First</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Your store catalog and customer metrics are strictly confidential. We enforce a zero public training policy with enterprise LLM providers.
                </p>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 flex items-start gap-4">
              <HeartHandshake className="w-6 h-6 text-amber-400 shrink-0 mt-1" />
              <div>
                <h4 className="text-base font-bold text-white">Human-in-the-Loop Safeguards</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  You stay in command. Keep any agent in autonomous autopilot or require one-click approval before posts or inventory updates go live.
                </p>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 flex items-start gap-4">
              <Zap className="w-6 h-6 text-yellow-400 shrink-0 mt-1" />
              <div>
                <h4 className="text-base font-bold text-white">Sub-Second Execution Speed</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Built on high-performance asynchronous Python FastAPI and Redis streams for real-time customer support response in under 1.2 seconds.
                </p>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 flex items-start gap-4">
              <Users className="w-6 h-6 text-blue-400 shrink-0 mt-1" />
              <div>
                <h4 className="text-base font-bold text-white">Built For Real Store Owners</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  No complex coding or prompt engineering needed. Connect your Shopify or WooCommerce store in 60 seconds and let the AI do the heavy lifting.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* CTA Box */}
        <div className="text-center p-10 rounded-3xl bg-gradient-to-r from-amber-500/20 via-yellow-500/10 to-amber-500/20 border border-amber-400/30">
          <h3 className="text-2xl sm:text-3xl font-extrabold text-white mb-3">
            Ready to hire your first AI Employee?
          </h3>
          <p className="text-sm text-slate-300 max-w-xl mx-auto mb-6">
            Join forward-thinking e-commerce brands automating their stores with Digital FTE today.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/home-new"
              className="px-6 py-3 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-400 text-[#06111b] font-bold text-sm hover:shadow-xl hover:shadow-amber-500/20 transition-all flex items-center gap-2"
            >
              <span>Start Free 14-Day Trial</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/contact"
              className="px-6 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-sm transition-all"
            >
              Talk to Our Team
            </Link>
          </div>
        </div>

      </main>

      <Footer />
    </div>
  );
}