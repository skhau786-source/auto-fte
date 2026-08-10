"use client";

import React, { useState } from "react";
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
  Check, 
  LogOut, 
  ShieldCheck, 
  AlertCircle,
  MessageSquare,
  Globe,
  Instagram,
  Image,
  Calendar,
  MessageCircle,
  Settings,
  Loader2,
  Twitter,
  Facebook,
  Youtube,
  Music,
  LayoutDashboard,
  Package,
  Share2,
  Users,
  CreditCard,
  BarChart3,
  DollarSign,
  Bell,
} from "lucide-react";
import { InteractiveRobot } from "./components/InteractiveRobot";
import BusinessDashboard from "./components/BusinessDashboard";

// --- MOCK DATA ---
const MOCK_PRODUCTS = [
  { id: 1, name: "Classic Cotton Tee", price: 24.99, stock: 142, status: "In Stock" },
  { id: 2, name: "Denim Jacket", price: 89.99, stock: 8, status: "Low Stock" },
  { id: 3, name: "Running Sneakers", price: 129.99, stock: 0, status: "Out of Stock" },
  { id: 4, name: "Leather Wallet", price: 45.00, stock: 67, status: "In Stock" },
  { id: 5, name: "Wool Beanie", price: 19.99, stock: 5, status: "Low Stock" },
  { id: 6, name: "Canvas Backpack", price: 74.99, stock: 34, status: "In Stock" },
];

// --- API HELPER FUNCTIONS ---
export const buildApiUrl = (endpoint: string) => {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000";
  return `${baseUrl}${endpoint}`;
};

