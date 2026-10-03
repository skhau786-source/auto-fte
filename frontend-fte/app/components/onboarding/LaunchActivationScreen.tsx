"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { InteractiveRobot } from "../site/InteractiveRobot";
import { useLanguage } from "../../lib/LanguageContext";

type ScreenStatus = "charging" | "pulse" | "explosion" | "warp";

interface LaunchActivationScreenProps {
  onComplete?: () => void;
}

const CHARGING_DURATION = 7000;
const PULSE_DURATION = 2500;
const EXPLOSION_DURATION = 1800;
const WARP_DURATION = 1200;

export function LaunchActivationScreen({ onComplete }: LaunchActivationScreenProps) {
  const { t } = useLanguage();
  const statusLogs = [
    t("activation.logs.neural"),
    t("activation.logs.sync"),
    t("activation.logs.creative"),
    t("activation.logs.signals"),
    t("activation.logs.inventory"),
    t("activation.logs.launch"),
  ];
  const badges = [
    { title: t("activation.badges.neural"), subtitle: t("activation.badges.activated"), icon: <Zap className="w-4 h-4" /> },
    { title: t("activation.badges.autopilot"), subtitle: t("activation.badges.engaged"), icon: <Sparkles className="w-4 h-4" /> },
    { title: t("activation.badges.guard"), subtitle: t("activation.badges.online"), icon: <ShieldCheck className="w-4 h-4" /> },
  ];
  const [status, setStatus] = useState<ScreenStatus>("charging");
  const [logIndex, setLogIndex] = useState(0);
  const [badgeIndex, setBadgeIndex] = useState(0);
  const [readyPercent, setReadyPercent] = useState(0);

  useEffect(() => {
    if (status !== "charging") return;

    const interval = window.setInterval(() => {
      setLogIndex((prev) => (prev + 1) % statusLogs.length);
      setBadgeIndex((prev) => (prev + 1) % badges.length);
      setReadyPercent((prev) => Math.min(100, prev + 16));
    }, 700);

    return () => window.clearInterval(interval);
  }, [badges.length, status, statusLogs.length]);

  useEffect(() => {
    if (status === "charging") {
      const timeout = window.setTimeout(() => setStatus("pulse"), CHARGING_DURATION);
      return () => window.clearTimeout(timeout);
    }

    if (status === "pulse") {
      const timeout = window.setTimeout(() => setStatus("explosion"), PULSE_DURATION);
      return () => window.clearTimeout(timeout);
    }

    if (status === "explosion") {
      const timeout = window.setTimeout(() => setStatus("warp"), EXPLOSION_DURATION);
      return () => window.clearTimeout(timeout);
    }

    if (status === "warp") {
      const timeout = window.setTimeout(() => {
        onComplete?.();
      }, WARP_DURATION);
      return () => window.clearTimeout(timeout);
    }

    return undefined;
  }, [onComplete, status]);

  const particles = useMemo(
    () => Array.from({ length: 16 }, (_, index) => ({ id: index, size: 8 + (index % 4) * 2 })),
    []
  );

  const percent = Math.min(
    100,
    Math.max(readyPercent, status === "charging" ? 24 : status === "pulse" ? 72 : status === "explosion" ? 96 : 100)
  );

  return (
    <div className="relative min-h-[80vh] w-full overflow-hidden rounded-[32px] border border-amber-400/30 bg-[radial-gradient(circle_at_top,_rgba(251,191,36,0.16),_transparent_40%),linear-gradient(135deg,#07111d_0%,#10233f_45%,#193a5d_100%)] p-6 text-white shadow-2xl shadow-amber-500/10">
      {/* ambient glow, purely decorative, ignores layout flow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(255,255,255,0.06),_transparent_55%)]" />
      {/* faint scanlines for a "command deck" feel */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(to bottom, rgba(255,255,255,0.6) 0px, rgba(255,255,255,0.6) 1px, transparent 1px, transparent 3px)",
        }}
      />

      <AnimatePresence mode="wait">
        {status !== "warp" ? (
          <motion.div
            key={status}
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.04 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="relative z-10 grid h-full min-h-[72vh] grid-rows-[minmax(220px,34vh)_auto_auto] items-center justify-items-center gap-4 py-4"
          >
            <div className="pointer-events-none absolute inset-0 bg-black/20" style={{ opacity: status === "pulse" ? 0.5 : 0.16 }} />

            {/* ROW 1 — robot, locked inside a fixed frame so it can never bleed into row 2/3 */}
            <div className="relative flex h-full w-full items-center justify-center overflow-hidden">
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <motion.div
                  className="rounded-full border border-amber-300/20"
                  animate={{
                    width: status === "pulse" ? 260 : status === "explosion" ? 340 : 200,
                    height: status === "pulse" ? 260 : status === "explosion" ? 340 : 200,
                    opacity: status === "pulse" ? 0.9 : status === "explosion" ? 0.2 : 0.15,
                  }}
                  transition={{ duration: 0.6, ease: "easeOut" }}
                />
              </div>

              {particles.map((particle, index) => {
                const driftX = (index % 4) * 14 - 21;
                const driftY = Math.floor(index / 4) * 14 - 21;

                return (
                  <motion.div
                    key={particle.id}
                    className="pointer-events-none absolute left-1/2 top-1/2 rounded-full bg-amber-300/80 shadow-[0_0_18px_rgba(251,191,36,0.8)]"
                    style={{ width: particle.size, height: particle.size, opacity: status === "charging" ? 0.95 : 0.6 }}
                    animate={{
                      x: driftX,
                      y: driftY,
                      scale: status === "explosion" ? 1.4 : 1,
                      opacity: status === "charging" ? 0.95 : status === "pulse" ? 0.8 : 0.35,
                    }}
                    transition={{ type: "spring", stiffness: 120, damping: 16, mass: 0.6 }}
                  />
                );
              })}

              <motion.div
                animate={{
                  scale: status === "pulse" ? [1, 1.06, 1] : status === "explosion" ? 1.08 : 1,
                  rotate: status === "explosion" ? 6 : 0,
                  y: status === "pulse" ? [0, -8, 0] : 0,
                }}
                transition={{ duration: 0.8, ease: "easeOut" }}
                className="relative z-20 h-full max-h-[220px] w-[160px] shrink-0 md:w-[200px]"
              >
                <div className="h-full w-full [&>*]:h-full [&>*]:w-full [&>*]:object-contain">
                  <InteractiveRobot isEmailFocused={false} isPasswordFocused={false} isPasswordVisible={false} isWaving={status !== "charging"} compact />
                </div>
              </motion.div>
            </div>

            {/* ROW 2 — status card, its own grid row, guaranteed below the robot frame */}
            <motion.div
              className="relative z-20 w-[92%] max-w-xl rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-center shadow-lg backdrop-blur"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
            >
              <div className="mb-2 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.3em] text-amber-200">
                <Sparkles className="w-3.5 h-3.5" />
                {t("activation.engine")}
              </div>
              <p className="text-sm font-semibold text-slate-100">{statusLogs[logIndex]}</p>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-amber-400 via-yellow-300 to-orange-500"
                  animate={{ width: `${percent}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
              <p className="mt-2 text-[11px] text-slate-300">{t("activation.workspace")} • {percent}% {t("activation.ready")}</p>
            </motion.div>

            {/* ROW 3 — badges, own grid row, guaranteed below the status card */}
            <motion.div
              className="relative z-20 flex w-full max-w-2xl flex-wrap items-center justify-center gap-3"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              {badges.map((badge, index) => {
                const isActive = index === badgeIndex;
                return (
                  <motion.div
                    key={badge.title}
                    className={`rounded-3xl border px-4 py-3 text-xs font-semibold backdrop-blur-md ${
                      isActive
                        ? "border-amber-300/40 bg-amber-400/15 text-amber-100"
                        : "border-white/10 bg-white/10 text-slate-200"
                    }`}
                    animate={{ scale: isActive ? 1.02 : 1, opacity: isActive ? 1 : 0.8 }}
                    transition={{ duration: 0.25 }}
                  >
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-white/10 p-1">{badge.icon}</span>
                      <span>
                        {badge.title} <span className="font-medium">• {badge.subtitle}</span>
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          </motion.div>
        ) : (
          <motion.div
            key="warp"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1.08 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="relative z-10 flex min-h-[72vh] items-center justify-center"
          >
            <div className="absolute inset-0 overflow-hidden rounded-[24px]">
              <div className="absolute left-1/2 top-1/2 h-[180%] w-[180%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-amber-300/30" />
              <div className="absolute left-1/2 top-1/2 h-[140%] w-[140%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" />
              {[...Array(20)].map((_, index) => (
                <motion.div
                  key={index}
                  className="absolute left-1/2 top-1/2 h-[2px] w-[60px] rounded-full bg-amber-300/70"
                  animate={{
                    rotate: index * 18,
                    x: [0, 140, 0],
                    opacity: [0, 1, 0],
                  }}
                  transition={{ duration: 0.9, delay: index * 0.03, ease: "easeOut" }}
                />
              ))}
            </div>

            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
              className="relative z-20 rounded-3xl border border-amber-300/30 bg-slate-950/70 px-6 py-5 text-center shadow-2xl shadow-amber-500/20"
            >
              <div className="mb-4 flex justify-center">
                <div className="rounded-full bg-amber-400/15 p-3 text-amber-300">
                  <CheckCircle2 className="h-8 w-8" />
                </div>
              </div>
              <p className="text-lg font-black text-white">{t("activation.completeTitle")}</p>
              <p className="mt-2 text-sm text-slate-300">{t("activation.completeDesc")}</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}