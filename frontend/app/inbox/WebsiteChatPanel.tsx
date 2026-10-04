"use client";

import { useState } from "react";
import { ChevronDown, Copy, Globe, KeyRound } from "lucide-react";
import { Btn, Card, Modal } from "../components/workspace/ui";
import { apiFetch, ApiError } from "../lib/api";
import { API_BASE_URL } from "../lib/config";

interface PublicChatInfo {
  public_key: string;
  enabled: boolean;
}

// Owner ke liye: store ki website par chat widget lagane ka embed code (anjaan visitors, bina login).
export function WebsiteChatPanel({
  storeId,
  toast,
}: {
  storeId: number;
  toast: (k: "ok" | "err", t: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<PublicChatInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const base = `/api/v1/stores/${storeId}/public-chat`;

  const toggleOpen = async () => {
    const next = !open;
    setOpen(next);
    if (next && !info) {
      try {
        setInfo(await apiFetch<PublicChatInfo>(base)); // pehli baar key yahin banti hai
      } catch (e) {
        toast("err", (e as ApiError).message);
      }
    }
  };

  const run = async (fn: () => Promise<PublicChatInfo>, done: string) => {
    setBusy(true);
    try {
      setInfo(await fn());
      toast("ok", done);
    } catch (e) {
      toast("err", (e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const snippet = info
    ? `<script src="${window.location.origin}/chatbot_free/chatbot.js"\n        data-store-key="${info.public_key}"\n        data-api-url="${API_BASE_URL || window.location.origin}" async></script>`
    : "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      toast("ok", "Embed code copied");
    } catch {
      toast("err", "Could not copy — select the code and copy it manually.");
    }
  };

  return (
    <Card className="mb-4">
      <button
        onClick={toggleOpen}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Globe className="h-4 w-4 text-amber-300" />
          Website chat widget
          <span className="hidden text-xs font-normal text-slate-400 sm:inline">
            — let visitors on your own website chat with the bot, no login
          </span>
        </span>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="space-y-3 border-t border-white/10 px-4 py-4">
          {!info ? (
            <p className="text-sm text-slate-400">Loading…</p>
          ) : (
            <>
              <p className="text-xs text-slate-400">
                Paste this on any page of your store website. Visitors stay anonymous, can only ask questions, see price,
                stock and policies, and see their own chat. Order lookups and purchases are handed to you in this inbox.
              </p>
              <pre className="overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-3 text-xs text-slate-200">
                {snippet}
              </pre>
              <div className="flex flex-wrap items-center gap-2">
                <Btn onClick={copy} variant="ghost">
                  <Copy className="h-4 w-4" /> Copy code
                </Btn>
                <Btn
                  variant={info.enabled ? "ghost" : "primary"}
                  loading={busy}
                  onClick={() =>
                    run(
                      () => apiFetch<PublicChatInfo>(base, { method: "PUT", body: { enabled: !info.enabled } }),
                      info.enabled ? "Website chat turned off" : "Website chat turned on"
                    )
                  }
                >
                  {info.enabled ? "Turn off" : "Turn on"}
                </Btn>
                <Btn variant="danger" disabled={busy} onClick={() => setConfirmRotate(true)}>
                  <KeyRound className="h-4 w-4" /> Rotate key
                </Btn>
                <span className={`text-xs ${info.enabled ? "text-emerald-300" : "text-amber-300"}`}>
                  {info.enabled ? "Live" : "Off — visitors get no answer"}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {confirmRotate && (
        <Modal title="Rotate the public key?" onClose={() => setConfirmRotate(false)}>
          <p className="text-sm text-slate-300">
            The current key stops working immediately. Widgets already installed on your website will show no
            answers until you paste the new code. Visitors&apos; open chats continue with the new key.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Btn variant="ghost" onClick={() => setConfirmRotate(false)}>
              Cancel
            </Btn>
            <Btn
              variant="danger"
              onClick={() => {
                setConfirmRotate(false);
                run(() => apiFetch<PublicChatInfo>(`${base}/rotate`, { method: "POST" }), "New key created — update your website");
              }}
            >
              Rotate
            </Btn>
          </div>
        </Modal>
      )}
    </Card>
  );
}
