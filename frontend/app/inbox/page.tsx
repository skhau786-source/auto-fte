"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Bot, CheckCircle2, Inbox as InboxIcon, RotateCcw, Send, Store as StoreIcon, UserRound } from "lucide-react";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { Badge, Btn, Card, Empty, Spinner, fmtDate, inputCls, useToasts } from "../components/workspace/ui";
import {
  apiFetch, ApiError, ConversationStatus, InboxItem, InboxList, InboxThread, Store, ThreadMessage,
} from "../lib/api";

const POLL_MS = 15000;
const MAX_REPLY = 4000;

const TABS: { id: ConversationStatus; label: string }[] = [
  { id: "handoff", label: "Needs you" },
  { id: "open", label: "With bot" },
  { id: "closed", label: "Resolved" },
];

export default function InboxPage() {
  return (
    <WorkspaceShell
      title="Support Inbox"
      subtitle="Customer chats the bot handed over to you. Reply, resolve, or hand them back to the bot."
    >
      <InboxWorkspace />
    </WorkspaceShell>
  );
}

function InboxWorkspace() {
  const { toast, toastNode } = useToasts();
  const [stores, setStores] = useState<Store[] | null>(null);
  const [storeId, setStoreId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Store[]>("/api/v1/stores")
      .then((list) => {
        setStores(list);
        if (list.length) setStoreId(list[0].id);
      })
      .catch((e: ApiError) =>
        setError(e.status === 401 ? "Your session expired. Please log in again." : e.message)
      );
  }, []);

  if (error) {
    return (
      <Card className="p-6">
        <Empty title="Could not load the inbox" text={error} />
      </Card>
    );
  }
  if (stores === null) return <Spinner label="Loading your stores…" />;
  if (stores.length === 0 || storeId === null) {
    return (
      <Card className="p-6">
        <Empty
          icon={<StoreIcon className="h-8 w-8" />}
          title="No store connected yet"
          text="Connect a store first. Customer chats for that store will show up here."
        />
      </Card>
    );
  }

  return (
    <>
      {stores.length > 1 && (
        <div className="mb-3">
          <select
            aria-label="Store"
            value={storeId}
            onChange={(e) => setStoreId(Number(e.target.value))}
            className={`${inputCls} !w-auto`}
          >
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || `Store ${s.id}`} ({s.platform})
              </option>
            ))}
          </select>
        </div>
      )}
      <InboxPanes key={storeId} storeId={storeId} toast={toast} />
      {toastNode}
    </>
  );
}

// ─── Two panes: list + thread ────────────────────────────────

