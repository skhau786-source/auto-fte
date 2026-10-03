"use client";

import { useEffect, useRef, useState } from "react";
import { buildApiUrl } from "../lib/config";

type Turn = { role: "customer" | "bot"; text: string; lang?: string };

const CONTACT_RE = /^(\+?\d[\d\s-]{7,}|[^\s@]+@[^\s@]+\.[^\s@]+)$/;

const SUGGESTIONS = [
  "What is the price of the canvas backpack?",
  "Wool beanie kitne bache hain?",
  "Where is my order 1234?",
  "Owner se baat karni hai",
];

function getSessionId(): string {
  const fallback = `s-${Math.random().toString(36).slice(2, 12)}`;
  try {
    const k = "fte_support_session";
    const existing = window.localStorage.getItem(k);
    if (existing) return existing;
    window.localStorage.setItem(k, fallback);
  } catch {
    /* storage unavailable (private mode) - session lives for this page only */
  }
  return fallback;
}

export default function SupportChatWidget({
  storeId,
  storeName = "Support",
  startOpen = false,
}: {
  storeId: string;
  storeName?: string;
  startOpen?: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  const [turns, setTurns] = useState<Turn[]>([
    { role: "bot", text: "Hello! Assalam o alaikum! Ask about a product's price or stock, an order, or say \"talk to the owner\". / Price, stock ya order status poochein." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [handoffId, setHandoffId] = useState<string | null>(null);
  const sessionId = useRef<string>("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionId.current = getSessionId();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, open, busy]);

  async function send(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    setInput("");
    const next: Turn[] = [...turns, { role: "customer", text }];
    setTurns(next);
    setBusy(true);

    try {
      // A phone/email right after a handoff is saved on that request.
      if (handoffId && CONTACT_RE.test(text)) {
        const r = await fetch(buildApiUrl("/support-chat/handoff-contact"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ handoff_id: handoffId, session_id: sessionId.current, contact: text }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setHandoffId(null);
        setTurns([...next, { role: "bot", text: "Thank you! The owner will contact you on this. / Shukriya! Owner is par aap se rabta karenge." }]);
        return;
      }

      const res = await fetch(buildApiUrl("/support-chat/message"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          store_id: storeId,
          session_id: sessionId.current,
          message: text,
          history: next.slice(-11, -1).map((t) => ({ role: t.role, text: t.text.slice(0, 1000), lang: t.lang })),
        }),
      });
      if (!res.ok) throw new Error(res.status === 404 ? "store" : `HTTP ${res.status}`);
      const data = await res.json();
      if (data.handoff_id) setHandoffId(data.handoff_id);
      setTurns([...next, { role: "bot", text: data.reply, lang: data.language }]);
    } catch (e) {
      const msg =
        e instanceof Error && e.message === "store"
          ? "This chat link is not valid (store not found)."
          : "Sorry, I couldn't reach the shop right now. Please try again. / Maaf kijiye, abhi connection nahi hua.";
      setTurns([...next, { role: "bot", text: msg }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-3 font-sans">
      {open && (
        <div
          role="dialog"
          aria-label={`${storeName} chat`}
          className="flex h-[32rem] max-h-[80vh] w-[22rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        >
          <div className="flex items-center justify-between bg-violet-600 px-4 py-3 text-white">
            <div>
              <p className="text-sm font-semibold">{storeName}</p>
              <p className="text-xs text-violet-100">English &amp; Roman Urdu</p>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close chat" className="rounded p-1 text-xl leading-none hover:bg-violet-500">
              ×
            </button>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto bg-slate-50 p-3" aria-live="polite">
            {turns.map((t, i) => (
              <div key={i} className={`flex ${t.role === "customer" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                    t.role === "customer" ? "bg-violet-600 text-white" : "border border-slate-200 bg-white text-slate-800"
                  }`}
                >
                  {t.text}
                </div>
              </div>
            ))}
            {busy && <div className="text-xs text-slate-400">typing…</div>}
            {turns.length <= 1 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-violet-200 bg-white px-3 py-1 text-xs text-violet-700 hover:bg-violet-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex gap-2 border-t border-slate-200 bg-white p-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Type your message…"
              aria-label="Message"
              className="min-w-0 flex-1 rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-900 outline-none focus:border-violet-500"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="rounded-full bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close chat" : "Open chat"}
        className="flex h-14 w-14 items-center justify-center rounded-full bg-violet-600 text-2xl text-white shadow-lg hover:bg-violet-500"
      >
        {open ? "×" : "💬"}
      </button>
    </div>
  );
}
