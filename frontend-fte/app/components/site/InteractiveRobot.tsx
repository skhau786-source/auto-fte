"use client";

import React, { useState, useEffect, useRef } from "react";
import { useLanguage } from "../../lib/LanguageContext";

interface RobotProps {
  isEmailFocused?: boolean;
  isPasswordFocused?: boolean;
  isPasswordVisible?: boolean;
  isFullNameFocused?: boolean;
  isWaving?: boolean;
  compact?: boolean;
  showWelcome?: boolean;
  showOrbitItems?: boolean;
  showRightArm?: boolean;
  motionPaused?: boolean;
  orbitRadiusX?: number;
  orbitItemScale?: number;
  visualScale?: number;
}

const ORBIT_ITEMS = [
  { label: "Inventory", color: "border-emerald-500/50 bg-emerald-950/80 text-emerald-300", glow: "shadow-emerald-500/30" },
  { label: "Social Media", color: "border-sky-500/50 bg-sky-950/80 text-sky-300", glow: "shadow-sky-500/30" },
  { label: "Auto Reply", color: "border-purple-500/50 bg-purple-950/80 text-purple-300", glow: "shadow-purple-500/30" },
  { label: "AI Images", color: "border-amber-500/50 bg-amber-950/80 text-amber-300", glow: "shadow-amber-500/30" },
  { label: "Analytics", color: "border-indigo-500/50 bg-indigo-950/80 text-indigo-300", glow: "shadow-indigo-500/30" },
];