function InboxPanes({
  storeId,
  toast,
}: {
  storeId: number;
  toast: (k: "ok" | "err", t: string) => void;
}) {
  const [tab, setTab] = useState<ConversationStatus>("handoff");
  const [list, setList] = useState<InboxList | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [thread, setThread] = useState<InboxThread | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const base = `/api/v1/stores/${storeId}/inbox`;

  const loadList = useCallback(async () => {
    try {
      setList(await apiFetch<InboxList>(`${base}?status=${tab}&page_size=50`));
    } catch (e) {
      toast("err", (e as ApiError).message);
    }
  }, [base, tab, toast]);

  const loadThread = useCallback(
    async (id: number, showSpinner = false) => {
      if (showSpinner) setThreadLoading(true);
      try {
        setThread(await apiFetch<InboxThread>(`${base}/${id}`));
      } catch (e) {
        toast("err", (e as ApiError).message);
      } finally {
        setThreadLoading(false);
      }
    },
    [base, toast]
  );

  // List: tab badalne par aur har POLL_MS par
  useEffect(() => {
    loadList();
    const t = setInterval(loadList, POLL_MS);
    return () => clearInterval(t);
  }, [loadList]);

  // Thread: select hone par aur har POLL_MS par (naye customer messages ke liye)
  useEffect(() => {
    if (selectedId === null) {
      setThread(null);
      return;
    }
    setThread(null);
    loadThread(selectedId, true);
    const t = setInterval(() => loadThread(selectedId), POLL_MS);
    return () => clearInterval(t);
  }, [selectedId, loadThread]);

  const afterChange = useCallback(() => {
    loadList();
    if (selectedId !== null) loadThread(selectedId);
  }, [loadList, loadThread, selectedId]);

  const counts = list?.counts;

  return (
    <div className="grid gap-4 md:grid-cols-[340px_1fr]">
      {/* ── List ── */}
      <Card className={`flex h-[calc(100vh-260px)] min-h-[420px] flex-col p-3 ${selectedId !== null ? "hidden md:flex" : "flex"}`}>
        <div className="mb-3 flex gap-1 rounded-xl border border-white/10 bg-black/20 p-1" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => {
                setTab(t.id);
                setSelectedId(null);
              }}
              className={`flex flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-lg px-1.5 py-1.5 text-xs font-medium transition-colors ${
                tab === t.id ? "bg-amber-400 text-slate-900" : "text-slate-300 hover:bg-white/5"
              }`}
            >
              {t.label}
              {counts && counts[t.id] > 0 && (
                <span
                  className={`rounded-full px-1.5 text-[10px] font-bold ${
                    tab === t.id ? "bg-slate-900/20" : t.id === "handoff" ? "bg-rose-500 text-white" : "bg-white/10"
                  }`}
                >
                  {counts[t.id]}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="-mr-1 flex-1 overflow-y-auto pr-1">
          {list === null ? (
            <Spinner />
          ) : list.items.length === 0 ? (
            <Empty
              icon={<InboxIcon className="h-8 w-8" />}
              title={tab === "handoff" ? "Nothing needs you" : tab === "open" ? "No chats with the bot" : "No resolved chats"}
              text={tab === "handoff" ? "When the bot escalates a chat, it will appear here." : undefined}
            />
          ) : (
            <ul className="space-y-1">
              {list.items.map((c) => (
                <ConversationRow key={c.id} item={c} active={c.id === selectedId} onClick={() => setSelectedId(c.id)} />
              ))}
            </ul>
          )}
        </div>
      </Card>

      {/* ── Thread ── */}
      <Card className={`h-[calc(100vh-260px)] min-h-[420px] flex-col ${selectedId === null ? "hidden md:flex" : "flex"}`}>
        {selectedId === null ? (
          <div className="flex flex-1 items-center justify-center">
            <Empty icon={<InboxIcon className="h-9 w-9" />} title="Select a conversation" text="Pick a chat on the left to read it and reply." />
          </div>
        ) : threadLoading || !thread ? (
          <Spinner />
        ) : (
          <ThreadView
            key={thread.id}
            storeId={storeId}
            thread={thread}
            toast={toast}
            onBack={() => setSelectedId(null)}
            onChanged={afterChange}
          />
        )}
      </Card>
    </div>
  );
}

function ConversationRow({ item, active, onClick }: { item: InboxItem; active: boolean; onClick: () => void }) {
  return (
    <li>
      <button
        onClick={onClick}
        aria-current={active}
        className={`w-full rounded-xl px-3 py-2.5 text-left transition-colors ${active ? "bg-amber-400/15" : "hover:bg-white/5"}`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5">
            {item.awaiting_reply && <span className="h-2 w-2 shrink-0 rounded-full bg-rose-400" title="Waiting for your reply" />}
            <span className="truncate text-sm font-semibold">{item.customer_email}</span>
          </span>
          <span className="shrink-0 text-[11px] text-slate-500">{fmtDate(item.last_activity)}</span>
        </div>
        <p className="mt-0.5 truncate text-xs text-slate-400">
          {item.last_role === "agent_human" && "You: "}
          {item.last_role === "agent_bot" && "Bot: "}
          {item.last_message || "No messages"}
        </p>
        {item.handoff_reason && item.status === "handoff" && (
          <p className="mt-0.5 truncate text-[11px] text-amber-300/80">{friendlyReason(item.handoff_reason)}</p>
        )}
      </button>
    </li>
  );
}

// "Out of scope keyword in: 'text'" → Customer said: "text"
function friendlyReason(reason: string): string {
  const m = reason.match(/Out of scope keyword in:\s*'([\s\S]*)'\s*$/);
  if (m) return `Customer said: "${m[1]}"`;
  return reason;
}

const STATUS_TONE: Record<ConversationStatus, string> = { handoff: "expired", open: "active", closed: "released" };
const STATUS_LABEL: Record<ConversationStatus, string> = { handoff: "Needs you", open: "With bot", closed: "Resolved" };

function ThreadView({
  storeId,
  thread,
  toast,
  onBack,
  onChanged,
}: {
  storeId: number;
  thread: InboxThread;
  toast: (k: "ok" | "err", t: string) => void;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [acting, setActing] = useState<ConversationStatus | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const base = `/api/v1/stores/${storeId}/inbox/${thread.id}`;
  const closed = thread.status === "closed";
  const lastMessageId = thread.messages[thread.messages.length - 1]?.id;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [lastMessageId]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending || closed) return;
    setSending(true);
    try {
      await apiFetch(`${base}/reply`, { method: "POST", body: { text } });
      setDraft("");
      toast("ok", "Reply sent");
      onChanged();
    } catch (e) {
      toast("err", (e as ApiError).message);
    } finally {
      setSending(false);
    }
  };

  const setStatus = async (status: ConversationStatus, done: string) => {
    setActing(status);
    try {
      await apiFetch(`${base}/status`, { method: "POST", body: { status } });
      toast("ok", done);
      onChanged();
    } catch (e) {
      toast("err", (e as ApiError).message);
    } finally {
      setActing(null);
    }
  };

  const reason = thread.handoffs[0]?.reason;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 p-3">
        <div className="flex min-w-0 items-center gap-2">
          <button onClick={onBack} aria-label="Back to list" className="rounded-lg p-1.5 text-slate-300 hover:bg-white/10 md:hidden">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{thread.customer_email}</p>
            <p className="text-[11px] text-slate-500">Started {fmtDate(thread.created_at)}</p>
          </div>
          <Badge tone={STATUS_TONE[thread.status]}>{STATUS_LABEL[thread.status]}</Badge>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {thread.status === "open" && (
            <Btn variant="ghost" loading={acting === "handoff"} onClick={() => setStatus("handoff", "You took over this chat")}>
              <UserRound className="h-4 w-4" /> Take over
            </Btn>
          )}
          {thread.status === "handoff" && (
            <Btn variant="ghost" loading={acting === "open"} onClick={() => setStatus("open", "Handed back to the bot")}>
              <Bot className="h-4 w-4" /> Hand back to bot
            </Btn>
          )}
          {!closed && (
            <Btn loading={acting === "closed"} onClick={() => setStatus("closed", "Conversation resolved")}>
              <CheckCircle2 className="h-4 w-4" /> Resolve
            </Btn>
          )}
          {closed && (
            <Btn variant="ghost" loading={acting === "handoff"} onClick={() => setStatus("handoff", "Conversation reopened")}>
              <RotateCcw className="h-4 w-4" /> Reopen
            </Btn>
          )}
        </div>
      </div>

      {reason && thread.status === "handoff" && (
        <div className="border-b border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
          <span className="font-semibold">Why it was escalated: </span>
          {friendlyReason(reason)}
        </div>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {thread.messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-white/10 p-3">
        {closed ? (
          <p className="text-center text-xs text-slate-500">This conversation is resolved. Reopen it to reply.</p>
        ) : (
          <>
            <textarea
              className={`${inputCls} min-h-[72px] resize-y`}
              placeholder="Write a reply to the customer…  (Ctrl+Enter to send)"
              value={draft}
              maxLength={MAX_REPLY}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  send();
                }
              }}
              aria-label="Reply"
            />
            {/* Send left mein: global chatbot widget neeche-right corner dhakta hai */}
            <div className="mt-2 flex items-center gap-3">
              <Btn onClick={send} loading={sending} disabled={!draft.trim()}>
                <Send className="h-4 w-4" /> Send reply
              </Btn>
              <span className="text-[11px] text-slate-500">
                {thread.status === "open"
                  ? "Replying takes the chat over from the bot."
                  : `${draft.length}/${MAX_REPLY}`}
              </span>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Bubble({ message }: { message: ThreadMessage }) {
  const mine = message.role === "agent_human";
  const bot = message.role === "agent_bot";
  const who = mine ? "You" : bot ? "Bot" : "Customer";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[80%]">
        <p className={`mb-0.5 text-[10px] uppercase tracking-wider text-slate-500 ${mine ? "text-right" : ""}`}>
          {who} · {fmtDate(message.created_at)}
        </p>
        <div
          className={`whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm ${
            mine
              ? "rounded-br-sm bg-amber-400 text-slate-900"
              : bot
                ? "rounded-bl-sm border border-white/10 bg-white/[0.06] text-slate-300"
                : "rounded-bl-sm bg-sky-500/20 text-sky-100"
          }`}
        >
          {message.content}
        </div>
      </div>
    </div>
  );
}