// --- MAIN AUTH PAGE COMPONENT ---
export default function AuthPage() {
  const [currentView, setCurrentView] = useState<"landing" | "auth">("landing");
  const [dailyOrders, setDailyOrders] = useState(250);
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

  // ONBOARDING FLOW STATES
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [isReady, setIsReady] = useState(false);


  // Add a toast notification helper
  const showToast = (message: string, type: "success" | "info" | "error" = "success") => {
    const id = Date.now().toString();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const normalizeUserEmail = (value?: string | null) => {
    const trimmedValue = value?.trim();
    return trimmedValue || "user@example.com";
  };

  // Time-based greeting for onboarding welcome screen
  const getTimeBasedGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  };

  // Extract a friendly display name from the user's email
  const getDisplayName = (emailValue: string | null) => {
    if (!emailValue) return "there";
    const namePart = emailValue.split("@")[0];
    if (!namePart) return "there";
    return namePart.charAt(0).toUpperCase() + namePart.slice(1);
  };

  const enterOnboardingFlow = (userEmail: string, successMessage: string) => {
    const safeEmail = normalizeUserEmail(userEmail);
    setAuthenticatedUser(safeEmail);
    setFlowMode("onboarding");
    setCurrentView("auth");
    setShowDashboard(false);
    setOnboardingStep(2);
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
  

  const handleOAuth = (platform: "shopify" | "google") => {
    if (platform === "google") {
      googleLogin();
    } else {
      showToast(`Initializing secure OAuth with Shopify App Store...`, "info");
      setLoading(true);
      setTimeout(() => {
        setLoading(false);
        setAuthenticatedUser(email || "founder@mystore.com");
        showToast(`Welcome! Successfully connected via Shopify.`, "success");
      }, 1500);
    }
  };

  const googleLogin = useGoogleLogin({
    onSuccess: async (codeResponse) => {
      showToast("Authenticating with Google...", "info");
      setLoading(true);
      
      try {
        const response = await fetch("https://www.googleapis.com/oauth2/v1/userinfo", {
          headers: { Authorization: `Bearer ${codeResponse.access_token}` },
        });
        const userInfo = await response.json();
        
        const googleUserEmail = normalizeUserEmail(userInfo.email);

        // Directly enter onboarding flow (sets authenticatedUser + onboardingStep together,
        // same as manual login) — avoids an empty "step 1" flash before step 2 renders.
        setTimeout(() => {
          enterOnboardingFlow(googleUserEmail, `Welcome ${userInfo.name || "there"}! Successfully logged in with Google.`);
        }, 1500);
        
        try {
          await fetch(buildApiUrl("/api/auth/google"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: userInfo.email,
              name: userInfo.name,
              picture: userInfo.picture,
              googleId: userInfo.id,
            }),
          });
        } catch (error) {
          console.log("Backend sync optional:", error);
        }
      } catch (error) {
        setLoading(false);
        showToast("Google authentication failed. Please try again.", "error");
        console.error("Google login error:", error);
      }
    },
    onError: () => {
      showToast("Google login failed. Please try again.", "error");
    },
    flow: "implicit",
  });

  const handleAuthSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      showToast("Please enter a valid email address.", "error");
      return;
    }
    if (authMode === "signup" && !fullName) {
      showToast("Please enter your full name.", "error");
      return;
    }
    if (!password || password.length < 6) {
      showToast("Password must be at least 6 characters long.", "error");
      return;
    }

    setLoading(true);
    showToast(authMode === "signin" ? "Verifying secure credentials..." : "Provisioning Digital FTE container instance...", "info");
    
    setTimeout(() => {
      enterOnboardingFlow(
        email,
        authMode === "signin"
          ? "Login successful! Let's set up your store."
          : "Account created! Let's set up your store."
      );
    }, 2000);
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
    showToast("Logged out successfully.", "info");
  };

  const isAuthenticated = Boolean(authenticatedUser);
  const isOnboardingActive = isAuthenticated && flowMode === "onboarding";
  const isDashboardActive = isAuthenticated && flowMode === "dashboard";

  return (
    <div id="auth-screen-root" className="min-h-screen bg-[#F5F3FF] text-slate-900 flex flex-col font-sans transition-all duration-300">
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
      <header id="app-header" className="border-b border-violet-100/50 bg-white/80 backdrop-blur-md sticky top-0 z-40 px-6 sm:px-12 py-4 flex items-center justify-between">
        <div 
          className="flex items-center gap-3 cursor-pointer group"
          onClick={() => {
            handleLogout();
          }}
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-violet-500/20 group-hover:scale-105 transition-transform">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-violet-950">Digital FTE</h1>
            <p className="text-[10px] font-bold text-violet-600 tracking-widest uppercase animate-pulse">E-Commerce Autonomous AI</p>
          </div>
        </div>

        {currentView === "landing" && !authenticatedUser && (
          <nav className="hidden lg:flex items-center gap-8 text-sm font-semibold text-slate-600">
            <a href="#features" onClick={(e) => { e.preventDefault(); document.getElementById("features")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">Features</a>
            <a href="#how-it-works" onClick={(e) => { e.preventDefault(); document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">How It Works</a>
            <a href="#pricing" onClick={(e) => { e.preventDefault(); document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">Pricing</a>
            <a href="#about" onClick={(e) => { e.preventDefault(); document.getElementById("about")?.scrollIntoView({ behavior: "smooth" }); }} className="hover:text-violet-600 transition-colors">About</a>
          </nav>
        )}

        <div className="flex items-center gap-3">
          {authenticatedUser ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-slate-50 text-slate-700 border border-slate-200 hover:bg-slate-100 transition-all cursor-pointer"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Log Out</span>
            </button>
          ) : currentView === "landing" ? (
            <button
              onClick={() => {
                setAuthMode("signup");
                setCurrentView("auth");
                showToast("Directing to trial signup view.", "info");
              }}
              className="px-4 py-2.5 text-sm font-bold rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:shadow-lg text-white shadow-md shadow-violet-500/10 hover:shadow-violet-500/25 transition-all cursor-pointer"
            >
              Get Started
            </button>
          ) : (
            <button
              onClick={() => {
                setCurrentView("landing");
                showToast("Returned to homepage.", "info");
              }}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-violet-50 text-violet-700 border border-violet-100 hover:bg-violet-100 transition-all cursor-pointer"
            >
              <span>← Back to Home</span>
            </button>
          )}
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className={`flex-1 flex flex-col ${currentView === "landing" && !authenticatedUser ? "py-6 px-4 sm:px-6 lg:px-8" : "justify-center py-6 px-4 sm:px-6 lg:px-8"}`}>
        
        {isAuthenticated ? (
          isDashboardActive || showDashboard ? (
            // ===== BUSINESS DASHBOARD =====
            <BusinessDashboard
              userEmail={authenticatedUser}
              onLogout={handleLogout}
            />
          ) : (
            // ✅ ONBOARDING FLOW
            <div className="max-w-4xl w-full mx-auto bg-white/90 backdrop-blur-sm border border-violet-100/50 shadow-xl rounded-3xl overflow-hidden animate-fade-in">
              {/* Progress Bar */}
              <div className="bg-gradient-to-r from-violet-900 via-violet-800 to-indigo-950 p-6 text-white">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-cyan-300 animate-pulse" />
                    Setup Your Digital FTE
                  </h2>
                  <span className="text-sm text-violet-200 bg-white/10 px-3 py-1 rounded-full">Step {onboardingStep} of 8</span>
                </div>
                <div className="w-full bg-violet-700/30 rounded-full h-2.5 overflow-hidden">
                  <div 
                    className="bg-gradient-to-r from-emerald-400 to-cyan-400 h-2.5 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${(onboardingStep / 8) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-8">
                {/* ========== STEP 2: Welcome ========== */}
                {onboardingStep === 2 && (
                  <div className="animate-fade-in text-center py-8 relative overflow-hidden">
                

                    <div className="relative w-32 h-32 mx-auto">
                      <div className="absolute inset-0 rounded-full bg-violet-400/20 blur-2xl animate-pulse-slow" />
                      <div className="relative w-32 h-32 rounded-full bg-gradient-to-br from-slate-950 to-violet-950 border border-violet-500/30 flex items-center justify-center p-4 shadow-xl shadow-violet-500/25">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} isFullNameFocused={false} />
                      </div>
                      <div className="absolute -bottom-1.5 -right-1.5 bg-white rounded-full p-1.5 shadow-lg border border-violet-100">
                        <Sparkles className="w-4 h-4 text-violet-500 animate-pulse" />
                      </div>
                    </div>

                    {/* Robot's speech bubble */}
                    <div className="mt-4 flex justify-center">
                      <div className="relative bg-white border border-violet-200 rounded-2xl px-5 py-2.5 shadow-md">
                        <p className="text-base font-bold text-violet-700">Hi {getDisplayName(authenticatedUser)}! 👋</p>
                        <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-t border-l border-violet-200 rotate-45" />
                      </div>
                    </div>

                    <h3 className="text-2xl font-extrabold text-slate-900 mt-4">{getTimeBasedGreeting()}! Welcome to Digital FTE</h3>
                    <p className="text-sm text-slate-500 mt-2">Let's set up your AI employee in 3 simple steps</p>

                    {/* Animated connector-line progress preview */}
                    <div className="mt-8 flex items-center justify-center max-w-md mx-auto">
                      {[
                        { icon: '🔗', label: 'Connect Store' },
                        { icon: '📱', label: 'Connect Social' },
                        { icon: '🚀', label: 'Ready!' },
                      ].map((item, i, arr) => (
                        <React.Fragment key={i}>
                          <div className="flex flex-col items-center gap-2">
                            <div
                              className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl border-2 transition-all duration-300 ${
                                i === 0
                                  ? 'bg-gradient-to-br from-violet-500 to-indigo-600 border-violet-300 shadow-lg shadow-violet-500/30 animate-pulse scale-110'
                                  : 'bg-white border-slate-200 text-slate-400'
                              }`}
                            >
                              {item.icon}
                            </div>
                            <p className={`text-[10px] font-bold ${i === 0 ? 'text-violet-700' : 'text-slate-400'}`}>{item.label}</p>
                          </div>
                          {i < arr.length - 1 && (
                            <div className="flex-1 h-0.5 bg-slate-200 mx-2 mb-5 relative overflow-hidden rounded-full">
                              {i === 0 && (
                                <div className="absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-violet-500 to-indigo-400 animate-pulse rounded-full" />
                              )}
                            </div>
                          )}
                        </React.Fragment>
                      ))}
                    </div>

                    <button
                      onClick={() => setOnboardingStep(3)}
                      className="w-full mt-8 py-3.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                    >
                      Let's Start <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                )}

                {/* ========== STEP 3: Website URL ========== */}
                {onboardingStep === 3 && (
                  <div className="animate-fade-in">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="mb-4">
                          <h3 className="text-lg font-bold text-slate-900">Connect Your Store</h3>
                          <p className="text-sm text-slate-500">Enter your Shopify or E-Commerce website URL</p>
                        </div>
                        <div className="mt-4">
                          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Website URL</label>
                          <div className="flex gap-3">
                            <input
                              type="url"
                              value={websiteUrl}
                              onChange={(e) => setWebsiteUrl(e.target.value)}
                              placeholder="https://yourstore.com"
                              className="flex-1 px-4 py-3 border-2 border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-4 focus:ring-violet-500/20 focus:border-violet-500 transition-all duration-300"
                            />
                            <button
                              onClick={() => {
                                if (!validateWebsite(websiteUrl)) return;
                                setIsConnecting(true);
                                showToast("🔍 Verifying store...", "info");
                                setTimeout(() => {
                                  setIsConnecting(false);
                                  setShopifyConnected(true);
                                  setOnboardingStep(4);
                                  showToast("✅ Store verified & connected!", "success");
                                }, 2000);
                              }}
                              disabled={isConnecting}
                              className="px-6 py-3 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-105 transition-all duration-300 disabled:opacity-50 flex items-center gap-2"
                            >
                              {isConnecting ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Connect Store'}
                            </button>
                          </div>
                          <p className="text-[8px] text-slate-400 mt-2 flex items-center gap-1">
                            <ShieldCheck className="w-3 h-3" /> Must be HTTPS • Valid domain required
                          </p>
                        </div>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 4: Inventory Summary ========== */}
                {onboardingStep === 4 && (
                  <div className="animate-fade-in">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="mb-4">
                          <h3 className="text-lg font-bold text-slate-900">✅ Store Connected!</h3>
                          <p className="text-sm text-slate-500">Your store has been verified successfully</p>
                        </div>
                        <div className="bg-gradient-to-br from-violet-50 to-indigo-50 rounded-xl p-6 border border-violet-100">
                          <div className="flex items-center gap-2 mb-4">
                            <ShoppingBag className="w-5 h-5 text-violet-600" />
                            <h4 className="text-sm font-bold text-slate-700">Store Inventory Summary</h4>
                          </div>
                          <div className="grid grid-cols-3 gap-4">
                            <div className="bg-white p-4 rounded-xl text-center border-2 border-violet-200 shadow-sm hover:shadow-md hover:scale-105 transition-all duration-300">
                              <p className="text-3xl font-black text-violet-600">6</p>
                              <p className="text-[10px] text-slate-500 font-medium">Total Products</p>
                            </div>
                            <div className="bg-white p-4 rounded-xl text-center border-2 border-emerald-200 shadow-sm hover:shadow-md hover:scale-105 transition-all duration-300">
                              <p className="text-3xl font-black text-emerald-600">3</p>
                              <p className="text-[10px] text-slate-500 font-medium">In Stock</p>
                            </div>
                            <div className="bg-white p-4 rounded-xl text-center border-2 border-amber-200 shadow-sm hover:shadow-md hover:scale-105 transition-all duration-300">
                              <p className="text-3xl font-black text-amber-600">2</p>
                              <p className="text-[10px] text-slate-500 font-medium">Low Stock</p>
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => setOnboardingStep(5)}
                          className="w-full mt-6 py-3.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                        >
                          Next Step <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 5: Ready to Continue ========== */}
                {onboardingStep === 5 && (
                  <div className="animate-fade-in">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="flex flex-col items-start">
                          <span className="text-6xl animate-bounce">👉</span>
                          <h3 className="text-3xl font-extrabold text-slate-900 mt-4">Ready to Continue?</h3>
                          <p className="text-sm text-slate-500 mt-2">Click next to connect your social media accounts</p>
                          <button
                            onClick={() => setOnboardingStep(6)}
                            className="w-full mt-6 py-3.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                          >
                            Next Step <ArrowRight className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 6: Social Media ========== */}
                {onboardingStep === 6 && (
                  <div className="animate-fade-in">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="mb-4">
                          <h3 className="text-lg font-bold text-slate-900">Connect Social Media</h3>
                          <p className="text-sm text-slate-500">Tap to connect your social accounts</p>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                          {[
                            { id: 'instagram', label: 'Instagram', icon: <Instagram className="w-5 h-5 text-pink-600" />, connected: instagramConnected, setter: setInstagramConnected },
                            { id: 'facebook', label: 'Facebook', icon: <Facebook className="w-5 h-5 text-blue-600" />, connected: facebookConnected, setter: setFacebookConnected },
                            { id: 'tiktok', label: 'TikTok', icon: <Music className="w-5 h-5 text-black" />, connected: tiktokConnected, setter: setTiktokConnected },
                            { id: 'youtube', label: 'YouTube', icon: <Youtube className="w-5 h-5 text-red-600" />, connected: youtubeConnected, setter: setYoutubeConnected },
                            { id: 'twitter', label: 'Twitter', icon: <Twitter className="w-5 h-5 text-sky-600" />, connected: twitterConnected, setter: setTwitterConnected },
                          ].map((item) => (
                            <div 
                              key={item.id}
                              onClick={() => item.setter(!item.connected)}
                              className={`p-4 rounded-xl border-2 transition-all duration-300 cursor-pointer hover:scale-105 hover:shadow-lg ${
                                item.connected ? 'border-emerald-500 bg-emerald-50/50 shadow-md shadow-emerald-200' : 'border-slate-200 hover:border-violet-300 bg-white'
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  {item.icon}
                                  <span className="text-sm font-bold text-slate-700">{item.label}</span>
                                </div>
                                {item.connected ? (
                                  <CheckCircle2 className="w-5 h-5 text-emerald-500 animate-bounce" />
                                ) : (
                                  <div className="w-5 h-5 rounded-full border-2 border-slate-300" />
                                )}
                              </div>
                              {item.connected && (
                                <p className="text-[8px] text-emerald-600 font-bold mt-1 animate-pulse">✅ Connected</p>
                              )}
                            </div>
                          ))}
                        </div>
                        <div className="mt-4 p-3 bg-gradient-to-r from-amber-50 to-amber-100 border border-amber-200 rounded-xl">
                          <p className="text-[10px] text-amber-700 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            Connect at least one social account to continue
                          </p>
                        </div>
                        <button
                          onClick={() => {
                            if (!isAnySocialConnected) {
                              showToast("⚠️ Please connect at least one social account!", "error");
                              return;
                            }
                            setOnboardingStep(7);
                          }}
                          className="w-full mt-6 py-3.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                        >
                          Continue <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 7: All Connected ========== */}
                {onboardingStep === 7 && (
                  <div className="animate-fade-in">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-3 mb-6">
                          {instagramConnected && <div className="w-14 h-14 rounded-full bg-gradient-to-br from-pink-400 to-pink-500 text-white flex items-center justify-center text-3xl animate-bounce shadow-lg shadow-pink-500/30"><Instagram className="w-7 h-7" /></div>}
                          {facebookConnected && <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-400 to-blue-500 text-white flex items-center justify-center text-3xl animate-bounce shadow-lg shadow-blue-500/30"><Facebook className="w-7 h-7" /></div>}
                          {tiktokConnected && <div className="w-14 h-14 rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-white flex items-center justify-center text-3xl animate-bounce shadow-lg shadow-slate-500/30"><Music className="w-7 h-7" /></div>}
                          {youtubeConnected && <div className="w-14 h-14 rounded-full bg-gradient-to-br from-red-400 to-red-500 text-white flex items-center justify-center text-3xl animate-bounce shadow-lg shadow-red-500/30"><Youtube className="w-7 h-7" /></div>}
                          {twitterConnected && <div className="w-14 h-14 rounded-full bg-gradient-to-br from-sky-400 to-sky-500 text-white flex items-center justify-center text-3xl animate-bounce shadow-lg shadow-sky-500/30"><Twitter className="w-7 h-7" /></div>}
                        </div>
                        <h3 className="text-3xl font-extrabold text-slate-900">All Connected! 🎉</h3>
                        <p className="text-sm text-slate-500 mt-2">Your store and social accounts are connected</p>
                        <button
                          onClick={() => {
                            setIsReady(true);
                            setFlowMode("dashboard");
                            setOnboardingStep(8);
                            showToast("🎉 Setting up your Digital FTE...", "info");
                            setTimeout(() => showToast("⏳ Please wait, building your dashboard...", "info"), 1000);
                            setTimeout(() => showToast("⚡ Almost ready...", "info"), 2500);
                            setTimeout(() => {
                              setShowDashboard(true);
                              showToast("🚀 Your Digital FTE is now live!", "success");
                            }, 4000);
                          }}
                          className="w-full mt-6 py-3.5 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-green-600 text-white font-bold text-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300 flex items-center justify-center gap-2"
                        >
                          🚀 Launch Digital FTE
                        </button>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
                  </div>
                )}

                {/* ========== STEP 8: 2 Minute Wait ========== */}
                {onboardingStep === 8 && !showDashboard && (
                  <div className="animate-fade-in text-center py-12">
                    <div className="flex items-start gap-6">
                      <div className="flex-1">
                        <div className="w-28 h-28 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center mx-auto shadow-2xl shadow-violet-500/30">
                          <Loader2 className="w-14 h-14 text-white animate-spin" />
                        </div>
                        <h2 className="text-3xl font-extrabold text-slate-900 mt-6">⏳ Setting Up Your Digital FTE</h2>
                        <p className="text-sm text-slate-500 mt-2">This will take about 2 minutes...</p>
                        <div className="mt-6 max-w-sm mx-auto">
                          <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
                            <div className="bg-gradient-to-r from-violet-500 via-indigo-500 to-purple-500 h-3 rounded-full transition-all duration-1000 w-[33%] animate-pulse" />
                          </div>
                          <div className="flex justify-between text-[8px] text-slate-400 mt-2">
                            <span className="animate-pulse">Connecting AI</span>
                            <span className="animate-pulse delay-300">Building Dashboard</span>
                            <span className="animate-pulse delay-700">Ready! 🚀</span>
                          </div>
                        </div>
                        <p className="text-[10px] text-slate-400 mt-4 flex items-center justify-center gap-2">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Loading AI models...
                        </p>
                      </div>
                      <div className="hidden md:block w-48 h-48">
                        <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} />
                      </div>
                    </div>
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
                    onClick={() => {
                      setAuthMode("signup");
                      setCurrentView("auth");
                      showToast("Let's configure your autonomous container!", "success");
                    }}
                    className="px-8 py-4 text-sm font-bold text-center rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:shadow-xl hover:shadow-violet-500/40 text-white shadow-lg shadow-violet-500/20 transform hover:scale-105 active:scale-[0.98] transition-all cursor-pointer flex items-center justify-center gap-2 duration-300"
                  >
                    <span>Start Free Trial</span>
                    <ArrowRight className="w-4 h-4 animate-bounce-right" />
                  </button>
                  <button
                    onClick={() => {
                      showToast("Launching interactive feature demonstration...", "info");
                    }}
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
                    <span>2 Minute Setup</span>
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

            <div id="pricing" className="py-12 border-t border-slate-100">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center bg-white border border-slate-100 rounded-[32px] p-8 sm:p-12 shadow-xl shadow-slate-100">
                <div className="lg:col-span-6">
                  <span className="text-xs font-bold text-cyan-600 tracking-widest uppercase bg-cyan-100 px-3 py-1 rounded-full">ROI CALCULATOR</span>
                  <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight mt-3">Calculate Your AI Gains</h2>
                  <p className="text-sm text-slate-500 mt-2 mb-8 leading-relaxed">Drag the slider to define your daily order flow and see how much overhead you convert into autonomous margin.</p>
                  <div className="space-y-6">
                    <div>
                      <div className="flex justify-between text-sm font-bold text-slate-700 mb-2">
                        <span>Daily Orders managed:</span>
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
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">HOURS SAVED / MO</p>
                        <p className="text-2xl font-black text-violet-950 mt-1">{(dailyOrders * 0.16).toFixed(0)} Hrs</p>
                      </div>
                      <div className="bg-slate-50 p-4 rounded-xl">
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">ADDED REVENUE / MO</p>
                        <p className="text-2xl font-black text-emerald-600 mt-1">${(dailyOrders * 2.8 * 30).toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
                      </div>
                    </div>
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
                      onClick={() => {
                        setAuthMode("signup");
                        setCurrentView("auth");
                        showToast("Activating Starter Trial Plan in sign up form.", "success");
                      }}
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
                      onClick={() => {
                        setAuthMode("signup");
                        setCurrentView("auth");
                        showToast("Activating Premium Scaling Plan in sign up form.", "success");
                      }}
                      className="w-full mt-6 py-2.5 px-4 text-xs font-bold text-violet-950 bg-white hover:bg-violet-50 rounded-xl transition-all cursor-pointer"
                    >
                      Deploy Container
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div id="about" className="bg-gradient-to-r from-violet-950 to-indigo-900 rounded-[32px] p-8 sm:p-12 text-center text-white relative overflow-hidden">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight relative z-10">Stop Managing. Start Orchestrating.</h2>
              <p className="text-sm text-violet-200 max-w-xl mx-auto mt-3 relative z-10 leading-relaxed">Unlock 24/7 growth capacity. Connect your Shopify or Google workspace today and let your Digital FTE do the work.</p>
              <button
                onClick={() => {
                  setAuthMode("signup");
                  setCurrentView("auth");
                  showToast("Provisioning container workspace...", "info");
                }}
                className="mt-8 px-8 py-4 bg-white hover:bg-violet-50 text-violet-950 font-bold text-sm rounded-xl transition-all shadow-xl hover:shadow-violet-900/40 relative z-10 cursor-pointer"
              >
                Launch Your First Agent Now
              </button>
            </div>
          </div>
        ) : (
          // AUTH PAGE
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
                  {authMode === "signin" ? "Welcome back" : "Start free trial"}
                </h2>
                <p className="text-sm text-slate-500 mt-1.5">
                  {authMode === "signin" 
                    ? "Log in to command your autonomous e-commerce workforce." 
                    : "No credit card required. Instantly deploy your first AI employee."}
                </p>
              </div>

              <div className="flex-1 flex flex-col justify-center">
                <div className="relative flex p-1 bg-slate-100/80 rounded-xl mb-6 border border-slate-200/50">
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("signin");
                      showToast("Switched to Sign In mode.", "info");
                    }}
                    className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                      authMode === "signin" ? "bg-white text-violet-950 shadow-sm" : "text-slate-500 hover:text-slate-900"
                    }`}
                  >
                    Sign In
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("signup");
                      showToast("Switched to Create Account mode.", "info");
                    }}
                    className={`flex-1 text-center py-2 text-xs font-bold rounded-lg transition-all z-10 cursor-pointer ${
                      authMode === "signup" ? "bg-white text-violet-950 shadow-sm" : "text-slate-500 hover:text-slate-900"
                    }`}
                  >
                    Create Account
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 mb-6">
                  <button
                    type="button"
                    onClick={() => handleOAuth("google")}
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

                <form onSubmit={handleAuthSubmit} className="space-y-4">
                  <div className={`transition-all duration-300 overflow-hidden ${authMode === "signup" ? "max-h-[85px] opacity-100 mb-4" : "max-h-0 opacity-0 pointer-events-none"}`}>
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

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">Email Address</label>
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
                        className="block w-full pl-10 pr-3.5 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
                        placeholder="founder@mystore.com"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide">Password</label>
                      {authMode === "signin" && (
                        <button
                          type="button"
                          onClick={() => {
                            setShowForgotPassword(true);
                            showToast("Please input reset target.", "info");
                          }}
                          className="text-xs font-bold text-violet-600 hover:text-violet-800 transition-colors cursor-pointer"
                        >
                          Forgot Password?
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
                        className="block w-full pl-10 pr-12 py-3 bg-slate-50 border border-transparent focus:border-violet-300 focus:bg-white focus:ring-4 focus:ring-violet-100 outline-none rounded-xl text-slate-900 placeholder-slate-400 text-sm transition-all duration-300"
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
                    className="w-full mt-2 py-3.5 px-4 bg-gradient-to-r from-violet-600 to-indigo-950 text-white font-bold text-sm tracking-wide shadow-lg shadow-violet-200 hover:shadow-violet-300 transform active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {loading ? (
                      <div className="w-5 h-5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    ) : (
                      <>
                        <span>{authMode === "signin" ? "Login to Dashboard" : "Start 7-Day Free Trial"}</span>
                        <ArrowRight className="w-4 h-4 text-violet-100" />
                      </>
                    )}
                  </button>
                </form>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
                {authMode === "signin" ? (
                  <p>
                    Don't have an account?{" "}
                    <button
                      onClick={() => setAuthMode("signup")}
                      className="text-violet-600 font-bold hover:underline cursor-pointer"
                    >
                      Sign up for Free Trial
                    </button>
                  </p>
                ) : (
                  <p>
                    Already have an account?{" "}
                    <button
                      onClick={() => setAuthMode("signin")}
                      className="text-violet-600 font-bold hover:underline cursor-pointer"
                    >
                      Login to Dashboard
                    </button>
                  </p>
                )}
              </div>
            </div>

            <div id="auth-right-panel" className="lg:col-span-6 bg-gradient-to-br from-[#F5F3FF] via-[#F5F3FF] to-violet-50 p-8 sm:p-12 relative flex flex-col items-center justify-center overflow-visible border-t lg:border-t-0 lg:border-l border-violet-100/60">
              <div className="absolute top-1/4 left-1/4 w-[350px] h-[350px] rounded-full bg-violet-300/20 blur-3xl animate-float" />
              <div className="absolute bottom-1/4 right-1/4 w-[250px] h-[250px] rounded-full bg-indigo-300/15 blur-2xl animate-float-delayed" />
              <div className="absolute top-12 right-12 w-6 h-6 rounded-full bg-yellow-300/30 blur-md animate-pulse" />
              <div className="absolute top-1/3 -right-32 w-[500px] h-[500px] rounded-full bg-indigo-200/10 blur-3xl animate-pulse-slow" />

              <div className="absolute bottom-8 left-6 md:bottom-12 md:left-12 z-20 max-w-[210px] sm:max-w-[240px] bg-white/90 backdrop-blur-lg p-4 rounded-2xl border border-violet-200/60 shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 animate-float-delayed">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
                  <span className="text-[10px] font-bold text-slate-700 tracking-wider uppercase">FTE-01 ACTIVE</span>
                </div>
                <p className="text-[11px] leading-relaxed text-slate-800 font-semibold italic">
                  "Working 24/7 to sync catalogs, capture customers, and scale e-commerce revenues."
                </p>
              </div>

              <div className="relative w-full flex items-center justify-center my-6 z-30">
                <div className="absolute w-64 h-64 bg-gradient-to-r from-violet-400/20 to-indigo-400/20 rounded-full blur-2xl animate-pulse-slow" />
                <InteractiveRobot 
                  isEmailFocused={isEmailFocused} 
                  isPasswordFocused={isPasswordFocused} 
                  isPasswordVisible={isPasswordVisible} 
                  isFullNameFocused={isFullNameFocused}
                />
              </div>

              <div className="text-center max-w-sm mt-2 z-20 hover:scale-105 transition-transform duration-300">
                <h3 className="text-lg font-bold text-violet-950 bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent">AI Employee Onboarding</h3>
                <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                  👁️ Focus on fields to interact with robot. 🔒 Hide password for encryption mode.
                </p>
              </div>

              <div className="absolute top-6 right-6 z-20 px-4 py-2 bg-emerald-50 border border-emerald-200 rounded-full text-[10px] font-bold text-emerald-700 tracking-wide">
                ✅ Encrypted end-to-end
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
          <div className="bg-white border border-violet-100 shadow-2xl rounded-2xl max-w-md w-full p-6 relative">
            <button onClick={() => setShowShopifyModal(false)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 font-bold">✕</button>
            <h3 className="text-lg font-bold text-violet-950 flex items-center gap-2"><ShoppingBag className="w-5 h-5 text-violet-600" /><span>Connect your Shopify store</span></h3>
            <p className="text-xs text-slate-500 mt-2">Your AI employee needs catalog and inventory access to keep everything in sync.</p>
            <div className="mt-4">
              <label className="block text-[10px] font-bold text-slate-700 uppercase tracking-wider mb-1.5">Store domain</label>
              <div className="relative rounded-xl shadow-sm">
                <input type="text" value={shopifyDomain} onChange={(e) => setShopifyDomain(e.target.value)} placeholder="mystore.myshopify.com" className="block w-full pl-3.5 pr-3.5 py-2.5 border border-slate-200 rounded-xl text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-600 transition-all" />
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
                        <span className="text-[8px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">#ShopNow</span>
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
          <div className="bg-white rounded-3xl max-w-2xl w-full p-8 relative shadow-2xl">
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
          <div className="bg-white rounded-3xl max-w-3xl w-full p-8 relative shadow-2xl max-h-[90vh] overflow-y-auto">
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
            <div className="mt-4 bg-white rounded-xl border border-slate-200 p-4">
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
      <footer id="app-footer" className="mt-auto py-6 text-center text-xs text-slate-400 border-t border-slate-100 bg-white/40">
        <p>© 2026 Digital FTE. Empowering 24/7 E-Commerce growth with secure, autonomous AI employee containers.</p>
      </footer>
    </div>
  );
}
