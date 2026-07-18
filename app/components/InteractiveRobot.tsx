"use client";

import React, { useState, useEffect, useRef } from "react";

interface RobotProps {
  isEmailFocused: boolean;
  isPasswordFocused: boolean;
  isPasswordVisible: boolean;
  isFullNameFocused?: boolean;
}

export function InteractiveRobot({ 
  isEmailFocused, 
  isPasswordFocused, 
  isPasswordVisible, 
  isFullNameFocused = false 
}: RobotProps) {
  const robotRef = useRef<HTMLDivElement>(null);
  const [pupilOffset, setPupilOffset] = useState({ x: 0, y: 0 });
  const [isBlinking, setIsBlinking] = useState(false);

  let state: "private" | "wink" | "surprised" | "idle" = "idle";
  
  if (isPasswordFocused) {
    if (isPasswordVisible) {
      state = "private";
    } else {
      state = "wink";
    }
  } else if (isEmailFocused) {
    state = "surprised";
  }

  useEffect(() => {
    const interval = setInterval(() => {
      if (state === "idle") {
        setIsBlinking(true);
        setTimeout(() => setIsBlinking(false), 150);
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
      const maxOffset = 6;
      const scale = Math.min(distance / 150, 1);
      
      setPupilOffset({
        x: Math.cos(angle) * maxOffset * scale,
        y: Math.sin(angle) * maxOffset * scale
      });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  let speechText = "";
  if (isEmailFocused) {
    speechText = "I see your email! 👀";
  } else if (isPasswordFocused) {
    if (isPasswordVisible) {
      speechText = "Oh, you made it visible! 🙈 Hands over my eyes, no peeking!";
    } else {
      speechText = "Security first! 🔒 Your password is safely masked. I am watching out!";
    }
  } else if (isFullNameFocused) {
    speechText = "That's an amazing name! ✨ Let's launch your container!";
  }

  return (
    <div 
      ref={robotRef} 
      id="interactive-robot-container" 
      className="relative w-full max-w-[340px] md:max-w-[400px] aspect-square mx-auto flex flex-col items-center justify-center select-none"
    >
      {speechText && (
        <div 
          id="robot-speech-bubble"
          className="absolute -top-10 md:-top-12 left-1/2 -translate-x-1/2 bg-violet-950 text-white text-[11px] font-bold px-4 py-2.5 rounded-2xl shadow-xl border border-violet-500/20 max-w-[260px] text-center whitespace-normal pointer-events-none z-30 flex items-center gap-2 animate-float transition-all duration-300"
        >
          <span className="shrink-0 text-violet-300">🤖</span>
          <span>{speechText}</span>
          <div className="absolute bottom-[-5px] left-1/2 -translate-x-1/2 w-2.5 h-2.5 bg-violet-950 rotate-45 border-r border-b border-violet-500/20" />
        </div>
      )}

      <div 
        className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[240px] h-[30px] rounded-full bg-violet-400/25 blur-xl animate-pulse-shadow" 
        style={{ transformOrigin: "center" }}
      />
      
      <svg 
        viewBox="0 0 400 400" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg" 
        className="w-full h-full animate-float relative z-10"
      >
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          
          <filter id="bezelGlow" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#8b5cf6" floodOpacity="0.4" />
          </filter>

          <filter id="softShadow" x="-10%" y="-10%" width="125%" height="125%">
            <feDropShadow dx="0" dy="12" stdDeviation="10" floodColor="#581c87" floodOpacity="0.15" />
          </filter>

          <linearGradient id="headCaseGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="50%" stopColor="#f8f6fc" />
            <stop offset="100%" stopColor="#e9e3f8" />
          </linearGradient>

          <linearGradient id="bezelGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#c084fc" />
            <stop offset="50%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#7c3aed" />
          </linearGradient>

          <linearGradient id="screenGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#110d29" />
            <stop offset="50%" stopColor="#090514" />
            <stop offset="100%" stopColor="#000000" />
          </linearGradient>

          <linearGradient id="accentGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#d8b4fe" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>

          <linearGradient id="metalJointGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#e2e8f0" />
            <stop offset="100%" stopColor="#94a3b8" />
          </linearGradient>
        </defs>

        {/* ROBOT BODY */}
        <rect x="175" y="255" width="50" height="30" rx="8" fill="url(#metalJointGrad)" />
        <ellipse cx="200" cy="275" rx="20" ry="8" fill="#7c3aed" opacity="0.4" />

        {/* Torso/Chest */}
        <path 
          d="M 120 280 L 280 280 Q 290 340 250 375 L 150 375 Q 110 340 120 280 Z" 
          fill="url(#headCaseGrad)" 
          filter="url(#softShadow)" 
        />
        {/* Core Heart / Central Digital Sensor */}
        <circle cx="200" cy="325" r="22" fill="#110d29" stroke="url(#accentGrad)" strokeWidth="2" />
        <circle cx="200" cy="325" r="14" fill="#8b5cf6" className="animate-pulse opacity-80" />
        <circle cx="200" cy="325" r="6" fill="#22d3ee" className="glow-cyan" />

        {/* ROBOT HEAD */}
        {/* Left Ear Antenna */}
        <g id="left-ear">
          <rect x="62" y="145" width="18" height="60" rx="9" fill="url(#accentGrad)" filter="url(#softShadow)" />
          <circle cx="71" cy="175" r="5" fill="#22d3ee" className="glow-cyan" />
          <path d="M 71 145 L 71 130" stroke="#8b5cf6" strokeWidth="3" strokeLinecap="round" />
          <circle cx="71" cy="130" r="3" fill="#22d3ee" className="glow-cyan" />
        </g>

        {/* Right Ear Antenna */}
        <g id="right-ear">
          <rect x="320" y="145" width="18" height="60" rx="9" fill="url(#accentGrad)" filter="url(#softShadow)" />
          <circle cx="329" cy="175" r="5" fill="#22d3ee" className="glow-cyan" />
          <path d="M 329 145 L 329 130" stroke="#8b5cf6" strokeWidth="3" strokeLinecap="round" />
          <circle cx="329" cy="130" r="3" fill="#22d3ee" className="glow-cyan" />
        </g>

        {/* Main white head housing */}
        <rect 
          x="80" 
          y="90" 
          width="240" 
          height="170" 
          rx="60" 
          ry="60" 
          fill="url(#headCaseGrad)" 
          stroke="#f3e8ff" 
          strokeWidth="3" 
          filter="url(#softShadow)" 
        />

        {/* Outer Purple Bezel Ring */}
        <rect 
          x="95" 
          y="105" 
          width="210" 
          height="140" 
          rx="45" 
          ry="45" 
          fill="url(#bezelGrad)" 
          filter="url(#bezelGlow)" 
        />

        {/* Digital AMOLED Screen */}
        <rect 
          x="105" 
          y="115" 
          width="190" 
          height="120" 
          rx="35" 
          ry="35" 
          fill="url(#screenGrad)" 
        />

        {/* Gloss glass reflection */}
        <path 
          d="M 115 145 Q 200 120 285 145 Q 275 125 245 120 L 145 120 Q 125 125 115 145 Z" 
          fill="#ffffff" 
          opacity="0.08" 
        />

        {/* DYNAMIC ROBOT FACE EXPRESSIONS */}
        
        {/* IDLE STATE */}
        <g id="expr-idle" className={`transition-opacity duration-300 ${state === "idle" ? "opacity-100" : "opacity-0"}`}>
          {isBlinking ? (
            <>
              <line x1="135" y1="176" x2="171" y2="176" stroke="#22d3ee" strokeWidth="7" strokeLinecap="round" className="glow-cyan" />
              <line x1="229" y1="176" x2="265" y2="176" stroke="#22d3ee" strokeWidth="7" strokeLinecap="round" className="glow-cyan" />
            </>
          ) : (
            <>
              <rect x="135" y="152" width="36" height="48" rx="18" fill="rgba(34, 211, 238, 0.15)" stroke="#22d3ee" strokeWidth="2.5" className="glow-cyan" />
              <ellipse cx={153 + pupilOffset.x} cy={176 + pupilOffset.y} rx="9" ry="12" fill="#22d3ee" className="glow-cyan" />
              <circle cx={150 + pupilOffset.x} cy={171 + pupilOffset.y} r="3" fill="#ffffff" />

              <rect x="229" y="152" width="36" height="48" rx="18" fill="rgba(34, 211, 238, 0.15)" stroke="#22d3ee" strokeWidth="2.5" className="glow-cyan" />
              <ellipse cx={247 + pupilOffset.x} cy={176 + pupilOffset.y} rx="9" ry="12" fill="#22d3ee" className="glow-cyan" />
              <circle cx={244 + pupilOffset.x} cy={171 + pupilOffset.y} r="3" fill="#ffffff" />
            </>
          )}

          <path 
            d="M 185 208 Q 200 226 215 208" 
            fill="none" 
            stroke="#22d3ee" 
            strokeWidth="5" 
            strokeLinecap="round" 
            className="glow-cyan" 
          />
        </g>

        {/* SURPRISED STATE */}
        <g id="expr-surprised" className={`transition-opacity duration-300 ${state === "surprised" ? "opacity-100" : "opacity-0"}`}>
          <circle cx="153" cy="176" r="22" fill="rgba(34, 211, 238, 0.2)" stroke="#22d3ee" strokeWidth="3" className="glow-cyan" />
          <circle cx={153 + pupilOffset.x * 0.5} cy={176 + pupilOffset.y * 0.5} r="12" fill="#22d3ee" className="glow-cyan" />
          <circle cx={149 + pupilOffset.x * 0.5} cy={172 + pupilOffset.y * 0.5} r="4" fill="#ffffff" />
          
          <circle cx="247" cy="176" r="22" fill="rgba(34, 211, 238, 0.2)" stroke="#22d3ee" strokeWidth="3" className="glow-cyan" />
          <circle cx={247 + pupilOffset.x * 0.5} cy={176 + pupilOffset.y * 0.5} r="12" fill="#22d3ee" className="glow-cyan" />
          <circle cx={243 + pupilOffset.x * 0.5} cy={172 + pupilOffset.y * 0.5} r="4" fill="#ffffff" />
          
          <ellipse 
            cx="200" cy="212" 
            rx="9" ry="14" 
            fill="none" 
            stroke="#22d3ee" 
            strokeWidth="5" 
            className="glow-cyan" 
          />
        </g>

        {/* PRIVATE STATE */}
        <g id="expr-private" className={`transition-opacity duration-300 ${state === "private" ? "opacity-100" : "opacity-0"}`}>
          <line x1="135" y1="176" x2="171" y2="176" stroke="#22d3ee" strokeWidth="7" strokeLinecap="round" className="glow-cyan" />
          <line x1="229" y1="176" x2="265" y2="176" stroke="#22d3ee" strokeWidth="7" strokeLinecap="round" className="glow-cyan" />
          <line x1="190" y1="210" x2="210" y2="210" stroke="#22d3ee" strokeWidth="6" strokeLinecap="round" className="glow-cyan" />
        </g>

        {/* WINK STATE */}
        <g id="expr-wink" className={`transition-opacity duration-300 ${state === "wink" ? "opacity-100" : "opacity-0"}`}>
          <path 
            d="M 135 180 Q 153 160 171 180" 
            fill="none" 
            stroke="#22d3ee" 
            strokeWidth="7" 
            strokeLinecap="round" 
            className="glow-cyan" 
          />
          
          <rect x="229" y="152" width="36" height="48" rx="18" fill="rgba(34, 211, 238, 0.15)" stroke="#22d3ee" strokeWidth="2.5" className="glow-cyan" />
          <ellipse cx={247 + pupilOffset.x} cy={176 + pupilOffset.y} rx="9" ry="12" fill="#22d3ee" className="glow-cyan" />
          <circle cx={244 + pupilOffset.x} cy={171 + pupilOffset.y} r="3" fill="#ffffff" />

          <path 
            d="M 188 206 Q 206 224 218 204" 
            fill="none" 
            stroke="#22d3ee" 
            strokeWidth="5" 
            strokeLinecap="round" 
            className="glow-cyan" 
          />
        </g>

        {/* INTERACTIVE ROBOT ARMS */}
        {/* Left shoulder & arm */}
        <g id="left-arm" className="transition-all duration-500">
          <circle cx="105" cy="295" r="16" fill="url(#accentGrad)" />
          {state === "private" ? (
            <>
              <path d="M 105 295 Q 60 190 145 176" stroke="url(#headCaseGrad)" strokeWidth="22" strokeLinecap="round" filter="url(#softShadow)" />
              <path d="M 105 295 Q 60 190 145 176" stroke="url(#bezelGrad)" strokeWidth="18" strokeLinecap="round" />
              <g id="left-hand-private" className="animate-pulse">
                <rect x="131" y="152" width="44" height="48" rx="16" fill="url(#accentGrad)" stroke="#7c3aed" strokeWidth="3" filter="url(#softShadow)" />
                <rect x="137" y="160" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
                <rect x="137" y="172" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
                <rect x="137" y="184" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
              </g>
            </>
          ) : (
            <>
              <path d="M 105 295 Q 65 315 80 345" stroke="url(#headCaseGrad)" strokeWidth="18" strokeLinecap="round" filter="url(#softShadow)" />
              <circle cx="80" cy="345" r="10" fill="url(#accentGrad)" />
              <path d="M 80 345 L 64 348 M 80 345 L 66 338" stroke="#7c3aed" strokeWidth="4" strokeLinecap="round" />
            </>
          )}
        </g>

        {/* Right shoulder & arm */}
        <g id="right-arm" className="transition-all duration-500">
          <circle cx="295" cy="295" r="16" fill="url(#accentGrad)" />
          {state === "private" ? (
            <>
              <path d="M 295 295 Q 340 190 255 176" stroke="url(#headCaseGrad)" strokeWidth="22" strokeLinecap="round" filter="url(#softShadow)" />
              <path d="M 295 295 Q 340 190 255 176" stroke="url(#bezelGrad)" strokeWidth="18" strokeLinecap="round" />
              <g id="right-hand-private" className="animate-pulse">
                <rect x="225" y="152" width="44" height="48" rx="16" fill="url(#accentGrad)" stroke="#7c3aed" strokeWidth="3" filter="url(#softShadow)" />
                <rect x="231" y="160" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
                <rect x="231" y="172" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
                <rect x="231" y="184" width="32" height="6" rx="3" fill="#ffffff" opacity="0.4" />
              </g>
            </>
          ) : state === "wink" ? (
            <>
              <path d="M 295 295 Q 310 230 215 220" stroke="url(#headCaseGrad)" strokeWidth="18" strokeLinecap="round" filter="url(#softShadow)" />
              <path d="M 295 295 Q 310 230 215 220" stroke="url(#bezelGrad)" strokeWidth="14" strokeLinecap="round" />
              <circle cx="215" cy="220" r="11" fill="url(#accentGrad)" filter="url(#softShadow)" />
              <path d="M 215 220 L 215 204" stroke="#7c3aed" strokeWidth="5.5" strokeLinecap="round" />
              <path d="M 215 220 Q 223 222 221 216" stroke="#7c3aed" strokeWidth="3.5" strokeLinecap="round" />
            </>
          ) : (
            <>
              <path d="M 295 295 Q 335 315 320 345" stroke="url(#headCaseGrad)" strokeWidth="18" strokeLinecap="round" filter="url(#softShadow)" />
              <circle cx="320" cy="345" r="10" fill="url(#accentGrad)" />
              <path d="M 320 345 L 336 348 M 320 345 L 334 338" stroke="#7c3aed" strokeWidth="4" strokeLinecap="round" />
            </>
          )}
        </g>

      </svg>
    </div>
  );
}
