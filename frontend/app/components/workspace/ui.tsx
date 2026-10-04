"use client";

// Small shared UI pieces for the workspace pages (dark + amber theme).

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

export function Card({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur ${className}`}>
      {children}
    </div>
  );
}

export function SectionTitle({
  title,
  hint,
  right,
}: {
  title: string;
  hint?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 mb-3">
      <div>
        <h2 className="text-base font-semibold text-slate-100">{title}</h2>
        {hint && <p className="text-xs text-slate-400 mt-0.5">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

export function Stat({
  label,
  value,
  tone = "default",
  sub,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "warn" | "bad" | "good";
  sub?: string;
}) {
  const color = {
    default: "text-slate-100",
    warn: "text-amber-300",
    bad: "text-rose-300",
    good: "text-emerald-300",
  }[tone];
  return (
    <Card className="p-4">
      <p className="text-[11px] uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </Card>
  );
}

const BADGE_TONES: Record<string, string> = {
  active: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  committed: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  released: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  expired: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  cancelled: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  in_stock: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  low_stock: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  out_of_stock: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  default: "bg-white/5 text-slate-300 border-white/10",
};

export function Badge({ children, tone }: { children: React.ReactNode; tone?: string }) {
  const cls = BADGE_TONES[tone || "default"] || BADGE_TONES.default;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

export function Btn({
  children,
  onClick,
  variant = "primary",
  disabled,
  loading,
  type = "button",
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  loading?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const styles = {
    primary: "bg-amber-400 text-slate-900 hover:bg-amber-300",
    ghost: "border border-white/15 text-slate-200 hover:bg-white/10",
    danger: "border border-rose-500/40 text-rose-300 hover:bg-rose-500/10",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export const inputCls =
  "w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-amber-400/60";

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  // Portal: Card ka backdrop-filter fixed positioning ko apne andar rok leta hai.
  if (typeof document === "undefined") return null;
  return createPortal(
    <div
      className="fixed inset-0 z-50 text-slate-100 flex items-center justify-center bg-black/70 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0a1226] p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-100">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}

export function Empty({ icon, title, text }: { icon?: React.ReactNode; title: string; text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      {icon && <div className="mb-2 text-slate-500">{icon}</div>}
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {text && <p className="mt-1 max-w-sm text-xs text-slate-500">{text}</p>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

// ─── Toasts ───────────────────────────────────────────────────

interface ToastItem {
  id: number;
  kind: "ok" | "err";
  text: string;
}

export function useToasts() {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((kind: "ok" | "err", text: string) => {
    const id = Date.now() + Math.random();
    setItems((cur) => [...cur, { id, kind, text }]);
    setTimeout(() => setItems((cur) => cur.filter((t) => t.id !== id)), 4500);
  }, []);

  const node = (
    <div className="fixed bottom-4 left-4 z-[60] flex flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`flex max-w-sm items-start gap-2 rounded-xl border px-3 py-2 text-sm shadow-lg ${
            t.kind === "ok"
              ? "border-emerald-500/30 bg-emerald-950/90 text-emerald-200"
              : "border-rose-500/30 bg-rose-950/90 text-rose-200"
          }`}
        >
          {t.kind === "ok" ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );

  return { toast: push, toastNode: node };
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtMoney(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
