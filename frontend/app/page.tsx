"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { GoogleLogin } from "@react-oauth/google";
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
  TrendingUp, 
  Check, 
  LogOut, 
  ShieldCheck, 
  AlertCircle,
  Globe,
  Instagram,
  Image,
  Calendar,
  MessageCircle,
  Settings,
  Loader2,
  Zap,
  Twitter,
  Facebook,
  Youtube,
  Music,
  LayoutDashboard,
  BookOpen,
  Package,
  Share2,
  Users,
  CreditCard,
  BarChart3,
  DollarSign,
  Bell,
  Bot,
  Play,
  Cpu,
  HelpCircle,
  ChevronDown,
  Star,
} from "lucide-react";
import { InteractiveRobot } from "./components/InteractiveRobot";
import { LaunchActivationScreen } from "./components/onboarding/LaunchActivationScreen";
import { SiteNav } from "./components/SiteNav";
import { Footer } from "./components/Footer";
import { buildApiUrl } from "./lib/config";
import { useLanguage } from "./lib/LanguageContext";

// --- MOCK DATA ---
const MOCK_PRODUCTS = [
  { id: 1, name: "Classic Cotton Tee", price: 24.99, stock: 142, status: "In Stock" },
  { id: 2, name: "Denim Jacket", price: 89.99, stock: 8, status: "Low Stock" },
  { id: 3, name: "Running Sneakers", price: 129.99, stock: 0, status: "Out of Stock" },
  { id: 4, name: "Leather Wallet", price: 45.00, stock: 67, status: "In Stock" },
  { id: 5, name: "Wool Beanie", price: 19.99, stock: 5, status: "Low Stock" },
  { id: 6, name: "Canvas Backpack", price: 74.99, stock: 34, status: "In Stock" },
];

const TOTAL_ONBOARDING_STEPS = 6;

