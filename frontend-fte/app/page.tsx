"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useGoogleLogin } from "@react-oauth/google";
import {
  Mail,
  Lock,
  User,
  Eye,
  EyeOff,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  ShoppingBag,
  Chrome,
  TrendingUp,
  ShieldCheck,
  AlertCircle,
  MessageSquare,
  Loader2,
  AtSign,
} from "lucide-react";
import { InteractiveRobot } from "./components/InteractiveRobot";
import BusinessDashboard from "./components/BusinessDashboard";
import {
  authApi,
  tokenStore,
  isUnauthorized,
  type AuthUser,
} from "@/lib/api";

// ───────────────────────────────────────────────────────────────────
// Types & helpers
// ───────────────────────────────────────────────────────────────────

type View = "landing" | "auth";
type AuthMode = "signin" | "signup";

interface Toast {
  id: string;
  message: string;
  type: "success" | "info" | "error";
}

let toastSeq = 0;

function displayName(email: string): string {
  const part = email.split("@")[0];
  return part ? part.charAt(0).toUpperCase() + part.slice(1) : "there";
}

// ───────────────────────────────────────────────────────────────────
// Main page
// ───────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [view, setView] = useState<View>("landing");
  const [authMode, setAuthMode] = useState<AuthMode>("signin");

  // Auth form state
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Focus states for the robot's reactions
  const [isEmailFocused, setIsEmailFocused] = useState(false);
  const [isPasswordFocused, setIsPasswordFocused] = useState(false);
  const [isFullNameFocused, setIsFullNameFocused] = useState(false);

  // Session state
  const [user, setUser] = useState<AuthUser | null>(null);
  const [restoringSession, setRestoringSession] = useState(true);

  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dailyOrders, setDailyOrders] = useState(250);

  const showToast = useCallback((message: string, type: Toast["type"] = "success") => {
    const id = `${Date.now()}-${toastSeq++}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4500);
  }, []);

  // Restore session from a stored token (page refresh keeps you logged in).
  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      if (!tokenStore.get()) {
        setRestoringSession(false);
        return;
      }
      try {
        const res = await authApi.me();
        if (!cancelled) setUser(res.user);
      } catch {
        tokenStore.clear();
      } finally {
        if (!cancelled) setRestoringSession(false);
      }
    };
    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setView("landing");
    setAuthMode("signin");
    setEmail("");
    setPassword("");
    setFullName("");
    setUsername("");
    setFormError(null);
    showToast("Logged out successfully.", "info");
  }, [showToast]);

  const goToAuth = useCallback((mode: AuthMode) => {
    setAuthMode(mode);
    setFormError(null);
    setView("auth");
  }, []);

  // Backend notices such as "Username or email already registered" are already
  // user-friendly; keep them, otherwise use a generic message.
  const friendlyAuthError = (msg: string): string => msg || "Couldn't sign you in. Please try again.";

  // ── Local signup / signin ──

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!email.trim()) {
      setFormError("Please enter your email address.");
      return;
    }
    if (!password) {
      setFormError("Please enter your password.");
      return;
    }
    if (authMode === "signup") {
      if (!fullName.trim()) {
        setFormError("Please enter your full name.");
        return;
      }
      if (!username.trim() || username.trim().length < 3) {
        setFormError("Please choose a username of at least 3 characters.");
        return;
      }
      if (password.length < 8) {
        setFormError("Password must be at least 8 characters long.");
        return;
      }
      if (!/\d/.test(password)) {
        setFormError("Password must contain at least one number.");
        return;
      }
      if (!/[A-Z]/.test(password)) {
        setFormError("Password must contain at least one capital letter.");
        return;
      }
    }

    setLoading(true);
    try {
      const res =
        authMode === "signup"
          ? await authApi.signup({
              username: username.trim(),
              email: email.trim(),
              password,
              full_name: fullName.trim() || undefined,
            })
          : await authApi.login(email.trim(), password);

      if (res.access_token) tokenStore.set(res.access_token);
      setUser(res.user);
      setPassword("");
      setFormError(null);
      showToast(
        authMode === "signup"
          ? `Account created — welcome, ${displayName(res.user.email)}!`
          : `Welcome back, ${displayName(res.user.email)}!`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      if (isUnauthorized(err)) {
        setFormError("That email and password don't match our records.");
      } else {
        setFormError(friendlyAuthError(msg));
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Google sign-in (sends the Google ID token to the backend) ──

  const googleLogin = useGoogleLogin({
    scope: "openid email profile",
    flow: "implicit",
    onSuccess: async (codeResponse) => {
      const idToken = (codeResponse as { id_token?: string }).id_token;
      if (!idToken) {
        showToast(
          "Google sign-in couldn't start — please use email sign-in for now.",
          "error"
        );
        return;
      }
      setLoading(true);
      try {
        const res = await authApi.google(idToken);
        if (res.access_token) tokenStore.set(res.access_token);
        setUser(res.user);
        showToast(`Welcome, ${displayName(res.user.email)}!`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Google sign-in failed.";
        showToast(
          "Google sign-in isn't configured for this app yet. Use email sign-in, or contact your administrator.",
          "error"
        );
        setFormError(friendlyAuthError(msg));
      } finally {
        setLoading(false);
      }
    },
    onError: () => {
      showToast("Google sign-in was cancelled or failed. Please try again.", "error");
    },
  });

  const handleForgotPassword = () => {
    showToast(
      "Password reset isn't available yet — please contact support for help with your account.",
      "info"
    );
  };

  const isAuthenticated = Boolean(user);

  if (restoringSession) {
    return (
      <div className="min-h-screen bg-[#F5F3FF] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
      </div>
    );
  }

  // ── Business dashboard (real backend data) ──
  if (isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#F5F3FF] text-slate-900 font-sans">
        <BusinessDashboard userEmail={user!.email} onLogout={handleLogout} />
      </div>
    );
  }

  return (
    <div id="auth-screen-root" className="min-h-screen bg-[#F5F3FF] text-slate-900 flex flex-col font-sans transition-all duration-300">
      {/* Toast overlay */}
      <div id="toast-container" className="fixed top-5 right-5 z-50 flex flex-col gap-3 max-w-sm w-full">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`p-4 rounded-xl shadow-lg border flex items-center justify-between gap-3 animate-bounce-short transition-all duration-300 ${
              toast.type === "success"
                ? "bg-emerald-50/95 border-emerald-200 text-emerald-800"
                : toast.type === "error"
                ? "bg-rose-50/95 border-rose-200 text-rose-800"
                : "bg-violet-50/95 border-violet-200 text-violet-800"
            }`}
          >
            <div className="flex items-center gap-2.5">
              {toast.type === "success" && <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />}
              {toast.type === "error" && <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />}
              {toast.type === "info" && <Sparkles className="w-5 h-5 text-violet-600 shrink-0 animate-spin-slow" />}
              <p className="text-sm font-medium">{toast.message}</p>
            </div>
            <button
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              className="text-xs font-semibold opacity-60 hover:opacity-100 transition-opacity"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Header */}
      <header id="app-header" className="border-b border-violet-100/50 bg-white/80 backdrop-blur-md sticky top-0 z-40 px-6 sm:px-12 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3 cursor-pointer group" onClick={() => setView("landing")}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-violet-500/20 group-hover:scale-105 transition-transform">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-violet-950">Digital FTE</h1>
            <p className="text-[10px] font-bold text-violet-600 tracking-widest uppercase animate-pulse">E-Commerce Autonomous AI</p>
          </div>
        </div>

        {view === "landing" && (
          <nav className="hidden lg:flex items-center gap-8 text-sm font-semibold text-slate-600">
            <a href="#features" onClick={(e) => { e.preventDefault(); document.getElementById("features")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">Features</a>
            <a href="#how-it-works" onClick={(e) => { e.preventDefault(); document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">How It Works</a>
            <a href="#pricing" onClick={(e) => { e.preventDefault(); document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">Pricing</a>
            <a href="#about" onClick={(e) => { e.preventDefault(); document.getElementById("about")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">About</a>
          </nav>
        )}

        <div className="flex items-center gap-3">
          {view === "landing" ? (
            <button
              onClick={() => { goToAuth("signup"); showToast("Directing to trial signup view.", "info"); }}
              className="px-4 py-2.5 text-sm font-bold rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:shadow-lg text-white shadow-md shadow-violet-500/10 hover:shadow-violet-500/25 transition-all cursor-pointer"
            >
              Get Started
            </button>
          ) : (
            <button
              onClick={() => setView("landing")}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-violet-50 text-violet-700 border border-violet-100 hover:bg-violet-100 transition-all cursor-pointer"
            >
              <span>← Back to Home</span>
            </button>
          )}
        </div>
      </header>

      <main className={`flex-1 flex flex-col ${view === "landing" ? "py-6 px-4 sm:px-6 lg:px-8" : "justify-center py-6 px-4 sm:px-6 lg:px-8"}`}>
        {view === "landing" ? (
          <LandingPage onStartFreeTrial={() => { goToAuth("signup"); showToast("Let's set up your account.", "success"); }} onWatchDemo={() => showToast("Our demo walkthrough is coming soon.", "info")} dailyOrders={dailyOrders} setDailyOrders={setDailyOrders} />
        ) : (
          <AuthPanel
            mode={authMode}
            setMode={goToAuth}
            email={email}
            setEmail={setEmail}
            fullName={fullName}
            setFullName={setFullName}
            username={username}
            setUsername={setUsername}
            password={password}
            setPassword={setPassword}
            isPasswordVisible={isPasswordVisible}
            setIsPasswordVisible={setIsPasswordVisible}
            isEmailFocused={isEmailFocused}
            setIsEmailFocused={setIsEmailFocused}
            isPasswordFocused={isPasswordFocused}
            setIsPasswordFocused={setIsPasswordFocused}
            isFullNameFocused={isFullNameFocused}
            setIsFullNameFocused={setIsFullNameFocused}
            loading={loading}
            error={formError}
            onSubmit={handleAuthSubmit}
            onGoogle={googleLogin}
            onForgotPassword={handleForgotPassword}
          />
        )}
      </main>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Landing page (marketing — static content, no fake business data)
// ───────────────────────────────────────────────────────────────────

function LandingPage({ onStartFreeTrial, onWatchDemo, dailyOrders, setDailyOrders }: {
  onStartFreeTrial: () => void;
  onWatchDemo: () => void;
  dailyOrders: number;
  setDailyOrders: (n: number) => void;
}) {
  return (
    <div id="landing-view-root" className="w-full max-w-7xl mx-auto flex flex-col gap-20 py-4 animate-fade-in">
      {/* Hero */}
      <div id="hero" className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center py-4">
        <div className="lg:col-span-7 flex flex-col items-start text-left">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-100 text-violet-700 text-xs font-bold mb-6 tracking-wide uppercase shadow-sm hover:shadow-md hover:bg-violet-200 transition-all animate-pulse">
            <Sparkles className="w-3.5 h-3.5 text-violet-600 animate-pulse" />
            <span>AI-POWERED E-COMMERCE EMPLOYEE</span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-[1.1] mb-6 animate-fade-in">
            Your AI Digital FTE, <br />
            <span className="bg-gradient-to-r from-violet-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent animate-pulse">Working 24/7 for You.</span>
          </h1>
          <p className="text-base sm:text-lg text-slate-600 max-w-xl leading-relaxed mb-8 animate-fade-in-delay">
            One AI Employee that manages your store, engages customers, creates content, and grows your revenue—so you can focus on what matters most.
          </p>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 mb-8 w-full sm:w-auto animate-fade-in-delay">
            <button
              onClick={onStartFreeTrial}
              className="px-8 py-4 text-sm font-bold text-center rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:shadow-xl hover:shadow-violet-500/40 text-white shadow-lg shadow-violet-500/20 transform hover:scale-105 active:scale-[0.98] transition-all cursor-pointer flex items-center justify-center gap-2 duration-300"
            >
              <span>Start Free Trial</span>
              <ArrowRight className="w-4 h-4 animate-bounce-right" />
            </button>
            <button
              onClick={onWatchDemo}
              className="px-8 py-4 text-sm font-bold text-center rounded-xl bg-white border-2 border-slate-200 hover:border-violet-400 hover:shadow-md hover:scale-105 text-slate-700 hover:bg-slate-50 transition-all cursor-pointer flex items-center justify-center gap-2 duration-300"
            >
              <div className="w-5 h-5 rounded-full bg-gradient-to-r from-violet-100 to-indigo-100 flex items-center justify-center text-slate-600 hover:text-violet-600 transition-colors">
                <svg className="w-2.5 h-2.5 fill-current ml-0.5" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              </div>
              <span>Watch Demo</span>
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-slate-500 text-xs font-semibold animate-fade-in-delay-2">
            <div className="flex items-center gap-1.5 hover:text-slate-700 transition-colors">
              <CheckCircle2 className="w-4.5 h-4.5 text-violet-500" />
              <span>No Credit Card</span>
            </div>
            <div className="flex items-center gap-1.5 hover:text-slate-700 transition-colors">
              <CheckCircle2 className="w-4.5 h-4.5 text-violet-500" />
              <span>Quick Setup</span>
            </div>
            <div className="flex items-center gap-1.5 hover:text-slate-700 transition-colors">
              <CheckCircle2 className="w-4.5 h-4.5 text-violet-500" />
              <span>Cancel Anytime</span>
            </div>
          </div>
        </div>

        <div className="lg:col-span-5 relative w-full max-w-lg mx-auto flex items-center justify-center min-h-[460px]">
          <div className="absolute w-[350px] h-[350px] rounded-full bg-violet-300/20 blur-3xl animate-float" />
          <div className="absolute w-[250px] h-[250px] rounded-full bg-cyan-200/20 blur-3xl -bottom-10 animate-float-delayed" />
          <div className="relative w-[280px] h-[280px] sm:w-[320px] sm:h-[320px] bg-gradient-to-br from-slate-950 to-violet-950 rounded-full border border-violet-500/30 flex items-center justify-center p-6 shadow-2xl shadow-violet-500/15 animate-float-delayed hover:shadow-violet-500/25 transition-shadow duration-300">
            <div className="absolute -inset-1.5 rounded-full border border-violet-500/10 animate-spin-slow" style={{ borderStyle: "dashed" }} />
            <div className="absolute -inset-8 rounded-full border border-violet-500/5 animate-pulse" />
            <div className="w-[180px] h-[180px] sm:w-[220px] sm:h-[220px] relative z-10 hover:scale-110 transition-transform duration-500">
              <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
            </div>
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[220px] sm:w-[250px] h-[20px] bg-gradient-to-r from-slate-900 to-slate-800 border-t border-slate-700/50 rounded-b-lg shadow-xl flex items-center justify-center px-10">
              <div className="w-12 h-1 bg-slate-700 rounded-full" />
            </div>
          </div>
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[200px] h-3 bg-violet-950/20 rounded-full blur-sm animate-pulse-shadow" />
        </div>
      </div>

      {/* Features */}
      <div id="features" className="py-12 border-t border-slate-100">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">Our Core Autonomous Roles</h2>
          <p className="text-sm text-slate-500 mt-2">Hire one Digital FTE to scale different aspects of your store.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { icon: <ShoppingBag className="w-6 h-6" />, title: 'Automated Inventory Agent', desc: 'Instantly syncs new vendor items, matches catalogs, tracks real-time stock levels, and dynamically optimizes pricing schemas to capture peak conversion rates.' },
            { icon: <MessageSquare className="w-6 h-6" />, title: 'Autonomous Support Desk', desc: 'Engages buyers instantly via integrated live chat, processes order changes, handles tracking inquiries, and dispatches refund approvals according to your store policy.' },
            { icon: <Sparkles className="w-6 h-6" />, title: 'Omni-Channel Content Factory', desc: 'Drafts highly engaging social posts, generates customized ad variants for Google & Meta, and writes SEO-optimized blog articles referencing current store trends.' },
          ].map((item, i) => (
            <div key={i} className="bg-white border border-slate-100 p-6 rounded-2xl shadow-sm hover:shadow-xl hover:border-violet-200 hover:scale-105 transition-all duration-300">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-50 to-indigo-50 text-violet-600 flex items-center justify-center mb-5">
                {item.icon}
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">{item.title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div id="how-it-works" className="py-12 border-t border-slate-100 bg-gradient-to-br from-slate-50 to-violet-50/30 rounded-3xl p-8 sm:p-12">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <span className="text-xs font-bold text-violet-600 tracking-widest uppercase bg-violet-100 px-3 py-1 rounded-full">WORKFLOW</span>
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight mt-3">Three Steps to 24/7 Autonomy</h2>
          <p className="text-sm text-slate-500 mt-2">Deploying your e-commerce AI container is simple.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
          {[
            { num: '1', title: 'Authenticate Store', desc: 'Securely connect your store catalog in 1-click using Shopify App Store or Google Workspace.' },
            { num: '2', title: 'Assign FTE Roles', desc: 'Select roles (Support Pilot, Inventory Sync, or Content Writer) and specify daily operating budgets.' },
            { num: '3', title: 'Go Live 24/7', desc: 'Your autonomous container scales up to drive engagement, manage logs, and grow your sales while you sleep.' },
          ].map((item, i) => (
            <div key={i} className="flex flex-col items-center text-center px-4">
              <div className="w-14 h-14 rounded-full bg-gradient-to-br from-violet-600 to-indigo-600 text-white font-black text-xl flex items-center justify-center mb-4 shadow-md shadow-violet-500/20 animate-bounce">
                {item.num}
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-2">{item.title}</h3>
              <p className="text-xs text-slate-500 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pricing + ROI estimate */}
      <div id="pricing" className="py-12 border-t border-slate-100">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center bg-white border border-slate-100 rounded-[32px] p-8 sm:p-12 shadow-xl shadow-slate-100">
          <div className="lg:col-span-6">
            <span className="text-xs font-bold text-cyan-600 tracking-widest uppercase bg-cyan-100 px-3 py-1 rounded-full">ROI ESTIMATOR</span>
            <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight mt-3">Estimate Your AI Gains</h2>
            <p className="text-sm text-slate-500 mt-2 mb-8 leading-relaxed">
              Drag the slider to enter your expected daily orders and see an <span className="font-bold text-slate-700">estimate</span> of hours saved.
              This is a planning tool only — your actual numbers come from your connected store.
            </p>
            <div className="space-y-6">
              <div>
                <div className="flex justify-between text-sm font-bold text-slate-700 mb-2">
                  <span>Expected daily orders:</span>
                  <span className="text-violet-600">{dailyOrders} orders</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="1500"
                  step="10"
                  value={dailyOrders}
                  onChange={(e) => setDailyOrders(Number(e.target.value))}
                  className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-violet-600"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-50 p-4 rounded-xl">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">EST. HOURS SAVED / MO</p>
                  <p className="text-2xl font-black text-violet-950 mt-1">{(dailyOrders * 0.16).toFixed(0)} Hrs</p>
                </div>
                <div className="bg-slate-50 p-4 rounded-xl">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">EST. ADDED REVENUE / MO</p>
                  <p className="text-2xl font-black text-emerald-600 mt-1">${(dailyOrders * 2.8 * 30).toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                </div>
              </div>
              <p className="text-[10px] text-slate-400">* Estimates based on typical e-commerce benchmarks. Not a guarantee.</p>
            </div>
          </div>
          <div className="lg:col-span-6 grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="border border-slate-100 p-6 rounded-2xl flex flex-col justify-between bg-slate-50/50">
              <div>
                <h3 className="text-base font-bold text-slate-900">7-Day Free Trial</h3>
                <p className="text-xs text-slate-400 mt-1">Perfect for proof-of-concept testing.</p>
                <p className="text-3xl font-black text-slate-900 mt-4">$0 <span className="text-xs text-slate-400 font-medium">/ 7 days</span></p>
              </div>
              <button
                onClick={onStartFreeTrial}
                className="w-full mt-6 py-2.5 px-4 text-xs font-bold text-violet-700 bg-white border border-violet-200 hover:bg-violet-50 rounded-xl transition-all cursor-pointer"
              >
                Deploy Free Trial
              </button>
            </div>
            <div className="border border-violet-500 bg-gradient-to-br from-violet-600 to-indigo-600 text-white p-6 rounded-2xl flex flex-col justify-between shadow-lg shadow-violet-500/25 relative overflow-hidden">
              <div className="absolute right-0 top-0 bg-violet-500 text-white text-[9px] font-bold px-3 py-1 rounded-bl-xl uppercase tracking-wider">Most Active</div>
              <div>
                <h3 className="text-base font-bold">Scaling Champion</h3>
                <p className="text-xs text-violet-200 mt-1">Full-time autonomous catalog & CRM.</p>
                <p className="text-3xl font-black mt-4">$49 <span className="text-xs text-violet-200 font-medium">/ month</span></p>
              </div>
              <button
                onClick={onStartFreeTrial}
                className="w-full mt-6 py-2.5 px-4 text-xs font-bold text-violet-950 bg-white hover:bg-violet-50 rounded-xl transition-all cursor-pointer"
              >
                Deploy Container
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* About / CTA */}
      <div id="about" className="bg-gradient-to-r from-violet-950 to-indigo-900 rounded-[32px] p-8 sm:p-12 text-center text-white relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />
        <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight relative z-10">Stop Managing. Start Orchestrating.</h2>
        <p className="text-sm text-violet-200 max-w-xl mx-auto mt-3 relative z-10 leading-relaxed">Unlock 24/7 growth capacity. Connect your Shopify or Google workspace today and let your Digital FTE do the work.</p>
        <button
          onClick={onStartFreeTrial}
          className="mt-8 px-8 py-4 bg-white hover:bg-violet-50 text-violet-950 font-bold text-sm rounded-xl transition-all shadow-xl hover:shadow-violet-900/40 relative z-10 cursor-pointer"
        >
          Launch Your First Agent Now
        </button>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Auth panel (real backend authentication)
// ───────────────────────────────────────────────────────────────────

function AuthPanel(props: {
  mode: AuthMode;
  setMode: (m: AuthMode) => void;
  email: string;
  setEmail: (v: string) => void;
  fullName: string;
  setFullName: (v: string) => void;
  username: string;
  setUsername: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  isPasswordVisible: boolean;
  setIsPasswordVisible: (v: boolean) => void;
  isEmailFocused: boolean;
  setIsEmailFocused: (v: boolean) => void;
  isPasswordFocused: boolean;
  setIsPasswordFocused: (v: boolean) => void;
  isFullNameFocused: boolean;
  setIsFullNameFocused: (v: boolean) => void;
  loading: boolean;
  error: string | null;
  onSubmit: (e: React.FormEvent) => void;
  onGoogle: () => void;
  onForgotPassword: () => void;
}) {
  const [isUsernameFocused, setIsUsernameFocused] = useState(false);

  const {
    mode, setMode, email, setEmail, fullName, setFullName, username, setUsername,
    password, setPassword, isPasswordVisible, setIsPasswordVisible,
    isEmailFocused, setIsEmailFocused, isPasswordFocused, setIsPasswordFocused,
    isFullNameFocused, setIsFullNameFocused, loading, error, onSubmit, onGoogle, onForgotPassword,
  } = props;

  return (
    <div id="unified-split-container" className="max-w-6xl w-full mx-auto bg-white border border-gray-100 shadow-2xl rounded-[32px] overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-[620px]">
      <div id="auth-left-panel" className="lg:col-span-6 p-6 sm:p-10 md:p-12 flex flex-col justify-between bg-white">
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2 lg:hidden">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold">
              <TrendingUp className="w-4 h-4" />
            </div>
            <span className="font-bold text-lg text-slate-900">Digital FTE</span>
          </div>
          <h2 className="text-3xl font-extrabold text-violet-950 tracking-tight">
            {mode === "signin" ? "Welcome back" : "Start free trial"}
          </h2>
          <p className="text-sm text-slate-500 mt-1.5">
            {mode === "signin"
              ? "Log in to command your autonomous e-commerce workforce."
              : "No credit card required. Instantly deploy your first AI employee."}
          </p>
        </div>

        <div className="flex-1 flex flex-col justify-center">
          <div className="relative flex p-1 bg-slate-100/80 rounded-xl mb-6 border border-slate-200/50">
            <button
              type="button"
              onClick={() => { setMode("signin"); }}
              className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                mode === "signin" ? "bg-white text-violet-950 shadow-sm" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => { setMode("signup"); }}
              className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                mode === "signup" ? "bg-white text-violet-950 shadow-sm" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Create Account
            </button>
          </div>

          <div className="grid grid-cols-1 gap-3 mb-6">
            <button
              type="button"
              onClick={onGoogle}
              disabled={loading}
              className="group flex items-center justify-center gap-2.5 py-3.5 px-4 rounded-xl border-2 border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50 hover:from-blue-100 hover:to-indigo-100 text-gray-800 text-xs font-bold transition-all duration-300 hover:shadow-lg hover:shadow-blue-200 hover:scale-105 active:scale-95 cursor-pointer disabled:opacity-50"
            >
              {loading ? (
                <div className="w-4 h-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
              ) : (
                <>
                  <Chrome className="w-5 h-5 text-[#4285F4] shrink-0 group-hover:scale-110 transition-transform" />
                  <span className="flex-1">Continue with Google</span>
                  <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                </>
              )}
            </button>
          </div>

          <div className="relative flex py-2 items-center mb-6">
            <div className="flex-grow border-t border-slate-100"></div>
            <span className="flex-shrink mx-4 text-[10px] text-slate-400 font-bold uppercase tracking-wider">Or connect via email</span>
            <div className="flex-grow border-t border-slate-100"></div>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className={`transition-all duration-300 overflow-hidden ${mode === "signup" ? "max-h-[85px] opacity-100 mb-4" : "max-h-0 opacity-0 pointer-events-none"}`}>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">Full Name</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <User className={`w-4 h-4 transition-colors ${isFullNameFocused ? "text-violet-600" : "text-slate-400"}`} />
                </div>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  onFocus={() => setIsFullNameFocused(true)}
                  onBlur={() => setIsFullNameFocused(false)}
                  className="block w-full pl-10 pr-3.5 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
                  placeholder="John Doe"
                />
              </div>
            </div>

            <div className={`transition-all duration-300 overflow-hidden ${mode === "signup" ? "max-h-[85px] opacity-100 mb-4" : "max-h-0 opacity-0 pointer-events-none"}`}>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">Username</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <AtSign className={`w-4 h-4 transition-colors ${isUsernameFocused ? "text-violet-600" : "text-slate-400"}`} />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onFocus={() => setIsUsernameFocused(true)}
                  onBlur={() => setIsUsernameFocused(false)}
                  className="block w-full pl-10 pr-3.5 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
                  placeholder="founder (min 3 characters)"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">Email</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <Mail className={`w-4 h-4 transition-colors ${isEmailFocused ? "text-violet-600" : "text-slate-400"}`} />
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setIsEmailFocused(true)}
                  onBlur={() => setIsEmailFocused(false)}
                  className="block w-full pl-10 pr-3.5 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
                  placeholder="you@yourstore.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">Password</label>
              <div className="relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <Lock className={`w-4 h-4 transition-colors ${isPasswordFocused ? "text-violet-600" : "text-slate-400"}`} />
                </div>
                <input
                  type={isPasswordVisible ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setIsPasswordFocused(true)}
                  onBlur={() => setIsPasswordFocused(false)}
                  className="block w-full pl-10 pr-11 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
                  placeholder={mode === "signup" ? "8+ chars, 1 number, 1 capital" : "Your password"}
                />
                <button
                  type="button"
                  onClick={() => setIsPasswordVisible(!isPasswordVisible)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-violet-600 transition-colors"
                >
                  {isPasswordVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {mode === "signin" && (
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={onForgotPassword}
                  className="text-[11px] font-bold text-violet-600 hover:text-violet-800 hover:underline transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-50 border border-rose-100 text-rose-700">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <p className="text-xs font-medium">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-60 disabled:hover:scale-100 cursor-pointer"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {mode === "signin" ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>
      </div>

      {/* Right panel — robot */}
      <div className="hidden lg:col-span-6 lg:flex relative bg-gradient-to-br from-violet-900 via-violet-800 to-indigo-950 p-10 items-center justify-center overflow-hidden">
        <div className="absolute w-[420px] h-[420px] rounded-full bg-violet-500/20 blur-3xl animate-float" />
        <div className="absolute w-[300px] h-[300px] rounded-full bg-cyan-400/10 blur-3xl -bottom-16 -left-10 animate-float-delayed" />
        <div className="relative flex flex-col items-center text-center z-10">
          <div className="w-64 h-64 rounded-full bg-gradient-to-br from-slate-950 to-violet-950 border border-violet-500/30 flex items-center justify-center p-6 shadow-2xl shadow-violet-500/25 animate-float">
            <div className="w-48 h-48">
              <InteractiveRobot
                isEmailFocused={isEmailFocused}
                isPasswordFocused={isPasswordFocused}
                isPasswordVisible={isPasswordVisible}
                isFullNameFocused={isFullNameFocused}
              />
            </div>
          </div>
          <div className="mt-8 bg-white/10 backdrop-blur-md border border-white/10 rounded-2xl px-6 py-4 max-w-sm">
            <p className="text-sm text-violet-100 font-medium">
              {mode === "signin"
                ? "Your autonomous e-commerce workforce is waiting for you."
                : "Deploy your first AI employee in minutes — no credit card required."}
            </p>
          </div>
          <div className="mt-5 flex items-center gap-2 text-[11px] text-violet-300">
            <ShieldCheck className="w-4 h-4" />
            <span>Your data stays private &amp; secure</span>
          </div>
        </div>
      </div>
    </div>
  );
}
