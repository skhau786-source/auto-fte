"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { Footer } from "../components/Footer";
import { 
  FileCheck, 
  Scale, 
  Zap, 
  CreditCard, 
  ShieldAlert, 
  Layers, 
  ArrowLeft,
  HelpCircle
} from "lucide-react";

export default function TermsAndConditionsPage() {
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

      {/* HEADER NAVBAR */}
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
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-[#09151f] text-amber-200 border border-amber-300/20 hover:bg-[#11253c] transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Home</span>
          </Link>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="pt-32 pb-20 px-6 sm:px-12 max-w-4xl mx-auto relative z-10">
        
        {/* Title Header */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-300 text-xs font-bold uppercase tracking-wider mb-4">
            <Scale className="w-4 h-4 text-amber-400" />
            Legal Agreement
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white">
            Terms & Conditions
          </h1>
          <p className="mt-3 text-slate-400 text-sm sm:text-base max-w-xl mx-auto">
            Last updated: <span className="text-amber-300 font-semibold">September 2026</span> • Please read these terms carefully before deploying Digital FTE.
          </p>
        </motion.div>

        {/* Detailed Sections */}
        <div className="space-y-10 text-slate-300 text-sm sm:text-base leading-relaxed">
          
          {/* Section 1 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <FileCheck className="w-5 h-5 text-amber-400" />
              1. Agreement to Terms
            </h2>
            <p>
              By accessing or using the <strong className="text-white">Digital FTE</strong> platform (the "Service"), you agree to be bound by these Terms and Conditions. If you are using the Service on behalf of a company, online store, or business entity, you represent that you have the full legal authority to bind that entity.
            </p>
          </section>

          {/* Section 2 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <Zap className="w-5 h-5 text-amber-400" />
              2. Nature of the Autonomous AI Employee
            </h2>
            <p className="mb-3">
              Digital FTE provides automated software agents powered by large language models (Google Gemini) and API integrations (Shopify, Meta, TikTok, etc.) to perform e-commerce management tasks:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong className="text-white">Autonomous Actions:</strong> When configured in full autonomous mode, the agents may publish social media posts, reply to public comments, answer customer chat inquiries, and alert on low stock levels without manual confirmation.</li>
              <li><strong className="text-white">Human-in-the-Loop Controls:</strong> You retain the ability to set any agent into "Approval Required" mode, enabling manual review of generated captions, images, or answers before dispatch.</li>
              <li><strong className="text-white">Supervision:</strong> You are responsible for monitoring the overall settings, discount parameters, and brand voice guidelines provided to your AI agents.</li>
            </ul>
          </section>

          {/* Section 3 */}
          <section id="refund" className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <CreditCard className="w-5 h-5 text-amber-400" />
              3. Subscription, Free Trial & Cancellations
            </h2>
            <ul className="list-disc pl-6 space-y-3">
              <li><strong className="text-white">Free Trial:</strong> New accounts receive access to explore the core platform and connect one store without requiring credit card details upfront.</li>
              <li><strong className="text-white">Billing Cycles:</strong> Paid plans (Pro FTE) are billed in advance on a monthly or annual basis. Subscriptions renew automatically unless cancelled prior to the renewal date.</li>
              <li><strong className="text-white">Cancellation Policy:</strong> You may cancel your subscription at any time directly through your dashboard. Cancellation takes effect at the end of the current billing cycle.</li>
              <li><strong className="text-white">Refunds:</strong> We provide a 7-day money-back guarantee for initial annual plan purchases if the service does not meet your technical expectations.</li>
            </ul>
          </section>

          {/* Section 4 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <Layers className="w-5 h-5 text-amber-400" />
              4. Intellectual Property & Marketing Content
            </h2>
            <p className="mb-3">
              <strong className="text-white">You own 100% of your business assets:</strong> All product listings, brand logos, images, descriptions, customer data, and AI-generated social posts created by Digital FTE for your store are your exclusive property.
            </p>
            <p>
              Digital FTE and its licensors retain ownership of the core platform software, agent architectures, algorithms, and interface designs.
            </p>
          </section>

          {/* Section 5 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <ShieldAlert className="w-5 h-5 text-amber-400" />
              5. Limitation of Liability
            </h2>
            <p className="mb-3">
              While our AI agents operate with high precision thresholds, AI-generated content may occasionally require human moderation. To the maximum extent permitted by applicable law:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-slate-300">
              <li>Digital FTE is not liable for third-party platform API outages (e.g. Shopify maintenance, Meta Graph API rate limits, or internet downtime).</li>
              <li>Store owners are responsible for ensuring that product pricing, stock availability, and promotional promises conform to local trade and consumer protection regulations.</li>
              <li>Digital FTE's aggregate liability under any claim arising out of these terms shall not exceed the amount paid by you in the 3 months preceding the claim.</li>
            </ul>
          </section>

          {/* Section 6 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <HelpCircle className="w-5 h-5 text-amber-400" />
              6. Questions & Legal Inquiries
            </h2>
            <p className="mb-3">
              For any questions concerning these Terms and Conditions or to request a customized enterprise service level agreement (SLA), please contact:
            </p>
            <div className="p-4 rounded-xl bg-white/5 border border-white/10 space-y-1 text-sm">
              <p><strong className="text-white">Legal Inquiries:</strong> legal@digitalfte.ai</p>
              <p><strong className="text-white">Support Desk:</strong> support@digitalfte.ai</p>
            </div>
          </section>

        </div>

      </main>

      <Footer />
    </div>
  );
}