export function InteractiveRobot({ 
  isEmailFocused = false, 
  isPasswordFocused = false, 
  isPasswordVisible = false, 
  isFullNameFocused = false,
  isWaving = false,
  compact = false,
  showWelcome = false,
  showOrbitItems = true,
  showRightArm = true,
  motionPaused = false,
  orbitRadiusX = 160,
  orbitItemScale = 1,
  visualScale = 1
}: RobotProps) {
  const { t } = useLanguage();
  const robotRef = useRef<HTMLDivElement>(null);
  const [pupilOffset, setPupilOffset] = useState({ x: 0, y: 0 });
  const [headTransform, setHeadTransform] = useState({ rx: 0, ry: 0, tx: 0, ty: 0 });
  const [isBlinking, setIsBlinking] = useState(false);
  const [orbitAngle, setOrbitAngle] = useState(0);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  let state: "private" | "wink" | "surprised" | "wave" | "idle" = "idle";

  if (isWaving) {
    state = "wave";
  } else if (isPasswordFocused) {
    state = isPasswordVisible ? "private" : "wink";
  } else if (isEmailFocused) {
    state = "surprised";
  }

  useEffect(() => {
    if (!isMounted || motionPaused) return;
    let animationFrameId: number;
    const animate = () => {
      setOrbitAngle((prev) => (prev + 0.5) % 360);
      animationFrameId = requestAnimationFrame(animate);
    };
    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [isMounted, motionPaused]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (state === "idle" || state === "wave") {
        setIsBlinking(true);
        setTimeout(() => setIsBlinking(false), 160);
      }
    }, 3800);
    return () => clearInterval(interval);
  }, [state]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!robotRef.current) return;

      const rect = robotRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      const dx = e.clientX - centerX;
      const dy = e.clientY - centerY;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < 1) return;

      const angle = Math.atan2(dy, dx);
      const scale = Math.min(distance / 300, 1);

      setPupilOffset({
        x: Math.cos(angle) * 12 * scale,
        y: Math.sin(angle) * 8 * scale
      });

      setHeadTransform({
        rx: Math.max(-8, Math.min(8, -dy / 30)),
        ry: Math.max(-12, Math.min(12, dx / 30)),
        tx: Math.cos(angle) * 6 * scale,
        ty: Math.sin(angle) * 6 * scale
      });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  let speechText = "";
  if (showWelcome) {
    speechText = t("robot.messages.welcome");
  } else if (isEmailFocused) {
    speechText = t("robot.messages.email");
  } else if (isPasswordFocused) {
    speechText = isPasswordVisible ? t("robot.messages.visible") : t("robot.messages.security");
  } else if (isFullNameFocused) {
    speechText = t("robot.messages.name");
  }

  const isBadgeInFront = (index: number) => {
    const angleRad = ((orbitAngle + index * (360 / ORBIT_ITEMS.length)) * Math.PI) / 180;
    return Math.sin(angleRad) > 0;
  };

  const renderBadge = (item: (typeof ORBIT_ITEMS)[number], index: number) => {
    const labelKey = {
      Inventory: "robot.orbit.inventory",
      "Social Media": "robot.orbit.social",
      "Auto Reply": "robot.orbit.reply",
      "AI Images": "robot.orbit.images",
      Analytics: "robot.orbit.analytics",
    }[item.label];
    const angleDeg = (orbitAngle + index * (360 / ORBIT_ITEMS.length)) % 360;
    const angleRad = (angleDeg * Math.PI) / 180;
    const radiusX = orbitRadiusX;
    const radiusY = 50;
    const x = Math.cos(angleRad) * radiusX;
    const y = Math.sin(angleRad) * radiusY;
  const scale = Number(((0.85 + (y / radiusY) * 0.15) * orbitItemScale).toFixed(4));
    const opacity = Number((0.5 + (y / radiusY + 1) * 0.25).toFixed(4));

    return (
      <div
        key={item.label}
        className={`absolute px-3.5 py-1.5 rounded-full border text-[11px] font-medium backdrop-blur-md shadow-lg transition-transform ease-linear ${item.color} ${item.glow}`}
        style={{
          transform: `translate3d(${x.toFixed(2)}px, ${(y + 30).toFixed(2)}px, 0px) scale(${scale})`,
          opacity,
          ["--badge-x" as string]: `${x.toFixed(2)}px`,
          ["--badge-y" as string]: `${(y + 30).toFixed(2)}px`,
          ["--badge-scale" as string]: scale,
        }}
      >
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-current animate-ping" />
          <span>{labelKey ? t(labelKey) : item.label}</span>
        </div>
      </div>
    );
  };

  return (
    <div 
      ref={robotRef} 
      className={`relative w-full h-full ${compact ? "min-h-0" : "min-h-[480px] md:min-h-[580px]"} flex items-center justify-center select-none overflow-visible`}
      style={{
        transform: `scale(${visualScale})`,
        perspective: "1000px",
        height: compact ? "100%" : undefined,
        minHeight: compact ? 0 : undefined,
      }}
    >
      {/* Speech Bubble */}
      {speechText && (
        <div 
          className="absolute top-0 left-1/2 -translate-x-1/2 bg-slate-900/90 text-amber-300 text-[12px] font-semibold px-4 py-2 rounded-2xl shadow-2xl border border-amber-500/30 max-w-[260px] text-center backdrop-blur-md z-40 flex items-center gap-2 animate-bounce"
        >
          <span>🤖</span>
          <span className="text-white">{speechText}</span>
        </div>
      )}

      {/* --- 3D ORBITING TAGS --- */}
      {isMounted && showOrbitItems && (
        <>
          <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center" style={{ transformStyle: "preserve-3d" }}>
            {ORBIT_ITEMS.map((item, index) => (!isBadgeInFront(index) ? renderBadge(item, index) : null))}
          </div>
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center" style={{ transformStyle: "preserve-3d" }}>
            {ORBIT_ITEMS.map((item, index) => (isBadgeInFront(index) ? renderBadge(item, index) : null))}
          </div>
        </>
      )}

      {/* --- LARGER & FULLY CENTERED ROBOT SVG --- */}
      <svg 
        viewBox="0 0 400 400" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg" 
        className="w-full h-full max-w-[560px] max-h-[560px] relative z-10"
      >
        <defs>
          <linearGradient id="nexaWhiteBody" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="70%" stopColor="#e2e8f0" />
            <stop offset="100%" stopColor="#cbd5e1" />
          </linearGradient>

          <linearGradient id="yellowJointGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fde047" />
            <stop offset="50%" stopColor="#eab308" />
            <stop offset="100%" stopColor="#ca8a04" />
          </linearGradient>

          <linearGradient id="darkAmoledScreen" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#09090b" />
            <stop offset="100%" stopColor="#18181b" />
          </linearGradient>

          <filter id="yellowGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <filter id="cleanShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="8" stdDeviation="6" floodColor="#000000" floodOpacity="0.35" />
          </filter>
        </defs>

        {/* Torso */}
        <g id="torso-group">
          <rect x="120" y="180" width="160" height="115" rx="54" fill="url(#nexaWhiteBody)" stroke="#cbd5e1" strokeWidth="2" filter="url(#cleanShadow)" />
          <rect x="150" y="205" width="100" height="68" rx="22" fill="url(#darkAmoledScreen)" stroke="#27272a" strokeWidth="2" />
          <circle className="robot-light-pulse" cx="200" cy="239" r="17" fill="none" stroke="#f59e0b" strokeWidth="3.5" filter="url(#yellowGlow)" />
          <circle className="robot-light-pulse" cx="200" cy="239" r="7" fill="#fef08a" filter="url(#yellowGlow)" />

          <g id="arms">
            <g>
              <path d="M 125 205 Q 92 235 80 275" stroke="url(#nexaWhiteBody)" strokeWidth="18" strokeLinecap="round" />
              <circle cx="76" cy="283" r="18" fill="url(#yellowJointGrad)" />
            </g>

            {showRightArm && (
              <g
                style={{
                  transformOrigin: "275px 205px",
                  transformBox: "view-box",
                }}
              >
                <path d="M 275 205 Q 308 235 320 275" stroke="url(#nexaWhiteBody)" strokeWidth="18" strokeLinecap="round" />
                <circle cx="324" cy="283" r="18" fill="url(#yellowJointGrad)" />
              </g>
            )}
          </g>
        </g>

        {/* Head */}
        <g 
          id="head-group"
          style={{
            transform: `translate(${headTransform.tx}px, ${headTransform.ty}px) rotateX(${headTransform.rx}deg) rotateY(${headTransform.ry}deg)`,
            transformOrigin: "200px 160px",
            transition: "transform 0.1s ease-out"
          }}
        >
          <rect x="178" y="160" width="44" height="25" rx="8" fill="#94a3b8" />

          {/* Antenna */}
          <path d="M 200 30 L 200 8" stroke="#cbd5e1" strokeWidth="6" strokeLinecap="round" />
          <circle cx="200" cy="6" r="10" fill="url(#nexaWhiteBody)" stroke="#e2e8f0" strokeWidth="2" />
          <circle cx="200" cy="6" r="4.5" fill="#fef08a" filter="url(#yellowGlow)" />

          {/* Side Ears */}
          <rect x="52" y="75" width="22" height="46" rx="11" fill="url(#yellowJointGrad)" />
          <rect x="326" y="75" width="22" height="46" rx="11" fill="url(#yellowJointGrad)" />

          {/* White Head Outer Shell */}
          <rect x="65" y="18" width="270" height="158" rx="72" fill="url(#nexaWhiteBody)" stroke="#ffffff" strokeWidth="4" />

          {/* Black Screen */}
          <rect x="84" y="30" width="232" height="132" rx="52" fill="url(#darkAmoledScreen)" stroke="#18181b" strokeWidth="2" />

          {/* Glass Reflection */}
          <path d="M 100 43 Q 200 67 300 43 Q 250 55 200 55 Q 150 55 100 43 Z" fill="#ffffff" opacity="0.12" />

          {/* Soft cheeks add a friendlier expression. */}
          <circle cx="112" cy="119" r="9" fill="#f59e0b" opacity="0.16" />
          <circle cx="288" cy="119" r="9" fill="#f59e0b" opacity="0.16" />

          {/* Eyes */}
          <g id="eyes">
            {isBlinking || state === "private" ? (
              <>
                <line className="robot-light-pulse" x1="124" y1="90" x2="168" y2="90" stroke="#f59e0b" strokeWidth="7" strokeLinecap="round" filter="url(#yellowGlow)" />
                <line className="robot-light-pulse" x1="232" y1="90" x2="276" y2="90" stroke="#f59e0b" strokeWidth="7" strokeLinecap="round" filter="url(#yellowGlow)" />
              </>
            ) : state === "wink" ? (
              <>
                <path className="robot-light-pulse" d="M 124 93 Q 146 79 168 93" fill="none" stroke="#f59e0b" strokeWidth="7" strokeLinecap="round" filter="url(#yellowGlow)" />
                <rect className="robot-light-pulse" x="232" y="69" width="40" height="46" rx="17" fill="#f59e0b" filter="url(#yellowGlow)" />
              </>
            ) : (
              <>
                <rect x="124" y="67" width="40" height="50" rx="18" fill="#854d0e" opacity="0.25" />
                <rect className="robot-light-pulse"
                  x={129 + pupilOffset.x} 
                  y={72 + pupilOffset.y} 
                  width="30" 
                  height="40" 
                  rx="15" 
                  fill="#fef08a" 
                  filter="url(#yellowGlow)" 
                />
                <circle cx={134 + pupilOffset.x} cy={77 + pupilOffset.y} r="4" fill="#ffffff" />

                <rect x="236" y="67" width="40" height="50" rx="18" fill="#854d0e" opacity="0.25" />
                <rect className="robot-light-pulse"
                  x={241 + pupilOffset.x} 
                  y={72 + pupilOffset.y} 
                  width="30" 
                  height="40" 
                  rx="15" 
                  fill="#fef08a" 
                  filter="url(#yellowGlow)" 
                />
                <circle cx={246 + pupilOffset.x} cy={77 + pupilOffset.y} r="4" fill="#ffffff" />
              </>
            )}
          </g>

          {/* Smile */}
          <path 
            d="M 150 127 Q 200 157 250 127" 
            fill="none" 
            stroke="#f59e0b" 
            strokeWidth="5.5" 
            strokeLinecap="round" 
            filter="url(#yellowGlow)"
          />
        </g>
      </svg>
    </div>
  );
}