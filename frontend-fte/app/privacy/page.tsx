"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { SiteNav } from "../components/SiteNav";
import { Footer } from "../components/Footer";
import { 
  ShieldCheck, 
  Database, 
  KeyRound, 
  Cpu, 
  UserCheck, 
  FileText, 
  ArrowLeft,
  CheckCircle2
} from "lucide-react";

export default function PrivacyPolicyPage() {
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
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Enterprise Security & Privacy
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white">
            Privacy Policy
          </h1>
          <p className="mt-3 text-slate-400 text-sm sm:text-base max-w-xl mx-auto">
            Last updated: <span className="text-amber-300 font-semibold">September 2026</span> • Effective across all Digital FTE autonomous employee services.
          </p>
        </motion.div>

        {/* Highlight Box */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="p-6 rounded-2xl bg-gradient-to-r from-amber-500/10 via-violet-500/10 to-blue-500/10 border border-amber-400/30 mb-10"
        >
          <div className="flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-sm text-slate-200 leading-relaxed">
              <strong className="text-white block font-bold mb-1">Our Core Commitment to Store Owners:</strong>
              Your store catalog, customer purchase data, and order history are strictly confidential. 
              Digital FTE connects to your e-commerce channels exclusively to execute your authorized tasks. 
              <strong className="text-amber-300"> We never sell your data, and your store data is never used to train public AI models.</strong>
            </div>
          </div>
        </motion.div>

        {/* Detailed Sections */}
        <div className="space-y-10 text-slate-300 text-sm sm:text-base leading-relaxed">
          
          {/* Section 1 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <Database className="w-5 h-5 text-amber-400" />
              1. Information We Collect
            </h2>
            <p className="mb-3">
              To operate as your store's autonomous digital full-time employee, Digital FTE collects and synchronizes the following categories of data:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-slate-300">
              <li><strong className="text-white">Account Information:</strong> Name, work email address, hashed passwords, company name, and language preference.</li>
              <li><strong className="text-white">Store & Catalog Data:</strong> Product SKUs, inventory counts, pricing, descriptions, images, and category hierarchies synchronized via Shopify or WooCommerce APIs.</li>
              <li><strong className="text-white">Order & Customer Metadata:</strong> Order IDs, fulfillment status, delivery addresses, and purchase items required for customer support order lookups. (Credit card numbers are never collected or stored on our servers).</li>
              <li><strong className="text-white">Social Channel Authorizations:</strong> OAuth access tokens for Instagram, Facebook, TikTok, YouTube, and LinkedIn to schedule posts and read comments.</li>
            </ul>
          </section>

          {/* Section 2 */}
          <section id="data-security" className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <Cpu className="w-5 h-5 text-amber-400" />
              2. AI Processing & Zero Public Model Training Policy
            </h2>
            <p className="mb-3">
              Digital FTE utilizes the enterprise Google Gemini API to generate copywriting, summarize comments, analyze sentiment, and answer customer support inquiries.
            </p>
            <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-200 text-xs sm:text-sm space-y-2">
              <p className="font-bold flex items-center gap-2 text-emerald-300">
                <CheckCircle2 className="w-4 h-4" />
                Zero Public Training Guarantee
              </p>
              <p>
                Under our enterprise agreements, any prompt, product description, customer message, or e-commerce metric sent to Gemini is processed statelessly in ephemeral memory. Google does not retain your store content or use it to train future public foundation models.
              </p>
            </div>
          </section>

          {/* Section 3 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <KeyRound className="w-5 h-5 text-amber-400" />
              3. Encryption & Credentials Security
            </h2>
            <p className="mb-3">
              We implement industry-standard cryptographic safeguards across our infrastructure:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>All platform access tokens (Shopify access tokens, Meta Graph API tokens) are encrypted at rest using <strong className="text-white">AES-256 / Fernet key derivation</strong>.</li>
              <li>All API communication between your browser, our FastAPI backend, and third-party stores is strictly enforced over <strong className="text-white">TLS 1.3 / HTTPS</strong>.</li>
              <li>Webhook payloads from Shopify and WooCommerce are cryptographically validated using HMAC-SHA256 signatures before processing.</li>
            </ul>
          </section>

          {/* Section 4 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <UserCheck className="w-5 h-5 text-amber-400" />
              4. Data Ownership & Deletion Rights (GDPR / CCPA)
            </h2>
            <p className="mb-3">
              You retain 100% legal ownership of your business data. Store owners have the absolute right to:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>Request an export of all synced logs, scheduled posts, and AI agent execution records.</li>
              <li>Disconnect any e-commerce store or social media account instantly via the Settings dashboard.</li>
              <li>Request complete, permanent deletion of your account, database records, and encrypted tokens by contacting <span className="text-amber-300 font-mono">support@digitalfte.ai</span>. Upon receipt, all records are permanently purged within 72 business hours.</li>
            </ul>
          </section>

          {/* Section 5 */}
          <section className="bg-[#07111d]/90 border border-white/10 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-white flex items-center gap-2.5 mb-4">
              <FileText className="w-5 h-5 text-amber-400" />
              5. Contacting the Privacy Officer
            </h2>
            <p className="mb-4">
              If you have any questions, compliance requests, or security inquiries regarding our privacy standards, please reach out directly:
            </p>
            <div className="p-4 rounded-xl bg-white/5 border border-white/10 space-y-1 text-sm">
              <p><strong className="text-white">Data Protection Officer:</strong> Digital FTE Security Team</p>
              <p><strong className="text-white">Email:</strong> privacy@digitalfte.ai / support@digitalfte.ai</p>
              <p><strong className="text-white">Platform:</strong> Digital FTE E-Commerce Autonomous AI Suite</p>
            </div>
          </section>

        </div>

      </main>

      <Footer />
    </div>
  );
}