// --- MAIN AUTH PAGE COMPONENT ---
export default function AuthPage() {
  const { t } = useLanguage();
  const [currentView, setCurrentView] = useState<"landing" | "auth">("landing");
  const [robotMotionPaused, setRobotMotionPaused] = useState(false);
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  
  // Field focus states
  const [isEmailFocused, setIsEmailFocused] = useState(false);
  const [isPasswordFocused, setIsPasswordFocused] = useState(false);
  const [isFullNameFocused, setIsFullNameFocused] = useState(false);

  // Simulation states
  const [loading, setLoading] = useState(false);
  const [authenticatedUser, setAuthenticatedUser] = useState<string | null>(null);
  const [flowMode, setFlowMode] = useState<"landing" | "auth" | "onboarding" | "dashboard">("landing");
  const [toasts, setToasts] = useState<{ id: string; message: string; type: "success" | "info" | "error" }[]>([]);
  
  // Forgot Password modal
  const [showForgotPassword, setShowForgotPassword] = useState(false);

  // Shopify Sync connection state
  const [shopifyConnected, setShopifyConnected] = useState(false);
  const [showShopifyModal, setShowShopifyModal] = useState(false);
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyConnecting, setShopifyConnecting] = useState(false);

  // SOCIAL MEDIA STATES
  const [instagramConnected, setInstagramConnected] = useState(false);
  const [facebookConnected, setFacebookConnected] = useState(false);
  const [tiktokConnected, setTiktokConnected] = useState(false);
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [twitterConnected, setTwitterConnected] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSubmitted, setForgotSubmitted] = useState(false);

  // AI Post Generator States
  const [showPostModal, setShowPostModal] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState('');
  const [imageStyle, setImageStyle] = useState('Modern');
  const [captionTone, setCaptionTone] = useState('Casual');
  const [generatedPost, setGeneratedPost] = useState<{ image: string; caption: string } | null>(null);

  // Schedule Post States
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Comments Dashboard States
  const [showCommentsModal, setShowCommentsModal] = useState(false);

  // Settings States
  const [showSettingsModal, setShowSettingsModal] = useState(false);

  // Global SEO States
  const [showSEOModal, setShowSEOModal] = useState(false);

  // LANDING PAGE INTERACTIVE SIMULATION & FAQ STATES
  const [simActiveTab, setSimActiveTab] = useState<"inventory" | "content" | "support">("inventory");
  const [simStockTriggered, setSimStockTriggered] = useState(false);
  const [simContentGenerating, setSimContentGenerating] = useState(false);
  const [simGeneratedPost, setSimGeneratedPost] = useState(false);
  const [simChatLanguage, setSimChatLanguage] = useState<"en" | "ur">("en");
  const [landingFaqOpen, setLandingFaqOpen] = useState<number | null>(null);

  // ONBOARDING FLOW STATES
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [showActivationScreen, setShowActivationScreen] = useState(false);
  const [, setIsReady] = useState(false);

  useEffect(() => {
    if (onboardingStep === TOTAL_ONBOARDING_STEPS && !showActivationScreen) {
      setShowActivationScreen(true);
    }
  }, [onboardingStep, showActivationScreen]);

  // 🆕 SIDEBAR DASHBOARD STATE
  const [activeTab, setActiveTab] = useState('dashboard');

  // Add a toast notification helper
  const PAGE_STATE_KEY = "digital-fte-page-state";
  const AUTH_STORAGE_KEY = "digital-fte-auth";

  const showToast = (message: string, type: "success" | "info" | "error" = "success") => {
    const id = Date.now().toString();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(PAGE_STATE_KEY);
      if (!raw) return;

      const parsed = JSON.parse(raw) as Partial<{
        authenticatedUser: string | null;
        currentView: "landing" | "auth";
        flowMode: "landing" | "auth" | "onboarding" | "dashboard";
        onboardingStep: number;
        showDashboard: boolean;
        showActivationScreen: boolean;
        authMode: "signin" | "signup";
        activeTab: string;
        shopifyConnected: boolean;
        instagramConnected: boolean;
        facebookConnected: boolean;
        tiktokConnected: boolean;
        youtubeConnected: boolean;
        twitterConnected: boolean;
        websiteUrl: string;
      }>;

      if (parsed.authenticatedUser !== undefined) setAuthenticatedUser(parsed.authenticatedUser);
      if (parsed.currentView) setCurrentView(parsed.currentView);
      if (parsed.flowMode) setFlowMode(parsed.flowMode);
      if (parsed.onboardingStep) setOnboardingStep(parsed.onboardingStep);
      if (parsed.showDashboard !== undefined) setShowDashboard(parsed.showDashboard);
      if (parsed.showActivationScreen !== undefined) setShowActivationScreen(parsed.showActivationScreen);
      if (parsed.authMode) setAuthMode(parsed.authMode);
      if (parsed.activeTab) setActiveTab(parsed.activeTab);
      if (parsed.shopifyConnected !== undefined) setShopifyConnected(parsed.shopifyConnected);
      if (parsed.instagramConnected !== undefined) setInstagramConnected(parsed.instagramConnected);
      if (parsed.facebookConnected !== undefined) setFacebookConnected(parsed.facebookConnected);
      if (parsed.tiktokConnected !== undefined) setTiktokConnected(parsed.tiktokConnected);
      if (parsed.youtubeConnected !== undefined) setYoutubeConnected(parsed.youtubeConnected);
      if (parsed.twitterConnected !== undefined) setTwitterConnected(parsed.twitterConnected);
      if (parsed.websiteUrl !== undefined) setWebsiteUrl(parsed.websiteUrl);
    } catch {
      // Ignore invalid persisted state.
    }
  }, []);

  useEffect(() => {
    try {
      const state = {
        authenticatedUser,
        currentView,
        flowMode,
        onboardingStep,
        showDashboard,
        showActivationScreen,
        authMode,
        activeTab,
        shopifyConnected,
        instagramConnected,
        facebookConnected,
        tiktokConnected,
        youtubeConnected,
        twitterConnected,
        websiteUrl,
      };

      window.localStorage.setItem(PAGE_STATE_KEY, JSON.stringify(state));

      if (authenticatedUser) {
        window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ user: authenticatedUser }));
      } else {
        window.localStorage.removeItem(AUTH_STORAGE_KEY);
      }
    } catch {
      // Ignore write failures.
    }
  }, [
    authenticatedUser,
    currentView,
    flowMode,
    onboardingStep,
    showDashboard,
    showActivationScreen,
    authMode,
    activeTab,
    shopifyConnected,
    instagramConnected,
    facebookConnected,
    tiktokConnected,
    youtubeConnected,
    twitterConnected,
    websiteUrl,
  ]);

  const normalizeUserEmail = (value?: string | null) => {
    const trimmedValue = value?.trim();
    return trimmedValue || "user@example.com";
  };

  // Extract a friendly display name from the user's email
  const getDisplayName = (emailValue: string | null) => {
    if (!emailValue) return "there";
    const namePart = emailValue.split("@")[0];
    if (!namePart) return "there";
    return namePart.charAt(0).toUpperCase() + namePart.slice(1);
  };

  // Derive a friendly site name from a website URL (falls back to a simple placeholder)
  const getDomainFromUrl = (url?: string) => {
    if (!url) return "saeedghani.pk";
    try {
      const u = new URL(url);
      return u.hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  };

  const getSiteNameFromUrl = (url?: string) => {
    const domain = getDomainFromUrl(url);
    if (!domain) return "Your Store";
    const name = domain.split(".")[0];
    const parts = name.split(/[-_]/).filter(Boolean).map(p => p.charAt(0).toUpperCase() + p.slice(1));
    return parts.join(' ') || domain;
  };

  const enterOnboardingFlow = (userEmail: string, successMessage: string) => {
    const safeEmail = normalizeUserEmail(userEmail);
    setAuthenticatedUser(safeEmail);
    setFlowMode("onboarding");
    setCurrentView("auth");
    setShowDashboard(false);
    setOnboardingStep(1);
    setLoading(false);
    setIsConnecting(false);
    setIsReady(false);
    setShopifyConnected(false);
    setInstagramConnected(false);
    setFacebookConnected(false);
    setTiktokConnected(false);
    setYoutubeConnected(false);
    setTwitterConnected(false);
    setWebsiteUrl('');
    setActiveTab('dashboard');
    showToast(successMessage, "success");
  };

  // Website URL Validation
  const validateWebsite = (url: string) => {
    try {
      const urlObj = new URL(url);
      if (urlObj.protocol !== 'https:') {
        showToast("⚠️ Please use HTTPS (secure) website", "error");
        return false;
      }
      const hostname = urlObj.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        showToast("⚠️ Please enter a live website URL", "error");
        return false;
      }
      const validTLDs = ['.com', '.shop', '.store', '.io', '.co', '.org', '.net', '.app', '.dev'];
      const hasValidTLD = validTLDs.some(tld => hostname.endsWith(tld));
      if (!hasValidTLD) {
        showToast("⚠️ Please enter a valid store domain", "error");
        return false;
      }
      return true;
    } catch {
      showToast("⚠️ Please enter a valid website URL", "error");
      return false;
    }
  };

  // Generate AI Post
  const generatePost = () => {
    const product = MOCK_PRODUCTS.find(p => p.id === Number(selectedProduct));
    if (!product) return;
    const captions = [
      `✨ Check out our latest ${product.name}! Perfect for your everyday style. Available now at a special price! #ShopNow #NewArrival`,
      `🔥 You're going to love our new ${product.name}! Premium quality at an affordable price. Don't miss out! #Trending #Quality`,
      `💎 Upgrade your lifestyle with our ${product.name}. Handpicked just for you. Shop now and experience the difference! #Luxury #Style`
    ];
    setGeneratedPost({
      image: '🖼️',
      caption: captions[Math.floor(Math.random() * captions.length)]
    });
    showToast("🎨 AI generated your post!", "success");
  };

  // Pre-populate input for testing ease
  

  const AUTH_TOKEN_KEY = "digital-fte-token";

  const extractAuthError = (data: unknown, fallback: string) => {
    const detail = (data as { detail?: unknown })?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      return (first?.msg || fallback).replace(/^Value error, /, "");
    }
    return fallback;
  };

  // Backend /auth/* response -> token save + onboarding
  const finishBackendAuth = (
    data: { access_token?: string; user?: { email?: string; full_name?: string | null } },
    successMessage: string
  ) => {
    try {
      if (data.access_token) window.localStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
    } catch {
      // Ignore storage write failures.
    }
    enterOnboardingFlow(data.user?.email || "", successMessage);
  };

  const postAuth = async (path: string, body: Record<string, unknown>) => {
    const response = await fetch(buildApiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(extractAuthError(data, "Authentication failed. Please try again."));
    }
    return data;
  };

  // Google id_token (credential) -> POST /auth/google
  const handleGoogleCredential = async (idToken?: string) => {
    if (!idToken) {
      showToast("Google login failed. Please try again.", "error");
      return;
    }
    setLoading(true);
    showToast("Authenticating with Google...", "info");
    try {
      const data = await postAuth("/auth/google", { id_token: idToken });
      const name = data.user?.full_name || "there";
      finishBackendAuth(data, `Welcome ${name}! Successfully logged in with Google.`);
    } catch (error) {
      setLoading(false);
      showToast(error instanceof Error ? error.message : "Google authentication failed.", "error");
    }
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      showToast("Please enter a valid email address.", "error");
      return;
    }
    if (authMode === "signup" && !fullName) {
      showToast("Please enter your full name.", "error");
      return;
    }
    if (!password) {
      showToast("Please enter your password.", "error");
      return;
    }

    setLoading(true);
    showToast(authMode === "signin" ? "Verifying secure credentials..." : "Provisioning Digital FTE container instance...", "info");

    try {
      if (authMode === "signin") {
        const data = await postAuth("/auth/login", { email: email.trim(), password });
        finishBackendAuth(data, "Login successful! Let's set up your store.");
      } else {
        const data = await postAuth("/auth/signup", {
          email: email.trim(),
          password,
          full_name: fullName.trim(),
        });
        finishBackendAuth(data, "Account created! Let's set up your store.");
      }
    } catch (error) {
      setLoading(false);
      showToast(error instanceof Error ? error.message : "Authentication failed.", "error");
    }
  };

  const handleForgotSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!forgotEmail) {
      showToast("Please enter your email.", "error");
      return;
    }
    setForgotSubmitted(true);
    showToast(`Password reset instruction secure payload dispatched to ${forgotEmail}`, "success");
    setTimeout(() => {
      setShowForgotPassword(false);
      setForgotSubmitted(false);
      setForgotEmail("");
    }, 3000);
  };

  // Check if any social account is connected
  const isAnySocialConnected = instagramConnected || facebookConnected || tiktokConnected || youtubeConnected || twitterConnected;

  // Logout function with full reset
  const handleLogout = () => {
    setAuthenticatedUser(null);
    setFlowMode("landing");
    setCurrentView("landing");
    setOnboardingStep(1);
    setShowDashboard(false);
    setShopifyConnected(false);
    setInstagramConnected(false);
    setFacebookConnected(false);
    setTiktokConnected(false);
    setYoutubeConnected(false);
    setTwitterConnected(false);
    setWebsiteUrl('');
    setIsConnecting(false);
    setIsReady(false);
    setGeneratedPost(null);
    setSelectedProduct('');
    setShowPostModal(false);
    setShowScheduleModal(false);
    setShowCommentsModal(false);
    setShowSettingsModal(false);
    setShowSEOModal(false);
    setActiveTab('dashboard');
    try { window.localStorage.removeItem(AUTH_STORAGE_KEY); } catch { }
    showToast("Logged out successfully.", "info");
  };

  const isAuthenticated = Boolean(authenticatedUser);
  const isDashboardActive = isAuthenticated && flowMode === "dashboard";

  return (
    <div id="auth-screen-root" className="min-h-screen bg-[#02040d] text-white flex flex-col font-sans transition-all duration-300">
      {/* Toast Overlay */}
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

      {/* HEADER SECTION */}
      <header id="app-header" className="border-b border-white/10 bg-[#04090f]/95 backdrop-blur-xl sticky top-0 z-40 px-6 sm:px-12 py-4 flex items-center justify-between">
        <div 
          className="flex items-center gap-3 cursor-pointer group"
          onClick={() => {
            handleLogout();
          }}
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-500 flex items-center justify-center text-[#06111b] font-bold shadow-lg shadow-amber-500/20 group-hover:scale-105 transition-transform">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-white">Digital FTE</h1>
            <p className="text-[10px] font-bold text-amber-300 tracking-widest uppercase animate-pulse">E-Commerce Autonomous AI</p>
          </div>
        </div>

        {currentView === "landing" && !authenticatedUser && (
          <SiteNav />
        )}

        <div className="flex items-center gap-3">
          {authenticatedUser ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-[#0f1f3f]/90 text-white border border-white/10 hover:bg-[#162a57]/95 transition-all cursor-pointer"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">{t("auth.logOut")}</span>
            </button>
          ) : currentView === "landing" ? (
            <button
              onClick={() => {
                setAuthMode("signup");
                setCurrentView("auth");
                showToast("Directing to trial signup view.", "info");
              }}
              className="px-4 py-2.5 text-sm font-bold rounded-xl bg-gradient-to-r from-amber-500 to-yellow-400 hover:shadow-lg text-[#06111b] shadow-md shadow-amber-500/20 transition-all cursor-pointer"
            >
              {t("auth.getStarted")}
            </button>
          ) : (
            <button
              onClick={() => {
                setCurrentView("landing");
                showToast("Returned to homepage.", "info");
              }}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-[#09151f] text-amber-200 border border-amber-300/20 hover:bg-[#11253c] transition-all cursor-pointer"
            >
              <span>{t("auth.backHome")}</span>
            </button>
          )}
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className={`flex-1 flex flex-col ${currentView === "landing" && !authenticatedUser ? "py-6 px-4 sm:px-6 lg:px-8" : "justify-center py-6 px-4 sm:px-6 lg:px-8"}`}>
        
        {isAuthenticated ? (
          isDashboardActive || showDashboard ? (
            // 🆕 SIDEBAR DASHBOARD - NEXT LEVEL
            <div className="flex h-[calc(100vh-80px)] w-full max-w-7xl mx-auto gap-4">
              
              {/* ===== SIDEBAR ===== */}
              <div className="w-64 bg-[#07111d]/85 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl p-4 flex flex-col shrink-0 overflow-y-auto">
                
                {/* Brand Logo */}
                <div className="flex items-center gap-3 px-3 py-4 border-b border-white/10">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-400 flex items-center justify-center text-[#06111b] font-bold shadow-lg shadow-amber-400/30">
                    <TrendingUp className="w-5 h-5" />
                  </div>
                  <div>
                    <h1 className="text-lg font-extrabold text-white">Digital FTE</h1>
                    <p className="text-[8px] font-bold text-amber-300 tracking-widest uppercase">AI EMPLOYEE</p>
                  </div>
                </div>

                {/* Robot Status */}
                <div className="flex flex-col items-center py-4 border-b border-slate-100/50">
                  <div className="w-28 h-28 bg-slate-950 rounded-2xl p-1 shadow-inner shadow-violet-950/20">
                    <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} compact showOrbitItems={false} />
                  </div>
                  <p className="text-xs font-bold text-violet-600 mt-2">FTE-01 "Apex"</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    <span className="text-[10px] text-emerald-600 font-medium">Online</span>
                  </div>
                  <div className="w-full mt-2">
                    <div className="flex justify-between text-[8px] text-slate-400">
                      <span>AI Power</span>
                      <span>87%</span>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-1.5 mt-0.5 overflow-hidden">
                      <div className="bg-gradient-to-r from-violet-500 to-indigo-600 h-1.5 rounded-full animate-pulse" style={{ width: '87%' }} />
                    </div>
                  </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 py-4 space-y-1">
                  {[
                    { icon: <LayoutDashboard className="w-4 h-4" />, label: t('dashboard.tabs.dashboard'), id: 'dashboard' },
                    { icon: <Package className="w-4 h-4" />, label: t('dashboard.tabs.inventory'), id: 'inventory' },
                    { icon: <Share2 className="w-4 h-4" />, label: t('dashboard.tabs.social'), id: 'social' },
                    { icon: <Users className="w-4 h-4" />, label: t('dashboard.tabs.customers'), id: 'customers' },
                    { icon: <CreditCard className="w-4 h-4" />, label: t('dashboard.tabs.payments'), id: 'payments' },
                    { icon: <BarChart3 className="w-4 h-4" />, label: t('dashboard.tabs.analytics'), id: 'analytics' },
                    { icon: <Settings className="w-4 h-4" />, label: t('dashboard.tabs.settings'), id: 'settings' },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setActiveTab(item.id)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-300 ${
                        activeTab === item.id
                          ? 'bg-gradient-to-r from-violet-600/10 to-indigo-600/10 text-violet-700 border border-violet-200/50 shadow-sm'
                          : 'text-slate-500 hover:bg-slate-100/50 hover:text-slate-700'
                      }`}
                    >
                      <span className={activeTab === item.id ? 'text-violet-600' : 'text-slate-400'}>
                        {item.icon}
                      </span>
                      <span className="text-sm font-medium">{item.label}</span>
                      {activeTab === item.id && (
                        <span className="ml-auto w-1.5 h-6 rounded-full bg-gradient-to-b from-violet-500 to-indigo-600"></span>
                      )}
                    </button>
                  ))}

                  {/* Live pages (real store data) */}
                  <div className="pt-3 mt-3 border-t border-slate-100/50">
                    <p className="px-4 pb-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">Live tools</p>
                    <Link
                      href="/inventory"
                      className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-slate-500 hover:bg-slate-100/50 hover:text-slate-700 transition-all duration-300"
                    >
                      <span className="text-slate-400"><Package className="w-4 h-4" /></span>
                      <span className="text-sm font-medium">Inventory Manager</span>
                    </Link>
                    <Link
                      href="/knowledge-base"
                      className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-slate-500 hover:bg-slate-100/50 hover:text-slate-700 transition-all duration-300"
                    >
                      <span className="text-slate-400"><BookOpen className="w-4 h-4" /></span>
                      <span className="text-sm font-medium">Knowledge Base</span>
                    </Link>
                  </div>
                </nav>

                {/* Logout Button */}
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-slate-500 hover:bg-red-50 hover:text-red-600 transition-all duration-300 border-t border-slate-100/50 pt-4"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="text-sm font-medium">{t("dashboard.logout")}</span>
                </button>
              </div>

              {/* ===== MAIN CONTENT ===== */}
              <div className="flex-1 bg-white/60 backdrop-blur-sm border border-white/20 rounded-3xl shadow-2xl p-6 overflow-y-auto">
                
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-extrabold text-slate-900">
                      {activeTab === 'dashboard' && t('dashboard.titles.dashboard')}
                      {activeTab === 'inventory' && t('dashboard.titles.inventory')}
                      {activeTab === 'social' && t('dashboard.titles.social')}
                      {activeTab === 'customers' && t('dashboard.titles.customers')}
                      {activeTab === 'payments' && t('dashboard.titles.payments')}
                      {activeTab === 'analytics' && t('dashboard.titles.analytics')}
                      {activeTab === 'settings' && t('dashboard.titles.settings')}
                    </h2>
                    <p className="text-sm text-slate-500">{t("dashboard.welcomeBack")}, {authenticatedUser}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <Bell className="w-5 h-5 text-slate-400 cursor-pointer hover:text-slate-600 transition-colors" />
                      <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse"></span>
                    </div>
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-violet-500/20">
                      {authenticatedUser?.charAt(0).toUpperCase() || 'U'}
                    </div>
                  </div>
                </div>

                {/* ===== DASHBOARD TAB ===== */}
                {activeTab === 'dashboard' && (
                  <>
                    <div className="rounded-3xl bg-gradient-to-r from-[#07111d] via-[#11253c] to-[#1b2f55] p-5 mb-6 text-white shadow-2xl shadow-amber-500/10 border border-amber-400/20">
                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                        <div>
                          <p className="text-[10px] uppercase tracking-[0.25em] text-violet-100 font-bold">{t("dashboard.aiHub")}</p>
                          <h3 className="text-xl font-black mt-1">{t("dashboard.runningSmooth")}</h3>
                          <p className="text-sm text-violet-50/90 mt-2">{t("dashboard.liveSync")}</p>
                        </div>
                        <div className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 backdrop-blur-sm">
                          <p className="text-[10px] uppercase tracking-[0.25em] text-violet-100">{t("dashboard.statusLabel")}</p>
                          <p className="text-lg font-bold">{t("dashboard.allOnline")}</p>
                        </div>
                      </div>
                    </div>

                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                      {[
                        { label: 'Total Revenue', value: '$12,847', icon: <DollarSign className="w-5 h-5" />, change: '+12%', color: 'from-emerald-400 to-green-500' },
                        { label: 'Total Orders', value: '1,247', icon: <ShoppingBag className="w-5 h-5" />, change: '+8%', color: 'from-blue-400 to-cyan-500' },
                        { label: 'Social Reach', value: '89.2K', icon: <Users className="w-5 h-5" />, change: '+23%', color: 'from-purple-400 to-violet-500' },
                        { label: 'Conversion', value: '4.2%', icon: <TrendingUp className="w-5 h-5" />, change: '+2.1%', color: 'from-orange-400 to-amber-500' },
                      ].map((stat, i) => (
                        <div key={i} className="p-5 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                          <div className="flex items-center justify-between">
                            <div className={`p-2.5 rounded-xl bg-gradient-to-br ${stat.color} text-white shadow-lg`}>
                              {stat.icon}
                            </div>
                            <span className="text-[10px] font-bold text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-full">{stat.change}</span>
                          </div>
                          <p className="text-2xl font-black text-slate-900 mt-3">{stat.value}</p>
                          <p className="text-xs font-medium text-slate-500">{stat.label}</p>
                        </div>
                      ))}
                    </div>

                    {/* Charts Row */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                      {/* Revenue Chart */}
                      <div className="p-5 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                        <div className="flex items-center justify-between mb-4">
                          <h4 className="text-sm font-bold text-slate-900">📈 Daily Revenue</h4>
                          <span className="text-[10px] text-slate-400">Last 7 days</span>
                        </div>
                        <div className="h-48 flex items-end gap-2">
                          {[65, 45, 80, 55, 90, 70, 85].map((height, i) => (
                            <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
                              <div 
                                className="w-full rounded-lg bg-gradient-to-t from-violet-500 to-indigo-600 transition-all duration-500 hover:scale-105"
                                style={{ height: `${height}%` }}
                              />
                              <span className="text-[8px] text-slate-400">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][i]}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Pie Chart */}
                      <div className="p-5 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                        <div className="flex items-center justify-between mb-4">
                          <h4 className="text-sm font-bold text-slate-900">🎯 Revenue Sources</h4>
                          <span className="text-[10px] text-slate-400">This month</span>
                        </div>
                        <div className="flex items-center gap-6">
                          <div className="relative w-36 h-36">
                            <svg viewBox="0 0 100 100" className="transform -rotate-90">
                              {[
                                { percent: 45, color: '#8b5cf6' },
                                { percent: 25, color: '#3b82f6' },
                                { percent: 20, color: '#ec4899' },
                                { percent: 10, color: '#f59e0b' },
                              ].reduce<React.ReactElement[]>((acc, item, i, arr) => {
                                const prev = arr.slice(0, i).reduce((sum, p) => sum + p.percent, 0);
                                const start = (prev / 100) * 2 * Math.PI;
                                const end = ((prev + item.percent) / 100) * 2 * Math.PI;
                                const x1 = 50 + 40 * Math.cos(start);
                                const y1 = 50 + 40 * Math.sin(start);
                                const x2 = 50 + 40 * Math.cos(end);
                                const y2 = 50 + 40 * Math.sin(end);
                                const largeArc = item.percent > 50 ? 1 : 0;
                                acc.push(
                                  <path
                                    key={i}
                                    d={`M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`}
                                    fill={item.color}
                                    className="transition-all duration-500 hover:opacity-80 cursor-pointer"
                                  />
                                );
                                return acc;
                              }, [])}
                              <circle cx="50" cy="50" r="24" fill="white" />
                            </svg>
                          </div>
                          <div className="space-y-1.5">
                            {[
                              { color: 'bg-violet-500', label: 'Products', value: '45%' },
                              { color: 'bg-blue-500', label: 'Services', value: '25%' },
                              { color: 'bg-pink-500', label: 'Subscriptions', value: '20%' },
                              { color: 'bg-amber-500', label: 'Other', value: '10%' },
                            ].map((item, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <div className={`w-3 h-3 rounded-full ${item.color}`} />
                                <span className="text-xs text-slate-600">{item.label}</span>
                                <span className="text-xs font-bold text-slate-800 ml-auto">{item.value}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Recent Activity */}
                    <div className="p-5 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-sm font-bold text-slate-900">🔄 Recent Activity</h4>
                        <button className="text-[10px] text-violet-500 font-bold hover:underline">View All</button>
                      </div>
                      <div className="space-y-2.5">
                        {[
                          { icon: '📸', text: 'AI Post generated for "Classic Cotton Tee"', time: '2 min ago' },
                          { icon: '📅', text: 'Post scheduled for Instagram at 10:00 AM', time: '15 min ago' },
                          { icon: '💬', text: 'New comment replied by AI on Instagram', time: '1 hour ago' },
                          { icon: '📈', text: 'SEO analysis updated for 12 keywords', time: '3 hours ago' },
                          { icon: '💰', text: 'New payment received: $124.99', time: '5 hours ago' },
                        ].map((item, i) => (
                          <div key={i} className="flex items-center gap-3 p-2.5 bg-slate-50/50 rounded-xl border border-slate-100/50 hover:bg-slate-100/50 transition-all">
                            <span className="text-xl">{item.icon}</span>
                            <div className="flex-1">
                              <p className="text-xs font-medium text-slate-700">{item.text}</p>
                              <p className="text-[8px] text-slate-400">{item.time}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                {/* ===== INVENTORY TAB ===== */}
                {activeTab === 'inventory' && (
                  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                    <Link
                      href="/inventory"
                      className="mb-4 flex items-center justify-between rounded-xl border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm font-semibold text-amber-300 hover:bg-amber-400/20"
                    >
                      <span>Open the live Inventory Manager (real stock, reservations &amp; history)</span>
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-bold text-slate-900">📦 Inventory Management</h3>
                      <button className="text-xs text-violet-600 font-bold hover:underline">+ Add Product</button>
                    </div>
                    <div className="grid grid-cols-3 gap-4 mb-6">
                      <div className="p-4 bg-violet-50 rounded-xl text-center border border-violet-100">
                        <p className="text-2xl font-black text-violet-700">{MOCK_PRODUCTS.length}</p>
                        <p className="text-xs text-slate-500">Total Products</p>
                      </div>
                      <div className="p-4 bg-emerald-50 rounded-xl text-center border border-emerald-100">
                        <p className="text-2xl font-black text-emerald-700">{MOCK_PRODUCTS.filter(p => p.status === "In Stock").length}</p>
                        <p className="text-xs text-slate-500">In Stock</p>
                      </div>
                      <div className="p-4 bg-amber-50 rounded-xl text-center border border-amber-100">
                        <p className="text-2xl font-black text-amber-700">{MOCK_PRODUCTS.filter(p => p.status === "Low Stock").length}</p>
                        <p className="text-xs text-slate-500">Low Stock</p>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                          <tr>
                            <th className="px-4 py-3 text-left font-bold">Product</th>
                            <th className="px-4 py-3 text-left font-bold">Price</th>
                            <th className="px-4 py-3 text-left font-bold">Stock</th>
                            <th className="px-4 py-3 text-left font-bold">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {MOCK_PRODUCTS.map((p) => (
                            <tr key={p.id} className="hover:bg-slate-50/50">
                              <td className="px-4 py-3 font-medium text-slate-900">{p.name}</td>
                              <td className="px-4 py-3 text-slate-600">${p.price.toFixed(2)}</td>
                              <td className="px-4 py-3 text-slate-600">{p.stock}</td>
                              <td className="px-4 py-3">
                                <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                                  p.status === "In Stock" ? "bg-emerald-100 text-emerald-800" :
                                  p.status === "Low Stock" ? "bg-amber-100 text-amber-800" :
                                  "bg-rose-100 text-rose-800"
                                }`}>{p.status}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* ===== SOCIAL MEDIA TAB ===== */}
                {activeTab === 'social' && (
                  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                    <h3 className="text-lg font-bold text-slate-900 mb-4">📱 Social Media Accounts</h3>
                    <div className="grid grid-cols-2 gap-4">
                      {[
                        { icon: <Instagram className="w-6 h-6 text-pink-600" />, name: 'Instagram', connected: instagramConnected },
                        { icon: <Facebook className="w-6 h-6 text-blue-600" />, name: 'Facebook', connected: facebookConnected },
                        { icon: <Music className="w-6 h-6 text-black" />, name: 'TikTok', connected: tiktokConnected },
                        { icon: <Youtube className="w-6 h-6 text-red-600" />, name: 'YouTube', connected: youtubeConnected },
                        { icon: <Twitter className="w-6 h-6 text-sky-600" />, name: 'Twitter', connected: twitterConnected },
                      ].map((item, i) => (
                        <div key={i} className={`p-4 rounded-xl border-2 transition-all ${item.connected ? 'border-emerald-500 bg-emerald-50/50' : 'border-slate-200 bg-white'}`}>
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              {item.icon}
                              <span className="text-sm font-bold text-slate-700">{item.name}</span>
                            </div>
                            <span className={`text-[10px] font-bold ${item.connected ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {item.connected ? '✅ Connected' : '○ Not Connected'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ===== CUSTOMERS TAB ===== */}
                {activeTab === 'customers' && (
                  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                    <h3 className="text-lg font-bold text-slate-900 mb-4">💬 Customers</h3>
                    <div className="space-y-3">
                      {[
                        { name: 'Sarah Johnson', email: 'sarah@example.com', orders: 12, spent: '$847' },
                        { name: 'Mike Chen', email: 'mike@example.com', orders: 8, spent: '$524' },
                        { name: 'Emma Wilson', email: 'emma@example.com', orders: 5, spent: '$312' },
                        { name: 'Alex Turner', email: 'alex@example.com', orders: 3, spent: '$189' },
                      ].map((customer, i) => (
                        <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100 hover:bg-violet-50/50 transition-all">
                          <div>
                            <p className="text-sm font-bold text-slate-900">{customer.name}</p>
                            <p className="text-xs text-slate-500">{customer.email}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-bold text-slate-900">{customer.orders} orders</p>
                            <p className="text-xs text-slate-500">{customer.spent}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ===== PAYMENTS TAB ===== */}
                {activeTab === 'payments' && (
                  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                    <h3 className="text-lg font-bold text-slate-900 mb-4">💳 Payments</h3>
                    <div className="grid grid-cols-3 gap-4 mb-6">
                      <div className="p-4 bg-emerald-50 rounded-xl text-center border border-emerald-100">
                        <p className="text-2xl font-black text-emerald-700">$12,847</p>
                        <p className="text-xs text-slate-500">Total Revenue</p>
                      </div>
                      <div className="p-4 bg-blue-50 rounded-xl text-center border border-blue-100">
                        <p className="text-2xl font-black text-blue-700">1,247</p>
                        <p className="text-xs text-slate-500">Transactions</p>
                      </div>
                      <div className="p-4 bg-purple-50 rounded-xl text-center border border-purple-100">
                        <p className="text-2xl font-black text-purple-700">$103</p>
                        <p className="text-xs text-slate-500">Average Order</p>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {[
                        { id: '#FTE-001', customer: 'Sarah Johnson', amount: '$124.99', status: 'Completed' },
                        { id: '#FTE-002', customer: 'Mike Chen', amount: '$89.50', status: 'Pending' },
                        { id: '#FTE-003', customer: 'Emma Wilson', amount: '$249.00', status: 'Completed' },
                      ].map((payment, i) => (
                        <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100 hover:bg-violet-50/50 transition-all">
                          <div>
                            <p className="text-sm font-bold text-slate-900">{payment.id}</p>
                            <p className="text-xs text-slate-500">{payment.customer}</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-bold text-slate-900">{payment.amount}</p>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              payment.status === 'Completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                            }`}>{payment.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

               {/* ===== ANALYTICS TAB ===== */}
{activeTab === 'analytics' && (
  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
    <h3 className="text-lg font-bold text-slate-900 mb-4">📈 Analytics Dashboard</h3>
    
    {/* Stats Cards */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {[
        { label: 'Total Visits', value: '24.8K', change: '+12%', color: 'from-violet-500 to-indigo-600' },
        { label: 'Bounce Rate', value: '32.4%', change: '-5%', color: 'from-emerald-400 to-green-500' },
        { label: 'Avg. Session', value: '4m 32s', change: '+8%', color: 'from-blue-400 to-cyan-500' },
        { label: 'Conversion', value: '4.2%', change: '+2.1%', color: 'from-orange-400 to-amber-500' },
      ].map((stat, i) => (
        <div key={i} className="p-4 bg-slate-50 rounded-xl border border-slate-100 hover:shadow-md transition-all">
          <p className="text-xs text-slate-500">{stat.label}</p>
          <p className="text-2xl font-black text-slate-900">{stat.value}</p>
          <span className={`text-[10px] font-bold ${stat.change.startsWith('+') ? 'text-emerald-600' : 'text-rose-600'}`}>
            {stat.change}
          </span>
        </div>
      ))}
    </div>

    {/* Charts Row */}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      
      {/* Weekly Traffic Chart */}
      <div className="p-4 bg-white rounded-xl border border-slate-200">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">📊 Weekly Traffic</h4>
          <span className="text-[10px] text-slate-400">Last 7 days</span>
        </div>
        <div className="h-48 flex items-end gap-2">
          {[
            { day: 'Mon', height: 65 },
            { day: 'Tue', height: 45 },
            { day: 'Wed', height: 80 },
            { day: 'Thu', height: 55 },
            { day: 'Fri', height: 90 },
            { day: 'Sat', height: 70 },
            { day: 'Sun', height: 85 },
          ].map((item, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1.5 group">
              <div 
                className="w-full rounded-lg bg-gradient-to-t from-violet-500 to-indigo-600 transition-all duration-500 hover:scale-105 hover:shadow-lg"
                style={{ height: `${item.height}%` }}
              >
                <div className="opacity-0 group-hover:opacity-100 transition-opacity text-center text-[8px] text-white font-bold -mt-5">
                  {item.height}%
                </div>
              </div>
              <span className="text-[8px] text-slate-400 font-medium">{item.day}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Revenue Growth Chart */}
      <div className="p-4 bg-white rounded-xl border border-slate-200">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">📈 Revenue Growth</h4>
          <span className="text-[10px] text-slate-400">This month</span>
        </div>
        <div className="h-48 flex items-end gap-2">
          {[
            { day: 'Mon', height: 20 },
            { day: 'Tue', height: 35 },
            { day: 'Wed', height: 45 },
            { day: 'Thu', height: 55 },
            { day: 'Fri', height: 70 },
            { day: 'Sat', height: 80 },
            { day: 'Sun', height: 95 },
          ].map((item, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1.5 group">
              <div 
                className="w-full rounded-lg bg-gradient-to-t from-emerald-400 to-green-500 transition-all duration-500 hover:scale-105 hover:shadow-lg"
                style={{ height: `${item.height}%` }}
              >
                <div className="opacity-0 group-hover:opacity-100 transition-opacity text-center text-[8px] text-white font-bold -mt-5">
                  ${(item.height * 2.5).toFixed(0)}
                </div>
              </div>
              <span className="text-[8px] text-slate-400 font-medium">{item.day}</span>
            </div>
          ))}
        </div>
      </div>
    </div>

    {/* Bottom Charts Row */}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
      
      {/* Platform Distribution - Pie Chart */}
      <div className="p-4 bg-white rounded-xl border border-slate-200 lg:col-span-1">
        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-4">📱 Platform Distribution</h4>
        <div className="flex flex-col items-center">
          <div className="relative w-32 h-32">
            <svg viewBox="0 0 100 100" className="transform -rotate-90">
              {[
                { percent: 45, color: '#8b5cf6' },
                { percent: 25, color: '#3b82f6' },
                { percent: 20, color: '#ec4899' },
                { percent: 10, color: '#f59e0b' },
              ].reduce<React.ReactElement[]>((acc, item, i, arr) => {
                const prev = arr.slice(0, i).reduce((sum, p) => sum + p.percent, 0);
                const start = (prev / 100) * 2 * Math.PI;
                const end = ((prev + item.percent) / 100) * 2 * Math.PI;
                const x1 = 50 + 40 * Math.cos(start);
                const y1 = 50 + 40 * Math.sin(start);
                const x2 = 50 + 40 * Math.cos(end);
                const y2 = 50 + 40 * Math.sin(end);
                const largeArc = item.percent > 50 ? 1 : 0;
                acc.push(
                  <path
                    key={i}
                    d={`M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z`}
                    fill={item.color}
                    className="transition-all duration-500 hover:opacity-80 cursor-pointer"
                  />
                );
                return acc;
              }, [])}
              <circle cx="50" cy="50" r="24" fill="white" />
            </svg>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3 w-full">
            {[
              { color: 'bg-violet-500', label: 'Mobile', value: '45%' },
              { color: 'bg-blue-500', label: 'Desktop', value: '25%' },
              { color: 'bg-pink-500', label: 'Tablet', value: '20%' },
              { color: 'bg-amber-500', label: 'Other', value: '10%' },
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <div className={`w-2.5 h-2.5 rounded-full ${item.color}`} />
                <span className="text-[9px] text-slate-600">{item.label}</span>
                <span className="text-[9px] font-bold text-slate-800 ml-auto">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top Pages */}
      <div className="p-4 bg-white rounded-xl border border-slate-200 lg:col-span-2">
        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-4">📄 Top Pages</h4>
        <div className="space-y-2.5">
          {[
            { page: '/products/classic-tee', views: '12,847', bounce: '32%' },
            { page: '/collections/summer', views: '8,234', bounce: '28%' },
            { page: '/blog/ai-ecommerce', views: '5,672', bounce: '45%' },
            { page: '/about', views: '3,891', bounce: '18%' },
          ].map((item, i) => (
            <div key={i} className="flex items-center justify-between p-2 bg-slate-50 rounded-lg hover:bg-violet-50 transition-all">
              <div>
                <p className="text-xs font-medium text-slate-700">{item.page}</p>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-xs text-slate-500">{item.views} views</span>
                <span className="text-[10px] font-medium text-emerald-600">{item.bounce} bounce</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
)}

                {/* ===== SETTINGS TAB ===== */}
                {activeTab === 'settings' && (
                  <div className="p-6 rounded-2xl bg-white/70 backdrop-blur-sm border border-slate-200/50">
                    <h3 className="text-lg font-bold text-slate-900 mb-4">⚙️ Settings</h3>
                    <div className="space-y-4">
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Account</h4>
                        <div className="mt-2 flex items-center justify-between">
                          <span className="text-sm font-medium text-slate-700">{authenticatedUser}</span>
                          <button className="text-xs text-violet-600 font-bold hover:underline">Change Email</button>
                        </div>
                      </div>
                      <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Connected Accounts</h4>
                        <div className="mt-2 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">Shopify</span>
                            <span className={`text-xs font-bold ${shopifyConnected ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {shopifyConnected ? '● Connected' : '○ Not Connected'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">Instagram</span>
                            <span className={`text-xs font-bold ${instagramConnected ? 'text-emerald-600' : 'text-amber-600'}`}>
                              {instagramConnected ? '● Connected' : '○ Not Connected'}
                            </span>
                          </div>
                        </div>
                      </div>
                      <button className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-slate-700 to-slate-900 text-white font-bold text-sm hover:shadow-xl transition-all">
                        💾 Save Settings
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            // ✅ ONBOARDING FLOW
            <div className="max-w-4xl w-full min-w-0 mx-auto bg-white/90 backdrop-blur-sm border border-violet-100/50 shadow-xl rounded-3xl overflow-hidden animate-fade-in">
              {/* Progress Bar */}
              <div className="bg-gradient-to-r from-[#07111d] via-[#11253c] to-[#1b2f55] p-6 text-white">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-xl font-bold">
                    {t("onboarding.setupTitle")}
                  </h2>
                  <span className="text-sm text-amber-200 bg-white/10 px-3 py-1 rounded-full">{t("onboarding.stepOf")} {onboardingStep} {t("onboarding.of")} {TOTAL_ONBOARDING_STEPS}</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2.5 overflow-hidden">
                  <div 
                    className="bg-gradient-to-r from-amber-400 to-yellow-300 h-2.5 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${(onboardingStep / TOTAL_ONBOARDING_STEPS) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-4 sm:p-8 min-w-0">
                {/* ========== STEP 1: Welcome ========== */}
                {onboardingStep === 1 && (
                  <div className="animate-fade-in text-center py-8 relative overflow-hidden rounded-3xl border border-amber-400/30 bg-gradient-to-br from-[#07111d] via-[#10233f] to-[#193a5d] p-8 text-white shadow-2xl shadow-amber-500/10">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.18),_transparent_45%)]" />
                    <div className="relative">
                      <div className="relative w-48 h-48 mx-auto">
                        <div className="absolute inset-0 rounded-full bg-amber-400/20 blur-2xl animate-pulse-slow" />
                        <div className="relative w-48 h-48 rounded-full flex items-center justify-center p-2">
                          <InteractiveRobot
                            isEmailFocused={false}
                            isPasswordFocused={false}
                            isPasswordVisible={false}
                            isFullNameFocused={false}
                            compact
                            showOrbitItems
                            orbitRadiusX={125}
                            orbitItemScale={0.95}
                          />
                        </div>
                      </div>

                      <div className="mt-4 flex justify-center">
                        <div className="relative bg-white/10 border border-amber-300/30 rounded-2xl px-5 py-2.5 shadow-md backdrop-blur-sm">
                          <p className="text-base font-bold text-amber-200">Hi {getDisplayName(authenticatedUser)}! 👋</p>
                          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white/10 border-t border-l border-amber-300/30 rotate-45" />
                        </div>
                      </div>

                      <h3 className="mt-4 cursor-pointer text-2xl font-extrabold text-white transition-all duration-300 hover:scale-105 hover:text-amber-200 active:scale-95">
                        {t("onboarding.step1.headline")}
                      </h3>
                      <p className="text-sm text-amber-100/90 mt-2">{t("onboarding.step1.sub")}</p>

                      <div className="mt-8 flex items-center justify-center max-w-md mx-auto">
                        {[
                          { icon: '🔗', label: t("onboarding.step1.connectStore") },
                          { icon: '📱', label: t("onboarding.step1.connectSocial") },
                          { icon: '🚀', label: t("onboarding.step1.readyLabel") },
                        ].map((item, i, arr) => (
                          <React.Fragment key={i}>
                            <div className="flex flex-col items-center gap-2">
                              <div
                                className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl border-2 transition-all duration-300 ${
                                  i === 0
                                    ? 'bg-gradient-to-br from-amber-500 to-yellow-400 border-amber-300 shadow-lg shadow-amber-500/30 animate-pulse scale-110 text-[#06111b]'
                                    : 'bg-white/10 border-white/10 text-slate-300'
                                }`}
                              >
                                {item.icon}
                              </div>
                              <p className={`text-[10px] font-bold ${i === 0 ? 'text-amber-200' : 'text-slate-300'}`}>{item.label}</p>
                            </div>
                            {i < arr.length - 1 && (
                              <div className="flex-1 h-0.5 bg-white/20 mx-2 mb-5 relative overflow-hidden rounded-full">
                                {i === 0 && (
                                  <div className="absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-amber-400 to-yellow-300 animate-pulse rounded-full" />
                                )}
                              </div>
                            )}
                          </React.Fragment>
                        ))}
                      </div>

                      <div className="w-full mt-8">
                        <button
                          onClick={() => setOnboardingStep(2)}
                          className="w-full py-3.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 text-[#06111b] font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                        >
                          {t("onboarding.step1.startBtn")} <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 2: Website URL ========== */}
                {onboardingStep === 2 && (
                  <div className="animate-fade-in rounded-3xl border border-amber-400/30 bg-gradient-to-br from-[#07111d] via-[#10233f] to-[#193a5d] p-4 sm:p-8 text-white shadow-2xl shadow-amber-500/10">
                    <div className="flex flex-col md:flex-row items-start gap-6">
                      <div className="flex-1 min-w-0 w-full md:-translate-x-3">
                        <div className="mb-4">
                              <span className="px-3 py-1 rounded-full bg-amber-500/15 text-amber-200 text-[10px] font-bold uppercase tracking-[0.25em] border border-amber-300/20">
                            {t("onboarding.step2.stepLabel")}
                          </span>
                          <h3 className="mt-3 text-lg font-bold text-white md:translate-x-2">{t("onboarding.step2.title")}</h3>
                          <p className="text-sm text-amber-100/90 md:translate-x-2">{t("onboarding.step2.desc")}</p>
                        </div>
                        <div className="mt-4 rounded-2xl bg-white/10 border border-white/10 p-4 backdrop-blur-sm">
                          <label className="block text-[10px] font-bold text-amber-200 uppercase tracking-wider mb-1.5">{t("onboarding.step2.urlLabel")}</label>
                          <div className="flex flex-col sm:flex-row gap-3">
                            <input
                              type="url"
                              value={websiteUrl}
                              onChange={(e) => setWebsiteUrl(e.target.value)}
                              placeholder={t("onboarding.step2.placeholder")}
                              className="flex-1 min-w-0 w-full px-4 py-3 border border-white/10 bg-white text-slate-900 rounded-xl text-sm focus:outline-none focus:ring-4 focus:ring-amber-500/20 focus:border-amber-500 transition-all duration-300"
                            />
                            <button
                              onClick={() => {
                                if (!validateWebsite(websiteUrl)) return;
                                setIsConnecting(true);
                                showToast("🔍 Verifying store...", "info");
                                setTimeout(() => {
                                  setIsConnecting(false);
                                  setShopifyConnected(true);
                                  setOnboardingStep(3);
                                  showToast("✅ Store verified & connected!", "success");
                                }, 2000);
                              }}
                              disabled={isConnecting}
                              className="w-full sm:w-auto shrink-0 px-6 py-3 rounded-xl bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 text-[#06111b] font-bold text-sm hover:shadow-xl hover:scale-105 transition-all duration-300 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                              {isConnecting ? <Loader2 className="w-5 h-5 animate-spin" /> : t("onboarding.step2.connectBtn")}
                            </button>
                          </div>
                          <p className="text-[8px] text-amber-100/80 mt-3 flex items-center gap-1">
                            <ShieldCheck className="w-3 h-3" /> {t("onboarding.step2.secureNote")}
                          </p>
                        </div>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot
                          isEmailFocused={false}
                          isPasswordFocused={false}
                          isPasswordVisible={false}
                          compact
                          orbitRadiusX={70}
                          orbitItemScale={0.72}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 3: Store Connected Confirmation ========== */}
                {onboardingStep === 3 && (
                  <div className="animate-fade-in space-y-6">
                    <div className="bg-gradient-to-br from-[#07111d] via-[#10233f] to-[#193a5d] rounded-3xl p-8 text-white shadow-2xl border border-amber-400/30 text-center relative overflow-hidden">
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(251,191,36,0.16),_transparent_40%)]" />
                      <div className="relative">
                        <div className="w-16 h-16 bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/20">
                          <CheckCircle2 className="w-10 h-10" />
                        </div>

                        <span className="px-3.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-bold border border-emerald-400/30 inline-flex items-center gap-1.5 mb-3">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                          {t("onboarding.step3.badge")}
                        </span>

                        <h3 className="text-2xl font-black text-white tracking-tight">
                          {t("onboarding.step3.title")}
                        </h3>
                        <div className="mt-6 bg-white/10 backdrop-blur-md border border-white/10 rounded-2xl p-4 text-left max-w-md mx-auto space-y-3">
                          <div className="flex items-center justify-between border-b border-white/10 pb-3">
                            <div className="flex items-center gap-3">
                              <img 
                                src={`https://www.google.com/s2/favicons?domain=${getDomainFromUrl(websiteUrl)}&sz=128`} 
                                alt="Store Favicon" 
                                className="w-10 h-10 rounded-xl bg-white p-1 border border-white/20 shadow-sm"
                              />
                              <div>
                                <p className="text-sm font-bold text-white">{getSiteNameFromUrl(websiteUrl)}</p>
                                <p className="text-[11px] text-amber-100/80">{websiteUrl || "https://saeedghani.pk"}</p>
                              </div>
                            </div>
                            <span className="px-2.5 py-1 rounded-lg bg-amber-200/90 text-amber-900 text-[10px] font-bold border border-amber-300">
                              {t("onboarding.step3.active")}
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                            <div className="p-2.5 bg-white/5 rounded-xl border border-white/5">
                              <span className="text-slate-400 block text-[9px] uppercase font-bold">{t("onboarding.step3.apiSync")}</span>
                              <span className="text-emerald-300 font-bold flex items-center gap-1 mt-0.5">
                                <Zap className="w-3 h-3 text-emerald-400" /> {t("onboarding.step3.operational")}
                              </span>
                            </div>
                            <div className="p-2.5 bg-white/5 rounded-xl border border-white/5">
                              <span className="text-slate-400 block text-[9px] uppercase font-bold">{t("onboarding.step3.security")}</span>
                              <span className="text-amber-300 font-bold flex items-center gap-1 mt-0.5">
                                <ShieldCheck className="w-3 h-3 text-amber-400" /> {t("onboarding.step3.encrypted")}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={() => setOnboardingStep((s) => Math.max(1, s - 1))}
                        className="flex-1 py-3.5 px-4 rounded-xl bg-white/10 border border-amber-300/20 text-amber-100 font-bold text-sm hover:bg-white/20 transition-all"
                      >
                        {t("onboarding.step3.backBtn")}
                      </button>
                      <button
                        onClick={() => setOnboardingStep(4)}
                        className="flex-1 py-3.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 text-[#06111b] font-bold text-sm hover:shadow-xl hover:scale-[1.01] transition-all flex items-center justify-center gap-2"
                      >
                        {t("onboarding.step3.nextBtn")} <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* STEP 5: Social Media Connection */}
                {onboardingStep === 4 && (
                  <div className="animate-fade-in space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-[#07111d] via-[#10233f] to-[#193a5d] border border-amber-400/30 p-3.5 rounded-2xl shadow-lg shadow-amber-500/10 text-white">
                      <div>
                        <h3 className="text-lg font-black text-white">{t("onboarding.step5.title")}</h3>
                        <p className="text-xs text-amber-200">{t("onboarding.step5.desc")}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
                      <div className="md:col-span-8 space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {[
                            { id: 'instagram', label: 'Instagram', handle: '@saeedghani.official', capabilities: 'Auto Reels • DM Bot', icon: <Instagram className="w-5 h-5 text-pink-600"/>, connected: instagramConnected, setter: setInstagramConnected },
                            { id: 'facebook', label: 'Facebook', handle: '@saeedghani.official', capabilities: 'Page Posts • Messenger Bot', icon: <Facebook className="w-5 h-5 text-blue-600"/>, connected: facebookConnected, setter: setFacebookConnected },
                            { id: 'tiktok', label: 'TikTok', handle: '@saeedghani', capabilities: 'Shorts • Sound Trends', icon: <Music className="w-5 h-5 text-slate-900"/>, connected: tiktokConnected, setter: setTiktokConnected },
                            { id: 'youtube', label: 'YouTube', handle: '@SaeedGhaniOfficial', capabilities: 'Shorts • SEO Descriptions', icon: <Youtube className="w-5 h-5 text-red-600"/>, connected: youtubeConnected, setter: setYoutubeConnected },
                            { id: 'twitter', label: 'Twitter / X', handle: '@SaeedGhaniPK', capabilities: 'Auto Threads • Support Bot', icon: <Twitter className="w-5 h-5 text-sky-500"/>, connected: twitterConnected, setter: setTwitterConnected },
                          ].map((item) => (
                            <div 
                              key={item.id}
                              onClick={() => item.setter(!item.connected)}
                              className={`p-3.5 rounded-2xl border-2 transition-all duration-300 cursor-pointer relative overflow-hidden ${
                                item.connected 
                                  ? 'border-emerald-500 bg-emerald-50/40 shadow-md shadow-emerald-500/10' 
                                  : 'border-slate-200 bg-white hover:border-violet-300 hover:shadow-sm'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex items-center gap-2.5">
                                  <div className="p-2 rounded-xl bg-slate-50 border border-slate-100">{item.icon}</div>
                                  <div>
                                    <span className="text-sm font-extrabold text-slate-900 block">{item.label}</span>
                                    <span className="text-[10px] font-semibold text-violet-600 block">{item.capabilities}</span>
                                  </div>
                                </div>
                                {item.connected ? (
                                  <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0"/>
                                ) : (
                                  <div className="w-5 h-5 rounded-full border-2 border-slate-300 shrink-0" />
                                )}
                              </div>

                              {item.connected && (
                                <div className="mt-2.5 pt-2 border-t border-emerald-200/60 flex items-center justify-between text-[10px]">
                                  <div className="flex items-center gap-2">
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-200/60 text-emerald-800 font-bold">Linked</span>
                                    <button
                                      type="button"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        item.setter(false);
                                      }}
                                      className="rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 font-bold text-rose-700 transition-colors hover:bg-rose-100"
                                    >
                                      {t("onboarding.step5.disconnect")}
                                    </button>
                                  </div>
                                </div>
                              )}

                              {!item.connected && (
                                <div className="mt-2.5 flex justify-end">
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      item.setter(true);
                                    }}
                                    className="rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-800 transition-colors hover:bg-amber-100"
                                  >
                                    {t("onboarding.step5.connect")}
                                  </button>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>

                      </div>

                      <div className="md:col-span-4 flex flex-col items-center justify-center relative pt-2">
                        <div className="bg-gradient-to-br from-[#07111d] to-[#10233f] text-white text-xs p-3.5 rounded-2xl shadow-xl border border-amber-400/30 relative mb-3 max-w-[210px] text-center animate-bounce-slow">
                          <p className="font-semibold leading-snug">
                            "Linking social channels lets me auto-post products & auto-reply to comments 24/7! 🚀"
                          </p>
                          <div className="w-3 h-3 bg-[#10233f] rotate-45 absolute -bottom-1.5 left-1/2 -translate-x-1/2 border-r border-b border-amber-400/30" />
                        </div>

                        <div className="w-36 h-36">
                          <InteractiveRobot
                            isEmailFocused={false}
                            isPasswordFocused={false}
                            isPasswordVisible={false}
                            compact
                            orbitRadiusX={115}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={() => setOnboardingStep((s) => Math.max(1, s - 1))}
                        className="flex-1 py-3.5 px-4 rounded-xl bg-white border border-slate-200 text-slate-700 font-bold text-sm hover:shadow-md transition-all"
                      >
                        {t("common.back")}
                      </button>
                      <button
                        onClick={() => {
                          if (!isAnySocialConnected) {
                            showToast("⚠️ Please connect at least one social account!", "error");
                            return;
                          }
                          setOnboardingStep(5);
                        }}
                        className="flex-1 py-4 px-6 rounded-xl bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 text-[#06111b] font-extrabold text-sm hover:shadow-xl hover:shadow-amber-500/25 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2.5 cursor-pointer"
                      >
                        <span>{t("onboarding.step5.nextBtn")}</span>
                        <ArrowRight className="w-4 h-4"/>
                      </button>
                    </div>
                  </div>
                )}

                {/* STEP 6: All Connected Launchpad */}
                {onboardingStep === 5 && (
                  <div className="animate-fade-in space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-3 bg-gradient-to-r from-[#07111d] via-[#10233f] to-[#193a5d] border border-amber-400/30 p-3.5 rounded-2xl shadow-lg shadow-amber-500/10 text-white">
                      <div className="flex items-center gap-2">
                        <span className="relative flex h-3 w-3">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-300 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-200"></span>
                        </span>
                        <span className="text-xs font-extrabold text-white">System Readiness: 100%</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
                      <div className="md:col-span-8 space-y-4">
                        <div>
                          <h3 className="text-2xl font-black text-slate-900 tracking-tight">
                            {t("onboarding.step6.title")}
                          </h3>
                          <p className="text-xs sm:text-sm text-slate-600 mt-1">
                            {t("onboarding.step6.socialConnected")}
                          </p>
                        </div>

                        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3 shadow-sm">
                          <p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">{t("onboarding.step6.readyForLaunch")}</p>
                          <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-slate-50 rounded-xl border border-slate-100">
                            <div className="flex items-center gap-2.5">
                              <img 
                                src={`https://www.google.com/s2/favicons?domain=${getDomainFromUrl(websiteUrl)}&sz=64`} 
                                alt="Favicon" 
                                className="w-5 h-5 rounded border bg-white p-0.5"
                              />
                              <div className="flex flex-col">
                                <span className="text-xs font-bold text-slate-800">{getSiteNameFromUrl(websiteUrl)}</span>
                                <span className="text-[10px] text-slate-400">{getDomainFromUrl(websiteUrl)}</span>
                              </div>
                            </div>
                            <span className="text-[10px] font-bold text-amber-900 bg-amber-200/90 px-2.5 py-0.5 rounded-full">{t("onboarding.step3.active")}</span>
                          </div>

                          <div className="flex flex-wrap gap-2 pt-1">
                            {instagramConnected && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-200 bg-pink-50 px-2.5 py-1 text-xs font-bold text-pink-700 shadow-sm"><Instagram className="h-3.5 w-3.5"/> Instagram</span>}
                            {facebookConnected && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-200 bg-pink-50 px-2.5 py-1 text-xs font-bold text-pink-700 shadow-sm"><Facebook className="h-3.5 w-3.5"/> Facebook</span>}
                            {tiktokConnected && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-200 bg-pink-50 px-2.5 py-1 text-xs font-bold text-pink-700 shadow-sm"><Music className="h-3.5 w-3.5"/> TikTok</span>}
                            {youtubeConnected && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-200 bg-pink-50 px-2.5 py-1 text-xs font-bold text-pink-700 shadow-sm"><Youtube className="h-3.5 w-3.5"/> YouTube</span>}
                            {twitterConnected && <span className="inline-flex items-center gap-1 rounded-lg border border-pink-200 bg-pink-50 px-2.5 py-1 text-xs font-bold text-pink-700 shadow-sm"><Twitter className="h-3.5 w-3.5"/> Twitter</span>}
                          </div>
                        </div>

                        <div className="bg-gradient-to-r from-[#07111d] to-[#10233f] rounded-2xl p-4 text-white space-y-2.5 shadow-md border border-amber-400/20">
                          <p className="text-[10px] font-extrabold uppercase tracking-wider text-amber-300">{t("onboarding.step6.launchingTitle")}</p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                            <div className="flex items-center gap-2 bg-white/10 p-2 rounded-xl border border-white/10">
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0"/>
                              <span className="font-medium">Live Catalog & Stock Sync</span>
                            </div>
                            <div className="flex items-center gap-2 bg-white/10 p-2 rounded-xl border border-white/10">
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0"/>
                              <span className="font-medium">AI Post & Content Generator</span>
                            </div>
                            <div className="flex items-center gap-2 bg-white/10 p-2 rounded-xl border border-white/10">
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0"/>
                              <span className="font-medium">24/7 Smart Comment Reply</span>
                            </div>
                            <div className="flex items-center gap-2 bg-white/10 p-2 rounded-xl border border-white/10">
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0"/>
                              <span className="font-medium">Revenue & Order Analytics</span>
                            </div>
                          </div>
                        </div>

                      </div>

                      <div className="md:col-span-4 flex flex-col items-center justify-center relative pt-2">
                        <div className="bg-gradient-to-br from-[#07111d] to-[#10233f] text-white text-xs p-3.5 rounded-2xl shadow-xl border border-amber-400/30 relative mb-3 max-w-[210px] text-center animate-bounce-slow">
                          <p className="font-semibold leading-snug">
                            {t("onboarding.step6.robotMsg")}
                          </p>
                          <div className="w-3 h-3 bg-[#10233f] rotate-45 absolute -bottom-1.5 left-1/2 -translate-x-1/2 border-r border-b border-amber-400/30" />
                        </div>

                        <div className="w-36 h-36">
                          <InteractiveRobot
                            isEmailFocused={false}
                            isPasswordFocused={false}
                            isPasswordVisible={false}
                            compact
                            orbitRadiusX={82}
                            orbitItemScale={0.82}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={() => setOnboardingStep((s) => Math.max(2, s - 1))}
                        className="flex-1 py-3.5 px-4 rounded-xl bg-white border border-slate-200 text-slate-700 font-bold text-sm hover:shadow-md transition-all"
                      >
                        {t("common.back")}
                      </button>
                      <button
                        onClick={() => {
                          setIsReady(true);
                          setOnboardingStep(6);
                          setShowActivationScreen(true);
                          showToast("🎉 Initializing Digital FTE Agent...", "info");
                        }}
                        className="flex-1 py-4 px-6 rounded-xl bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 text-[#06111b] font-extrabold text-sm hover:shadow-xl hover:shadow-amber-500/25 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2.5 cursor-pointer"
                      >
                        <span>{t("onboarding.step6.launchBtn")}</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* ========== STEP 7: Activation Sequence ========== */}
                {onboardingStep === 6 && !showDashboard && (
                  <div className="animate-fade-in">
                    {showActivationScreen ? (
                      <LaunchActivationScreen
                        onComplete={() => {
                          setFlowMode("dashboard");
                          setShowDashboard(true);
                          showToast("🚀 Your Digital FTE is now live!", "success");
                        }}
                      />
                    ) : (
                      <div className="text-center py-12">
                        <div className="flex items-start gap-6">
                          <div className="flex-1">
                            <div className="w-28 h-28 rounded-full bg-gradient-to-br from-amber-500 to-yellow-400 flex items-center justify-center mx-auto shadow-2xl shadow-amber-500/30">
                              <Loader2 className="w-14 h-14 text-[#06111b] animate-spin" />
                            </div>
                            <h2 className="text-3xl font-extrabold text-slate-900 mt-6">{t("onboarding.step7.title")}</h2>
                            <p className="text-sm text-slate-500 mt-2">{t("onboarding.step7.desc")}</p>
                            <div className="mt-6 max-w-sm mx-auto">
                              <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
                                <div className="bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-500 h-3 rounded-full transition-all duration-1000 w-[33%] animate-pulse" />
                              </div>
                              <div className="flex justify-between text-[8px] text-slate-400 mt-2">
                                <span className="animate-pulse">{t("onboarding.step7.launching")}</span>
                                <span className="animate-pulse delay-300">{t("dashboard.aiHub")}</span>
                                <span className="animate-pulse delay-700">{t("onboarding.step6.readyForLaunch")}</span>
                              </div>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-4 flex items-center justify-center gap-2">
                              <Loader2 className="w-3 h-3 animate-spin" />
                              Loading AI models...
                            </p>
                            <div className="mt-6 flex justify-center">
                              <button
                                onClick={() => setOnboardingStep(5)}
                                className="px-4 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 font-semibold hover:shadow-md"
                              >
                                {t("common.back")}
                              </button>
                            </div>
                          </div>
                          <div className="hidden md:block w-48 h-48">
                            <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} compact />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        ) : currentView === "landing" ? (
          // LANDING PAGE
          <div id="landing-view-root" className="w-full max-w-7xl mx-auto flex flex-col gap-20 py-4 animate-fade-in">
            <div id="hero" className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center py-4">
              <div className="lg:col-span-7 flex flex-col items-start text-left">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 text-amber-300 text-xs font-bold mb-6 tracking-wide uppercase shadow-sm hover:shadow-md hover:bg-amber-500/15 transition-all animate-pulse">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                  <span>{t("hero.badge")}</span>
                </div>
                <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-[1.1] mb-6 animate-fade-in">
                  {t("hero.headline1")} <br />
                  <span className="bg-gradient-to-r from-amber-400 via-orange-400 to-yellow-400 bg-clip-text text-transparent animate-pulse">{t("hero.headline2")} {t("hero.headline3")}</span>
                </h1>
                <p className="text-base sm:text-lg text-slate-300 max-w-xl leading-relaxed mb-8 animate-fade-in-delay">
                  {t("hero.subheadline")}
                </p>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 mb-8 w-full sm:w-auto animate-fade-in-delay">
                  <button
                    onClick={() => {
                      setAuthMode("signup");
                      setCurrentView("auth");
                      showToast("Let's configure your autonomous container!", "success");
                    }}
                    className="px-8 py-4 text-sm font-bold text-center rounded-xl bg-gradient-to-r from-amber-500 to-yellow-400 hover:shadow-xl text-[#06111b] shadow-lg shadow-amber-500/20 transform hover:scale-105 active:scale-[0.98] transition-all cursor-pointer flex items-center justify-center gap-2 duration-300"
                  >
                    <span>{t("hero.ctaPrimary")}</span>
                    <ArrowRight className="w-4 h-4 animate-bounce-right" />
                  </button>
                  <a
                    href="#live-playground"
                    className="px-8 py-4 text-sm font-bold text-center rounded-xl bg-[#07111d] border border-amber-400/20 text-amber-200 hover:bg-[#0c2034] hover:shadow-md hover:scale-105 transition-all cursor-pointer flex items-center justify-center gap-2 duration-300"
                  >
                    <div className="w-5 h-5 rounded-full bg-amber-500/15 flex items-center justify-center text-amber-300">
                      <Play className="w-2.5 h-2.5 fill-current" />
                    </div>
                    <span>{t("hero.demoLabel") || "Live Simulation"}</span>
                  </a>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-xl w-full">
                  <div className="rounded-2xl border border-white/10 bg-[#071121] p-4 text-sm text-slate-200 shadow-lg shadow-black/10">
                    <p className="font-bold text-white">{t("hero.benefitFast")}</p>
                    <p className="mt-2 text-slate-400">{t("hero.benefitFastDesc")}</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-[#071121] p-4 text-sm text-slate-200 shadow-lg shadow-black/10">
                    <p className="font-bold text-white">{t("hero.benefitNoCard")}</p>
                    <p className="mt-2 text-slate-400">{t("hero.benefitNoCardDesc")}</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-[#071121] p-4 text-sm text-slate-200 shadow-lg shadow-black/10">
                    <p className="font-bold text-white">{t("hero.benefitCancel")}</p>
                    <p className="mt-2 text-slate-400">{t("hero.benefitCancelDesc")}</p>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-5 relative w-full max-w-lg mx-auto flex items-center justify-center min-h-[460px]">
                <div className="absolute w-[280px] h-[240px] sm:w-[340px] sm:h-[300px] rounded-full bg-[radial-gradient(ellipse,rgba(245,158,11,0.2),transparent_68%)] blur-[50px] opacity-80" />
                <div
                  className="relative flex h-[340px] w-[340px] items-center justify-center p-6 sm:h-[400px] sm:w-[400px] sm:-translate-y-8 -translate-y-6"
                  onClick={() => setRobotMotionPaused((paused) => !paused)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setRobotMotionPaused((paused) => !paused);
                    }
                  }}
                  aria-label={robotMotionPaused ? "Resume robot motion" : "Pause robot motion"}
                >
                  <div className="absolute -inset-1.5 rounded-full animate-spin-slow" style={{ animationPlayState: robotMotionPaused ? "paused" : "running" }} />
                  <div className="absolute -inset-8 rounded-full animate-pulse" style={{ animationPlayState: robotMotionPaused ? "paused" : "running" }} />
                  <div className="relative z-10 h-[300px] w-[300px] robot-emitter transition-transform duration-500 hover:scale-105 sm:h-[360px] sm:w-[360px]">
                    <InteractiveRobot
                      isEmailFocused={false}
                      isPasswordFocused={false}
                      isPasswordVisible={false}
                      isWaving
                      showWelcome
                      motionPaused={false}
                      orbitRadiusX={190}
                    />
                  </div>
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[220px] sm:w-[250px] h-[20px] bg-gradient-to-r from-slate-900 to-slate-800 border-t border-slate-700/50 rounded-b-lg shadow-xl flex items-center justify-center px-10">
                    <div className="w-12 h-1 bg-slate-700 rounded-full" />
                  </div>
                </div>
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[200px] h-3 bg-amber-500/10 rounded-full blur-sm animate-pulse-shadow" />
              </div>
            </div>

            {/* 1. PLATFORM & ECOSYSTEM INTEGRATIONS */}
            <div id="integrations" className="pt-8 pb-4 border-y border-white/5">
              <p className="text-center text-xs font-bold uppercase tracking-widest text-slate-400 mb-6">
                Connected Native Integrations & Infrastructure
              </p>
              <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-6 text-slate-300">
                {[
                  { name: "Shopify", badge: "Direct Webhooks", color: "from-emerald-500/20 to-green-500/10 border-emerald-500/30 text-emerald-300" },
                  { name: "WooCommerce", badge: "REST Sync", color: "from-purple-500/20 to-violet-500/10 border-purple-500/30 text-purple-300" },
                  { name: "Instagram", badge: "Meta Graph API", color: "from-pink-500/20 to-rose-500/10 border-pink-500/30 text-pink-300" },
                  { name: "Facebook", badge: "Catalog & Comments", color: "from-blue-500/20 to-cyan-500/10 border-blue-500/30 text-blue-300" },
                  { name: "TikTok Shop", badge: "Viral Queue", color: "from-slate-700/40 to-slate-800/20 border-slate-600/40 text-slate-200" },
                  { name: "YouTube", badge: "Community Posts", color: "from-red-500/20 to-rose-500/10 border-red-500/30 text-red-300" },
                  { name: "Google Gemini 2.5", badge: "Multimodal AI", color: "from-amber-500/20 to-yellow-500/10 border-amber-500/30 text-amber-300" },
                  { name: "Redis & Postgres", badge: "Sub-Second Bus", color: "from-orange-500/20 to-amber-500/10 border-orange-500/30 text-orange-300" },
                ].map((item, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-gradient-to-br ${item.color} border backdrop-blur-md shadow-sm hover:scale-105 transition-all duration-200`}
                  >
                    <span className="text-sm font-bold text-white">{item.name}</span>
                    <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-black/40 text-white/80">
                      {item.badge}
                    </span>
                    
                  </div>
                ))}
              </div>
            </div>

            {/* 2. THE 7 AUTONOMOUS AI AGENTS */}
            <div id="ai-workforce" className="py-8 space-y-12">
              <div className="text-center max-w-3xl mx-auto space-y-4">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-bold uppercase tracking-wider">
                  <Bot className="w-3.5 h-3.5" />
                  Your 24/7 Digital Workforce
                </div>
                <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight">
                  Seven Specialized AI Agents. <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-orange-400 to-yellow-300">
                    Zero Human Churn.
                  </span>
                </h2>
                <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
                  Unlike single-purpose bots, Digital FTE coordinates 7 specialized agents operating in an event-driven loop. Each agent owns a critical pillar of your e-commerce operations.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  {
                    num: "01",
                    role: "Inventory & Stock Sync",
                    desc: "Listens to live Shopify webhooks, prevents overselling, detects low stock, and automatically prepares supplier replenishment orders.",
                    icon: Package,
                    badge: "Real-Time Sync",
                    metrics: "Sub-Second SKU Updates",
                    accent: "border-amber-500/30 group-hover:border-amber-400/60"
                  },
                  {
                    num: "02",
                    role: "AI Creative Studio",
                    desc: "Gemini-powered copywriter crafts conversion-focused captions, hashtags, and product lifestyle renders aligned with your brand guidelines.",
                    icon: Sparkles,
                    badge: "Gemini 2.5 Flash",
                    metrics: "10x Faster Post Creation",
                    accent: "border-purple-500/30 group-hover:border-purple-400/60"
                  },
                  {
                    num: "03",
                    role: "Omnichannel Scheduler",
                    desc: "Automatically schedules and publishes content to Instagram, Facebook, TikTok, YouTube, and LinkedIn at peak audience engagement windows.",
                    icon: Calendar,
                    badge: "5 Platforms",
                    metrics: "100% Autonomous Queue",
                    accent: "border-blue-500/30 group-hover:border-blue-400/60"
                  },
                  {
                    num: "04",
                    role: "Comment & Engagement Agent",
                    desc: "Monitors post comments 24/7. Auto-replies to price and sizing questions, hides spam/toxic comments, and boosts algorithmic organic reach.",
                    icon: MessageCircle,
                    badge: "Sentiment Filter",
                    metrics: "< 3s Response Time",
                    accent: "border-emerald-500/30 group-hover:border-emerald-400/60"
                  },
                  {
                    num: "05",
                    role: "Bilingual Customer Support",
                    desc: "Handles live storefront chat inquiries in native English and Urdu (اردو). Performs instant order tracking, cart assists, and returns lookups.",
                    icon: Bot,
                    badge: "EN & اردو Native",
                    metrics: "99.4% First-Contact Resolution",
                    accent: "border-rose-500/30 group-hover:border-rose-400/60"
                  },
                  {
                    num: "06",
                    role: "Revenue & Analytics Agent",
                    desc: "Performs hourly order rollups, daily P&L digests, and anomaly detection so you always know your profit margins without opening spreadsheets.",
                    icon: BarChart3,
                    badge: "Hourly Rollup",
                    metrics: "Automated Daily P&L",
                    accent: "border-cyan-500/30 group-hover:border-cyan-400/60"
                  },
                  {
                    num: "07",
                    role: "Master Orchestrator",
                    desc: "The brain behind the system: manages agent heartbeats, multi-step workflows, task queues in Redis, and human-in-the-loop escalations.",
                    icon: Cpu,
                    badge: "Core Controller",
                    metrics: "Fault-Tolerant Heartbeat",
                    accent: "border-yellow-500/30 group-hover:border-yellow-400/60",
                    spanFull: true
                  },
                ].map((agent, i) => (
                  <div
                    key={i}
                    className={`p-6 sm:p-8 rounded-3xl bg-[#07111d]/90 border ${agent.accent} backdrop-blur-xl relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between ${agent.spanFull ? "lg:col-span-3 bg-gradient-to-r from-[#07111d] via-[#0d1c2d] to-[#07111d]" : ""}`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-xs font-mono font-bold text-amber-400/80 px-2 py-1 rounded-md bg-amber-400/10">
                          Agent #{agent.num}
                        </span>
                        <span className="text-[10px] font-semibold text-slate-400 px-2.5 py-1 rounded-full bg-white/5 border border-white/10">
                          {agent.badge}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0">
                          <agent.icon className="w-5 h-5" />
                        </div>
                        <h3 className="text-lg font-bold text-white group-hover:text-amber-300 transition-colors">
                          {agent.role}
                        </h3>
                      </div>
                      <p className="text-xs sm:text-sm text-slate-400 leading-relaxed mb-4">
                        {agent.desc}
                      </p>
                    </div>
                    <div className="pt-4 border-t border-white/5 flex items-center justify-between text-xs text-slate-300">
                      <span className="text-emerald-400 font-medium flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                        {agent.metrics}
                      </span>
                      <span className="text-slate-500 group-hover:text-amber-400 transition-colors">24/7 Autopilot →</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 3. INTERACTIVE SIMULATION PLAYGROUND */}
            <div id="live-playground" className="py-8 space-y-8">
              <div className="text-center max-w-2xl mx-auto space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs font-bold uppercase tracking-wider">
                  <Play className="w-3.5 h-3.5" />
                  Interactive Demo
                </div>
                <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                  Experience Your AI FTE Live
                </h2>
                <p className="text-slate-400 text-sm sm:text-base">
                  Test how the autonomous agents react to real e-commerce store events right in your browser.
                </p>
              </div>

              {/* Playground Container */}
              <div className="p-6 sm:p-10 rounded-3xl bg-[#07111d]/95 border border-white/10 shadow-2xl backdrop-blur-xl max-w-4xl mx-auto">
                
                {/* Tabs */}
                <div className="flex flex-wrap items-center justify-center gap-2 mb-8 border-b border-white/10 pb-4">
                  {[
                    { id: "inventory", label: "📦 Inventory Auto-Alert" },
                    { id: "content", label: "✨ AI Caption Studio" },
                    { id: "support", label: "🤖 24/7 Bilingual Chat" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setSimActiveTab(tab.id as any)}
                      className={`px-5 py-3 rounded-2xl text-xs sm:text-sm font-bold transition-all cursor-pointer ${
                        simActiveTab === tab.id
                          ? "bg-amber-400 text-[#06111b] shadow-lg shadow-amber-400/20 scale-105"
                          : "bg-white/5 text-slate-300 hover:bg-white/10"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Tab 1: Inventory Alert Simulation */}
                {simActiveTab === "inventory" && (
                  <div className="space-y-6">
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-2xl bg-white/5 border border-white/10">
                      <div>
                        <h4 className="text-sm font-bold text-white">Scenario: Product Stock Drops to 2 Units</h4>
                        <p className="text-xs text-slate-400 mt-0.5">Item: Classic Leather Jacket (SKU: LJ-BLK-04)</p>
                      </div>
                      <button
                        onClick={() => {
                          setSimStockTriggered(true);
                          showToast("⚡ Stock event triggered: Agent 1 activated!", "info");
                        }}
                        className="px-4 py-2 text-xs font-bold rounded-xl bg-amber-400/20 text-amber-300 border border-amber-400/40 hover:bg-amber-400/30 transition-all cursor-pointer flex items-center gap-2"
                      >
                        <Zap className="w-3.5 h-3.5" />
                        Trigger Low-Stock Event
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="p-5 rounded-2xl bg-black/40 border border-white/10 space-y-3">
                        <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Shopify Webhook Input</span>
                        <pre className="text-xs font-mono text-amber-300/90 overflow-x-auto bg-black/60 p-3 rounded-xl">
{`{
  "event": "orders/create",
  "sku": "LJ-BLK-04",
  "remaining_stock": ${simStockTriggered ? "2" : "14"},
  "status": "${simStockTriggered ? "LOW_STOCK_ALERT" : "HEALTHY"}"
}`}
                        </pre>
                      </div>

                      <div className="p-5 rounded-2xl bg-gradient-to-br from-amber-500/10 to-emerald-500/10 border border-amber-500/30 space-y-3">
                        <span className="text-[10px] uppercase tracking-wider font-bold text-emerald-400 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Autonomous Agent Actions
                        </span>
                        {simStockTriggered ? (
                          <div className="space-y-2 text-xs text-slate-200">
                            <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2">
                              <Check className="w-4 h-4 text-emerald-400 shrink-0" />
                              <span>Synced inventory count across Shopify & TikTok</span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center gap-2">
                              <Bell className="w-4 h-4 text-amber-400 shrink-0" />
                              <span>Pushed supplier replenishment draft to dashboard</span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center gap-2">
                              <Share2 className="w-4 h-4 text-blue-400 shrink-0" />
                              <span>Flagged "Hurry, only 2 left!" on live product page</span>
                            </div>
                          </div>
                        ) : (
                          <div className="h-28 flex items-center justify-center text-xs text-slate-400 italic text-center">
                            Click "Trigger Low-Stock Event" above to see real-time agent workflow
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab 2: AI Caption Studio Simulation */}
                {simActiveTab === "content" && (
                  <div className="space-y-6">
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-2xl bg-white/5 border border-white/10">
                      <div>
                        <h4 className="text-sm font-bold text-white">Target Product: Minimalist Chronograph Watch</h4>
                        <p className="text-xs text-slate-400 mt-0.5">Tone: Luxury & Aesthetic • Channel: Instagram & TikTok</p>
                      </div>
                      <button
                        onClick={() => {
                          setSimContentGenerating(true);
                          setTimeout(() => {
                            setSimContentGenerating(false);
                            setSimGeneratedPost(true);
                            showToast("✨ Post crafted by Google Gemini 2.5!", "success");
                          }, 800);
                        }}
                        disabled={simContentGenerating}
                        className="px-4 py-2 text-xs font-bold rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/40 hover:bg-purple-500/30 transition-all cursor-pointer flex items-center gap-2"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        {simContentGenerating ? "Crafting Copy..." : "Generate Social Post"}
                      </button>
                    </div>

                    <div className="p-5 rounded-2xl bg-black/40 border border-white/10">
                      {simGeneratedPost ? (
                        <div className="space-y-4">
                          <div className="flex items-center gap-3 border-b border-white/10 pb-3">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-yellow-500 via-rose-500 to-purple-500 flex items-center justify-center text-white text-xs font-bold">
                              IG
                            </div>
                            <div>
                              <p className="text-xs font-bold text-white">yourstore_official • <span className="text-amber-400 font-normal">Auto-Scheduled</span></p>
                              <p className="text-[10px] text-slate-400">Optimal engagement window: Today at 6:45 PM</p>
                            </div>
                          </div>
                          <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-sans">
                            Precision meets timeless elegance. ⏳ Crafted for those who value every second, our Minimalist Chronograph is engineered with sapphire crystal glass and genuine Italian leather.
                            <br /><br />
                            ⚡ Limited production batch now live on store. Tap the link in bio to claim yours with complimentary worldwide shipping.
                            <br /><br />
                            <span className="text-amber-400">#LuxuryTimepiece #MinimalistDesign #ModernElegance #WatchCollector #ECommerceStyle</span>
                          </p>
                        </div>
                      ) : (
                        <div className="h-28 flex items-center justify-center text-xs text-slate-400 italic text-center">
                          Click "Generate Social Post" above to simulate Google Gemini copywriter
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Tab 3: Bilingual Support Simulation */}
                {simActiveTab === "support" && (
                  <div className="space-y-6">
                    <div className="flex items-center justify-between p-4 rounded-2xl bg-white/5 border border-white/10">
                      <div>
                        <h4 className="text-sm font-bold text-white">24/7 Storefront Live Chatbot</h4>
                        <p className="text-xs text-slate-400 mt-0.5">Supports both English and Urdu (اردو) automatically</p>
                      </div>
                      <div className="flex items-center gap-1.5 p-1 rounded-xl bg-black/40 border border-white/10">
                        <button
                          onClick={() => setSimChatLanguage("en")}
                          className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                            simChatLanguage === "en" ? "bg-amber-400 text-black" : "text-slate-400"
                          }`}
                        >
                          English
                        </button>
                        <button
                          onClick={() => setSimChatLanguage("ur")}
                          className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                            simChatLanguage === "ur" ? "bg-amber-400 text-black" : "text-slate-400"
                          }`}
                        >
                          اردو
                        </button>
                      </div>
                    </div>

                    <div className="p-5 rounded-2xl bg-black/40 border border-white/10 space-y-3">
                      {simChatLanguage === "en" ? (
                        <>
                          <div className="flex justify-end">
                            <div className="max-w-xs px-4 py-2.5 rounded-2xl bg-amber-500/20 border border-amber-400/30 text-amber-200 text-xs">
                              Hi! Where is my order #DFTE-8921?
                            </div>
                          </div>
                          <div className="flex justify-start">
                            <div className="max-w-xs px-4 py-2.5 rounded-2xl bg-white/10 border border-white/10 text-slate-200 text-xs space-y-1">
                              <p className="font-semibold text-emerald-400 flex items-center gap-1.5">
                                <Bot className="w-3.5 h-3.5" />
                                Digital FTE Support Agent
                              </p>
                              <p>Hello! Order #DFTE-8921 was fulfilled 3 hours ago via Express Logistics. Tracking: <span className="text-amber-300 font-mono">TRK-98124</span>. Expected arrival: Tomorrow by 2 PM!</p>
                            </div>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="flex justify-start" dir="rtl">
                            <div className="max-w-xs px-4 py-2.5 rounded-2xl bg-amber-500/20 border border-amber-400/30 text-amber-200 text-xs font-sans">
                              السلام علیکم! میرا آرڈر #DFTE-8921 کب تک پہنچے گا؟
                            </div>
                          </div>
                          <div className="flex justify-end" dir="rtl">
                            <div className="max-w-xs px-4 py-2.5 rounded-2xl bg-white/10 border border-white/10 text-slate-200 text-xs space-y-1 font-sans">
                              <p className="font-semibold text-emerald-400 flex items-center gap-1.5">
                                <Bot className="w-3.5 h-3.5" />
                                ڈیجیٹل FTE سپورٹ ایجنٹ
                              </p>
                              <p>وعلیکم السلام! آپ کا آرڈر #DFTE-8921 کوریئر کو روانہ کر دیا گیا ہے۔ ٹریکنگ نمبر: <span className="text-amber-300 font-mono">TRK-98124</span> ہے۔ کل دوپہر 2 بجے تک موصول ہو جائے گا!</p>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}

              </div>
            </div>

            {/* 4. QUANTIFIABLE IMPACT & METRICS */}
            <div className="py-8 grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6">
              {[
                { val: "< 1.2s", label: "Chatbot Response Time", sub: "Fastest in e-commerce" },
                { val: "10x", label: "Content Creation Speed", sub: "Gemini 2.5 studio" },
                { val: "15+ Hrs", label: "Saved Weekly / Store", sub: "Zero manual admin" },
                { val: "99.9%", label: "Real-Time Sync Uptime", sub: "Redis event streams" },
              ].map((stat, i) => (
                <div
                  key={i}
                  className="p-6 rounded-3xl bg-[#07111d]/90 border border-white/10 text-center space-y-2 hover:border-amber-400/40 transition-all"
                >
                  <p className="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-yellow-300 font-mono">
                    {stat.val}
                  </p>
                  <p className="text-xs sm:text-sm font-bold text-white">{stat.label}</p>
                  <p className="text-[10px] text-slate-400">{stat.sub}</p>
                </div>
              ))}
            </div>



            {/* 6. FREQUENTLY ASKED QUESTIONS */}
            <div id="faq" className="py-8 space-y-8 max-w-3xl mx-auto w-full">
              <div className="text-center space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-bold uppercase tracking-wider">
                  <HelpCircle className="w-3.5 h-3.5" />
                  Common Questions
                </div>
                <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                  Frequently Asked Questions
                </h2>
                <p className="text-slate-400 text-sm">
                  Everything you need to know about setting up your autonomous AI employee.
                </p>
              </div>

              <div className="space-y-3">
                {[
                  {
                    q: "Is it safe to connect my Shopify or WooCommerce store?",
                    a: "Yes, 100%. Digital FTE connects via official OAuth API keys with read-only scopes by default. All access tokens are encrypted with AES-256 / Fernet key derivation, and your data is never used to train public AI models."
                  },
                  {
                    q: "How does the bilingual support (English & Urdu) work?",
                    a: "Our customer support agent detects the language of incoming visitor messages automatically. Whether a customer types in formal English, Roman Urdu, or standard Urdu script, the AI resolves their order status and questions accurately in the same language."
                  },
                  {
                    q: "Can I review AI-generated posts and replies before they publish?",
                    a: "Absolutely. You have total control: you can keep any agent in 'Human-in-the-Loop' mode where drafts require one-click approval, or toggle into full autonomous autopilot once you trust the brand voice."
                  },
                  {
                    q: "Do I need a credit card to start the free trial?",
                    a: "No credit card is required. You get 14 days of full access to explore the dashboard, test the AI agents, and connect your store with zero financial obligation."
                  },
                  {
                    q: "Can I cancel or change my plan anytime?",
                    a: "Yes. There are no contracts or long-term lock-ins. You can upgrade, downgrade, or cancel your subscription with a single click from the Settings tab."
                  }
                ].map((faq, idx) => {
                  const isOpen = landingFaqOpen === idx;
                  return (
                    <div
                      key={idx}
                      className="rounded-2xl border border-white/10 bg-[#07111d]/90 p-5 cursor-pointer transition-all hover:border-amber-400/30"
                      onClick={() => setLandingFaqOpen(isOpen ? null : idx)}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <h4 className="text-sm sm:text-base font-bold text-white">{faq.q}</h4>
                        <ChevronDown
                          className={`w-4 h-4 text-amber-400 shrink-0 transition-transform duration-200 ${
                            isOpen ? "rotate-180" : ""
                          }`}
                        />
                      </div>
                      {isOpen && (
                        <p className="mt-3 text-xs sm:text-sm text-slate-300 leading-relaxed pt-3 border-t border-white/5 animate-fade-in">
                          {faq.a}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>



          </div>
        ) : (
          // AUTH PAGE
          <div id="unified-split-container" className="max-w-6xl w-full mx-auto bg-[#02040d]/95 border border-white/10 shadow-[0_40px_80px_rgba(0,0,0,0.45)] rounded-[32px] overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-[620px]">
            <div id="auth-left-panel" className="lg:col-span-6 p-6 sm:p-10 md:p-12 flex flex-col justify-between bg-[#07111d]/95 border-r border-white/10">
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2 lg:hidden">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-yellow-400 flex items-center justify-center text-[#06111b] font-bold">
                    <TrendingUp className="w-4 h-4" />
                  </div>
                  <span className="font-bold text-lg text-white">Digital FTE</span>
                </div>
                <h2 className="text-3xl font-extrabold text-violet-950 tracking-tight">
                  {authMode === "signin" ? t("auth.signIn") : t("auth.getStarted")}
                </h2>
                <p className="text-sm text-slate-500 mt-1.5">
                  {authMode === "signin" 
                    ? t("auth.loginDesc")
                    : t("auth.signupDesc")}
                </p>
              </div>

              <div className="flex-1 flex flex-col justify-center">
                <div className="relative flex p-1 bg-white/5 rounded-xl mb-6 border border-white/10">
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("signin");
                      showToast("Switched to Sign In mode.", "info");
                    }}
                    className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                      authMode === "signin" ? "bg-[#0d172f] text-amber-300 shadow-sm border border-amber-500/20" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {t("auth.signIn")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("signup");
                      showToast("Switched to Create Account mode.", "info");
                    }}
                    className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                      authMode === "signup" ? "bg-[#0d172f] text-amber-300 shadow-sm border border-amber-500/20" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {t("auth.signUp")}
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 mb-6">
                  <div className={`flex justify-center ${loading ? "opacity-50 pointer-events-none" : ""}`}>
                    <GoogleLogin
                      onSuccess={(res) => handleGoogleCredential(res.credential)}
                      onError={() => showToast("Google login failed. Please try again.", "error")}
                      theme="filled_black"
                      shape="pill"
                      size="large"
                      width="320"
                      text={authMode === "signin" ? "signin_with" : "signup_with"}
                    />
                  </div>
                </div>

                <div className="relative flex py-2 items-center mb-6">
                  <div className="flex-grow border-t border-slate-100"></div>
                  <span className="flex-shrink mx-4 text-[10px] text-slate-400 font-bold uppercase tracking-wider">{t("auth.orContinueWith")}</span>
                  <div className="flex-grow border-t border-slate-100"></div>
                </div>

                <form onSubmit={handleAuthSubmit} className="space-y-4">
                  <div className={`transition-all duration-300 overflow-hidden ${authMode === "signup" ? "max-h-[85px] opacity-100 mb-4" : "max-h-0 opacity-0 pointer-events-none"}`}>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">{t("auth.fullNameLabel")}</label>
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
                        className="block w-full pl-10 pr-3.5 py-3 bg-white/5 border border-white/10 focus:border-amber-400 focus:bg-white/10 focus:ring-amber-400/20 outline-none rounded-xl text-white placeholder-slate-500 text-sm transition-all duration-300"
                        placeholder={t("auth.fullNamePlaceholder")}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">{t("auth.emailLabel")}</label>
                    <div className="relative rounded-xl shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                        <Mail className={`w-4 h-4 transition-colors ${isEmailFocused ? "text-violet-600" : "text-slate-400"}`} />
                      </div>
                      <input
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        onFocus={() => setIsEmailFocused(true)}
                        onBlur={() => setIsEmailFocused(false)}
                        className="block w-full pl-10 pr-3.5 py-3 bg-white/5 border border-white/10 focus:border-amber-400 focus:bg-white/10 focus:ring-amber-400/20 outline-none rounded-xl text-white placeholder-slate-500 text-sm transition-all duration-300"
                        placeholder={t("auth.emailPlaceholder")}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide">{t("auth.passwordLabel")}</label>
                      {authMode === "signin" && (
                        <button
                          type="button"
                          onClick={() => {
                            setShowForgotPassword(true);
                            showToast("Please input reset target.", "info");
                          }}
                          className="text-xs font-bold text-violet-600 hover:text-violet-800 transition-colors cursor-pointer"
                        >
                          {t("auth.forgotPassword")}
                        </button>
                      )}
                    </div>
                    <div className="relative rounded-xl shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                        <Lock className={`w-4 h-4 transition-colors ${isPasswordFocused ? "text-violet-600" : "text-slate-400"}`} />
                      </div>
                      <input
                        type={isPasswordVisible ? "text" : "password"}
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onFocus={() => setIsPasswordFocused(true)}
                        onBlur={() => setIsPasswordFocused(false)}
                        className="block w-full pl-10 pr-12 py-3 bg-white/5 border border-white/10 focus:border-amber-400 focus:bg-white/10 focus:ring-amber-400/20 outline-none rounded-xl text-white placeholder-slate-500 text-sm transition-all duration-300"
                        placeholder="••••••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setIsPasswordVisible(!isPasswordVisible);
                          showToast(
                            isPasswordVisible ? "Privacy mode enabled. Robot is closing eyes." : "Peeking mode enabled! Robot is watching.", 
                            "info"
                          );
                        }}
                        className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-violet-600 transition-colors cursor-pointer"
                        title={isPasswordVisible ? "Hide password" : "Show password"}
                      >
                        {isPasswordVisible ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full mt-2 py-3.5 px-4 bg-gradient-to-r from-amber-500 via-yellow-400 to-orange-400 text-[#06111b] font-bold text-sm tracking-wide shadow-lg shadow-amber-300/30 hover:shadow-amber-400 transform active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {loading ? (
                      <div className="w-5 h-5 rounded-full border-2 border-[#06111b] border-t-transparent animate-spin" />
                    ) : (
                      <>
                        <span>{authMode === "signin" ? t("auth.signIn") : t("pricing.trialBtn")}</span>
                        <ArrowRight className="w-4 h-4 text-[#06111b]" />
                      </>
                    )}
                  </button>
                </form>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
                {authMode === "signin" ? (
                  <p>
                    {t("auth.noAccount")} {" "}
                    <button
                      onClick={() => setAuthMode("signup")}
                      className="text-amber-300 font-bold hover:underline cursor-pointer"
                    >
                      {t("auth.signUpLink")}
                    </button>
                  </p>
                ) : (
                  <p>
                    {t("auth.haveAccount")} {" "}
                    <button
                      onClick={() => setAuthMode("signin")}
                      className="text-amber-300 font-bold hover:underline cursor-pointer"
                    >
                      {t("auth.signInLink")}
                    </button>
                  </p>
                )}
              </div>
            </div>

            <div id="auth-right-panel" className="lg:col-span-6 bg-[#020918] p-8 sm:p-12 relative flex flex-col items-center justify-center overflow-visible border-t lg:border-t-0 lg:border-l border-white/10">
              <div className="absolute top-1/4 left-1/4 w-[350px] h-[350px] rounded-full bg-amber-500/10 blur-3xl animate-float" />
              <div className="absolute bottom-1/4 right-1/4 w-[250px] h-[250px] rounded-full bg-violet-500/10 blur-2xl animate-float-delayed" />
              <div className="absolute top-12 right-12 w-6 h-6 rounded-full bg-amber-300/30 blur-md animate-pulse" />
              <div className="absolute top-1/3 -right-32 w-[500px] h-[500px] rounded-full bg-violet-400/08 blur-3xl animate-pulse-slow" />

              <div className="relative w-full flex items-center justify-center my-6 z-30">
                <div className="absolute w-64 h-64 bg-gradient-to-r from-violet-400/20 to-indigo-400/20 rounded-full blur-2xl animate-pulse-slow" />
                <InteractiveRobot 
                  isEmailFocused={isEmailFocused} 
                  isPasswordFocused={isPasswordFocused} 
                  isPasswordVisible={isPasswordVisible} 
                  isFullNameFocused={isFullNameFocused}
                  orbitItemScale={1.25}
                  visualScale={0.82}
                />
              </div>
            </div>
          </div>
        )}
      </main>

      {/* MODALS */}
      {showForgotPassword && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white border border-violet-100 shadow-2xl rounded-2xl max-w-md w-full p-6 relative">
            <button onClick={() => setShowForgotPassword(false)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 font-bold">✕</button>
            <h3 className="text-lg font-bold text-violet-950 flex items-center gap-2"><Lock className="w-5 h-5 text-violet-600" /><span>Recover Account Access</span></h3>
            <p className="text-xs text-slate-500 mt-2">No stress. Provide your verified email and we'll dispatch a secure recovery vector.</p>
            <form onSubmit={handleForgotSubmit} className="mt-4 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-700 uppercase tracking-wider mb-1.5">Email Address</label>
                <div className="relative rounded-xl shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none"><Mail className="w-4 h-4 text-slate-400" /></div>
                  <input type="email" required value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} className="block w-full pl-10 pr-3.5 py-2.5 border border-slate-200 rounded-xl text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600 transition-all" placeholder="founder@mystore.com" />
                </div>
              </div>
              <button type="submit" disabled={forgotSubmitted} className="w-full py-2.5 px-4 rounded-xl bg-violet-700 text-white font-bold text-xs tracking-wider hover:bg-violet-800 transition-all flex items-center justify-center gap-2">
                {forgotSubmitted ? <><Check className="w-4 h-4" /><span>Payload Dispatched!</span></> : <><span>Dispatch Recovery Key</span><ArrowRight className="w-4 h-4" /></>}
              </button>
            </form>
          </div>
        </div>
      )}

      {showShopifyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#07111d]/95 border border-white/10 shadow-2xl rounded-2xl max-w-md w-full p-6 relative">
            <button onClick={() => setShowShopifyModal(false)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-200 font-bold">✕</button>
            <h3 className="text-lg font-bold text-white flex items-center gap-2"><ShoppingBag className="w-5 h-5 text-amber-400" /><span>Connect your Shopify store</span></h3>
            <p className="text-xs text-slate-300 mt-2">Your AI employee needs catalog and inventory access to keep everything in sync.</p>
            <div className="mt-4">
              <label className="block text-[10px] font-bold text-slate-300 uppercase tracking-wider mb-1.5">Store domain</label>
              <div className="relative rounded-xl shadow-sm">
                <input type="text" value={shopifyDomain} onChange={(e) => setShopifyDomain(e.target.value)} placeholder="mystore.myshopify.com" className="block w-full pl-3.5 pr-3.5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-400/20 focus:border-amber-400 transition-all" />
              </div>
            </div>
            <button type="button" disabled={shopifyConnecting || !shopifyDomain} onClick={() => {
              setShopifyConnecting(true);
              showToast("Initializing secure OAuth with Shopify App Store...", "info");
              setTimeout(() => {
                setShopifyConnecting(false);
                setShopifyConnected(true);
                setShowShopifyModal(false);
                showToast("Shopify store connected successfully!", "success");
              }, 1800);
            }} className="w-full mt-5 py-2.5 px-4 rounded-xl bg-violet-700 text-white font-bold text-xs tracking-wider hover:bg-violet-800 transition-all flex items-center justify-center gap-2 disabled:opacity-50">
              {shopifyConnecting ? <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> : <><span>Connect to Shopify</span><ArrowRight className="w-4 h-4" /></>}
            </button>
          </div>
        </div>
      )}

      {/* AI Post Generator Modal */}
      {showPostModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
          <div className="bg-white rounded-3xl max-w-4xl w-full p-8 relative shadow-2xl max-h-[90vh] overflow-y-auto">
            <button onClick={() => setShowPostModal(false)} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all">✕</button>
            <div className="text-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center mx-auto shadow-2xl shadow-purple-500/30">
                <Image className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-extrabold text-slate-900 mt-4">🖼️ AI Post Generator</h2>
              <p className="text-sm text-slate-500 mt-1">Generate AI images + captions for your products</p>
            </div>
            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Select Product</label>
              <select value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)} className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600">
                <option value="">Select a product...</option>
                {MOCK_PRODUCTS.map(p => (<option key={p.id} value={p.id}>{p.name}</option>))}
              </select>
            </div>
            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Image Style</label>
              <div className="grid grid-cols-4 gap-2">
                {['Modern', 'Vintage', 'Minimal', 'Luxury'].map((style) => (
                  <button key={style} onClick={() => setImageStyle(style)} className={`p-2 rounded-xl border-2 transition-all text-xs font-bold ${imageStyle === style ? 'border-pink-500 bg-pink-50 text-pink-700' : 'border-slate-200 hover:border-pink-200 text-slate-600'}`}>
                    {style}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Caption Tone</label>
              <div className="grid grid-cols-3 gap-2">
                {['Professional', 'Casual', 'Fun'].map((tone) => (
                  <button key={tone} onClick={() => setCaptionTone(tone)} className={`p-2 rounded-xl border-2 transition-all text-xs font-bold ${captionTone === tone ? 'border-purple-500 bg-purple-50 text-purple-700' : 'border-slate-200 hover:border-purple-200 text-slate-600'}`}>
                    {tone}
                  </button>
                ))}
              </div>
            </div>
            <button onClick={generatePost} disabled={!selectedProduct} className="w-full mt-6 py-3 px-4 rounded-xl bg-gradient-to-r from-pink-500 to-purple-600 text-white font-bold text-sm hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed">
              🎨 Generate AI Post
            </button>
            {generatedPost && (
              <div className="mt-6 border-2 border-violet-200 rounded-2xl p-4 bg-gradient-to-br from-violet-50 to-pink-50">
                <h4 className="text-xs font-bold text-violet-700 mb-3 flex items-center gap-2"><Sparkles className="w-4 h-4" /> AI Generated Post</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-white rounded-xl p-4 border border-slate-200 flex items-center justify-center min-h-[250px]">
                    <div className="text-center">
                      <span className="text-7xl">🖼️</span>
                      <p className="text-xs text-slate-500 mt-2">{imageStyle} Style</p>
                      <button onClick={generatePost} className="mt-2 text-[10px] text-pink-600 hover:text-pink-800 font-bold">🔄 Regenerate Image</button>
                    </div>
                  </div>
                  <div className="bg-white rounded-xl p-4 border border-slate-200 flex flex-col">
                    <div className="flex-1">
                      <h4 className="text-xs font-bold text-slate-700 mb-2">📝 Caption</h4>
                      <p className="text-sm text-slate-600 leading-relaxed">{generatedPost.caption}</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        <span className="text-[8px] bg-blue-500/10 text-blue-200 px-2 py-0.5 rounded-full">#ShopNow</span>
                        <span className="text-[8px] bg-pink-100 text-pink-700 px-2 py-0.5 rounded-full">#Trending</span>
                        <span className="text-[8px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">#Quality</span>
                        <span className="text-[8px] bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">#Style</span>
                      </div>
                    </div>
                    <button onClick={generatePost} className="mt-3 text-[10px] text-violet-600 hover:text-violet-800 font-bold text-left">🔄 Regenerate Caption</button>
                  </div>
                </div>
                <div className="mt-4 flex gap-2">
                  <button onClick={() => { showToast("📥 Post saved as draft!", "success"); setGeneratedPost(null); setShowPostModal(false); }} className="flex-1 py-2.5 px-4 rounded-xl bg-emerald-600 text-white font-bold text-sm hover:bg-emerald-700 transition-all">💾 Save as Draft</button>
                  <button onClick={() => { setGeneratedPost(null); showToast("🔄 Start fresh!", "info"); }} className="py-2.5 px-4 rounded-xl border border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50 transition-all">🔄 New</button>
                </div>
              </div>
            )}
            <p className="text-[8px] text-slate-400 text-center mt-3">🔒 AI-powered • DALL-E + GPT-4 • Instagram & Facebook ready</p>
          </div>
        </div>
      )}

      {/* Schedule Post Modal */}
      {showScheduleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
          <div className="bg-[#07111d]/95 border border-white/10 rounded-3xl max-w-2xl w-full p-8 relative shadow-2xl">
            <button onClick={() => setShowScheduleModal(false)} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all">✕</button>
            <div className="text-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center mx-auto shadow-2xl shadow-orange-500/30">
                <Calendar className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-extrabold text-slate-900 mt-4">📅 Schedule Post</h2>
              <p className="text-sm text-slate-500 mt-1">Schedule AI-generated posts to social media</p>
            </div>
            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Select Post</label>
              <select className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600">
                <option value="">Select a saved post...</option>
                <option value="1">Classic Cotton Tee - AI Post</option>
                <option value="2">Denim Jacket - AI Post</option>
              </select>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div><label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Date</label><input type="date" defaultValue="2026-07-20" className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600" /></div>
              <div><label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Time</label><input type="time" defaultValue="10:00" className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600" /></div>
            </div>
            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Platform</label>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {instagramConnected && <button className="p-2.5 rounded-xl border-2 border-pink-500 bg-pink-50 text-pink-700 font-bold text-sm flex items-center justify-center gap-1"><Instagram className="w-4 h-4" /> Insta</button>}
                {facebookConnected && <button className="p-2.5 rounded-xl border-2 border-blue-500 bg-blue-50 text-blue-700 font-bold text-sm flex items-center justify-center gap-1"><Facebook className="w-4 h-4" /> FB</button>}
                {tiktokConnected && <button className="p-2.5 rounded-xl border-2 border-black bg-slate-100 text-black font-bold text-sm flex items-center justify-center gap-1"><Music className="w-4 h-4" /> TT</button>}
                {youtubeConnected && <button className="p-2.5 rounded-xl border-2 border-red-500 bg-red-50 text-red-700 font-bold text-sm flex items-center justify-center gap-1"><Youtube className="w-4 h-4" /> YT</button>}
                {twitterConnected && <button className="p-2.5 rounded-xl border-2 border-sky-500 bg-sky-50 text-sky-700 font-bold text-sm flex items-center justify-center gap-1"><Twitter className="w-4 h-4" /> X</button>}
              </div>
            </div>
            <div className="mt-4 bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl p-3 border border-orange-200">
              <p className="text-xs text-orange-700 flex items-center gap-2"><Sparkles className="w-3.5 h-3.5" /> 🤖 AI suggests: <strong>July 20, 2026 at 10:00 AM</strong> (Best engagement time)</p>
            </div>
            <button onClick={() => { showToast("📅 Post scheduled successfully!", "success"); setShowScheduleModal(false); }} className="w-full mt-6 py-3 px-4 rounded-xl bg-gradient-to-r from-orange-500 to-amber-600 text-white font-bold text-sm hover:shadow-xl transition-all">📅 Schedule Post</button>
            <p className="text-[8px] text-slate-400 text-center mt-3">🔒 Post will be published automatically at the scheduled time</p>
          </div>
        </div>
      )}

      {/* Comments Dashboard Modal */}
      {showCommentsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
          <div className="bg-[#07111d]/95 border border-white/10 rounded-3xl max-w-3xl w-full p-8 relative shadow-2xl max-h-[90vh] overflow-y-auto">
            <button onClick={() => setShowCommentsModal(false)} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all">✕</button>
            <div className="text-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center mx-auto shadow-2xl shadow-blue-500/30">
                <MessageCircle className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-extrabold text-slate-900 mt-4">💬 Comments Dashboard</h2>
              <p className="text-sm text-slate-500 mt-1">View & manage all social comments</p>
            </div>
            <div className="mt-4 space-y-3">
              {[
                { platform: <Instagram className="w-4 h-4 text-pink-600" />, user: "@sarah_j", comment: "Love this product! 😍", time: "2 hours ago", status: "Pending" },
                { platform: <Facebook className="w-4 h-4 text-blue-600" />, user: "@mike_23", comment: "Is this available in blue?", time: "5 hours ago", status: "Replied" },
                { platform: <Twitter className="w-4 h-4 text-sky-600" />, user: "@emma_w", comment: "Great quality, just ordered!", time: "1 day ago", status: "Replied" },
                { platform: <Music className="w-4 h-4 text-black" />, user: "@alex_t", comment: "How long does shipping take?", time: "2 days ago", status: "Pending" },
              ].map((item, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100 hover:shadow-md transition-all">
                  <div>
                    <p className="text-sm font-bold text-slate-900 flex items-center gap-2">{item.platform} {item.user}</p>
                    <p className="text-xs text-slate-600">{item.comment}</p>
                    <p className="text-[8px] text-slate-400">{item.time}</p>
                  </div>
                  <span className={`px-2 py-0.5 text-[8px] font-bold rounded-full ${item.status === 'Replied' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
            <button onClick={() => showToast("🔄 Comments refreshed!", "success")} className="w-full mt-4 py-2.5 px-4 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-600 text-white font-bold text-sm hover:shadow-xl transition-all">🔄 Refresh Comments</button>
            <p className="text-[8px] text-slate-400 text-center mt-3">🔒 Real-time comments • Auto-reply enabled</p>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-8 relative shadow-2xl max-h-[90vh] overflow-y-auto">
            <button onClick={() => setShowSettingsModal(false)} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all">✕</button>
            <div className="text-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-slate-600 to-slate-800 flex items-center justify-center mx-auto shadow-2xl shadow-slate-500/30">
                <Settings className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-extrabold text-slate-900 mt-4">⚙️ Settings</h2>
              <p className="text-sm text-slate-500 mt-1">Manage your account & preferences</p>
            </div>
            <div className="mt-4 space-y-4">
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Account</h4>
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">{authenticatedUser || 'user@example.com'}</span>
                  <button className="text-xs text-violet-600 font-bold hover:underline">Change Email</button>
                </div>
              </div>
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Connected Accounts</h4>
                <div className="mt-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2"><ShoppingBag className="w-4 h-4 text-emerald-600" /><span className="text-sm font-medium text-slate-700">Shopify</span></div>
                    <span className={`text-xs font-bold ${shopifyConnected ? 'text-emerald-600' : 'text-amber-600'}`}>{shopifyConnected ? '● Connected' : '○ Not Connected'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2"><Instagram className="w-4 h-4 text-pink-600" /><span className="text-sm font-medium text-slate-700">Instagram</span></div>
                    <span className={`text-xs font-bold ${instagramConnected ? 'text-emerald-600' : 'text-amber-600'}`}>{instagramConnected ? '● Connected' : '○ Not Connected'}</span>
                  </div>
                </div>
              </div>
              <button onClick={() => { showToast("💾 Settings saved!", "success"); setShowSettingsModal(false); }} className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-slate-700 to-slate-900 text-white font-bold text-sm hover:shadow-xl transition-all">💾 Save Settings</button>
            </div>
            <p className="text-[8px] text-slate-400 text-center mt-3">🔒 Your data is encrypted and secure</p>
          </div>
        </div>
      )}

      {/* SEO Modal */}
      {showSEOModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-8 relative shadow-2xl max-h-[90vh] overflow-y-auto">
            <button onClick={() => setShowSEOModal(false)} className="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-all">✕</button>
            <div className="text-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-rose-500 to-orange-500 flex items-center justify-center mx-auto shadow-2xl shadow-rose-500/30">
                <Globe className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-2xl font-extrabold text-slate-900 mt-4">🌐 Global SEO Dashboard</h2>
              <p className="text-sm text-slate-500 mt-1">Basic SEO analytics for your store</p>
            </div>
            <div className="mt-4 flex justify-center"><span className="text-[8px] bg-gradient-to-r from-violet-500 to-indigo-600 text-white px-3 py-1 rounded-full">📍 PHASE 1 - BASIC ANALYTICS</span></div>
            <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 p-3 rounded-xl border border-blue-200 text-center"><p className="text-xs font-black text-blue-700">1,247</p><p className="text-[8px] text-slate-500">Keywords</p></div>
              <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 p-3 rounded-xl border border-emerald-200 text-center"><p className="text-xs font-black text-emerald-700">89</p><p className="text-[8px] text-slate-500">Ranking</p></div>
              <div className="bg-gradient-to-br from-purple-50 to-purple-100/50 p-3 rounded-xl border border-purple-200 text-center"><p className="text-xs font-black text-purple-700">4.2K</p><p className="text-[8px] text-slate-500">Traffic</p></div>
              <div className="bg-gradient-to-br from-amber-50 to-amber-100/50 p-3 rounded-xl border border-amber-200 text-center"><p className="text-xs font-black text-amber-700">+32%</p><p className="text-[8px] text-slate-500">Growth</p></div>
            </div>
            <div className="mt-4 bg-white/5 rounded-xl border border-white/10 p-4">
              <h4 className="text-xs font-bold text-slate-700 mb-3">📈 Search Trends</h4>
              <div className="space-y-2">
                {[{ keyword: "Classic Cotton Tee", trend: "+45%", status: "up" }, { keyword: "Denim Jacket Sale", trend: "+28%", status: "up" }, { keyword: "Running Sneakers", trend: "-12%", status: "down" }, { keyword: "Leather Wallet", trend: "+67%", status: "up" }].map((item, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-slate-50 rounded-lg">
                    <span className="text-xs font-medium text-slate-700">{item.keyword}</span>
                    <span className={`text-xs font-bold ${item.status === 'up' ? 'text-emerald-600' : 'text-rose-600'}`}>{item.trend}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-4 bg-gradient-to-r from-rose-50 to-orange-50 rounded-xl p-4 border border-rose-200">
              <h4 className="text-xs font-bold text-rose-700 mb-2 flex items-center gap-2"><Sparkles className="w-4 h-4" /> SEO Suggestions (Beta)</h4>
              <ul className="space-y-1.5">
                <li className="text-xs text-slate-600 flex items-start gap-2"><span className="text-emerald-500">✅</span><span>Add "Classic Cotton Tee" to your meta description</span></li>
                <li className="text-xs text-slate-600 flex items-start gap-2"><span className="text-emerald-500">✅</span><span>Update title tag with "Premium Denim Jacket"</span></li>
                <li className="text-xs text-slate-600 flex items-start gap-2"><span className="text-amber-500">⚡</span><span>Target keyword: "Leather Wallet Gift" - trending up</span></li>
              </ul>
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => showToast("🔄 SEO analysis updated!", "success")} className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-rose-500 to-orange-500 text-white font-bold text-sm hover:shadow-xl transition-all">🔄 Update SEO Analysis</button>
              <button onClick={() => showToast("📄 SEO report generated!", "success")} className="py-2.5 px-4 rounded-xl border border-slate-200 text-slate-600 font-bold text-sm hover:bg-slate-50 transition-all">📄 Export Report</button>
            </div>
            <p className="text-[8px] text-slate-400 text-center mt-3">🔒 Basic SEO analytics • Phase 1 MVP</p>
          </div>
        </div>
      )}

      {/* FOOTER */}
      {currentView === "landing" && !authenticatedUser ? (
        <Footer />
      ) : (
        <footer id="app-footer" className="mt-auto border-t border-amber-400/20 bg-[#02040d]/70 py-7 text-center">
          <p className="px-4 text-sm font-semibold leading-relaxed tracking-wide text-white sm:text-base">
            <span className="text-amber-300">© 2026 Digital FTE</span>
            <span className="mx-2 text-white/60">•</span>
            {t("footer.description")}
          </p>
        </footer>
      )}
    </div>
  );
}