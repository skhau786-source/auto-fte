"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, FileText, Plus, Search, Trash2, Upload } from "lucide-react";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import {
  Btn, Card, Empty, Field, Modal, SectionTitle, Spinner, Stat, fmtDate, inputCls, useToasts,
} from "../components/workspace/ui";
import {
  apiFetch, ApiError, AugmentResult, KnowledgeBase, RagDocument, SearchResult,
} from "../lib/api";

const KB_API = "/chatbot/rag";
const MAX_FILE_BYTES = 1_000_000;

export default function KnowledgeBasePage() {
  return (
    <WorkspaceShell
      title="Knowledge Base"
      subtitle="Upload your policies, FAQs and product guides. The chatbot answers from these documents."
    >
      <KnowledgeBaseWorkspace />
    </WorkspaceShell>
  );
}

function KnowledgeBaseWorkspace() {
  const { toast, toastNode } = useToasts();
  const [kbs, setKbs] = useState<KnowledgeBase[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadKbs = useCallback(
    async (selectId?: number) => {
      try {
        const list = await apiFetch<KnowledgeBase[]>(`${KB_API}/knowledge-bases`);
        setKbs(list);
        setSelectedId((cur) => {
          if (selectId !== undefined) return selectId;
          if (cur !== null && list.some((k) => k.id === cur)) return cur;
          return list[0]?.id ?? null;
        });
      } catch (e) {
        const err = e as ApiError;
        setError(err.status === 401 ? "Your session expired. Please log in again." : err.message);
      }
    },
    []
  );

  useEffect(() => {
    loadKbs();
  }, [loadKbs]);

  if (error) {
    return (
      <Card className="p-6">
        <Empty title="Could not load knowledge bases" text={error} />
      </Card>
    );
  }
  if (kbs === null) return <Spinner />;

  const selected = kbs.find((k) => k.id === selectedId) || null;

  return (
    <>
      <div className="grid gap-4 md:grid-cols-[260px_1fr]">
        <Card className="h-fit p-3">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold">Your knowledge bases</h2>
            <Btn variant="ghost" onClick={() => setCreating(true)} className="!px-2 !py-1">
              <Plus className="h-4 w-4" /> New
            </Btn>
          </div>
          {kbs.length === 0 ? (
            <Empty icon={<BookOpen className="h-7 w-7" />} title="Nothing here yet" text="Create your first knowledge base." />
          ) : (
            <ul className="space-y-1">
              {kbs.map((k) => (
                <li key={k.id}>
                  <button
                    onClick={() => setSelectedId(k.id)}
                    aria-current={k.id === selectedId}
                    className={`w-full rounded-xl px-3 py-2 text-left transition-colors ${
                      k.id === selectedId ? "bg-amber-400/15 text-amber-200" : "hover:bg-white/5"
                    }`}
                  >
                    <p className="truncate text-sm font-medium">{k.name}</p>
                    <p className="text-xs text-slate-400">
                      {k.document_count} docs · {k.chunk_count} chunks
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {selected ? (
          <KnowledgeBaseDetail
            key={selected.id}
            kb={selected}
            toast={toast}
            onChanged={() => loadKbs()}
            onDeleted={() => {
              setSelectedId(null);
              loadKbs();
            }}
          />
        ) : (
          <Card className="p-6">
            <Empty
              icon={<BookOpen className="h-8 w-8" />}
              title="Select or create a knowledge base"
              text="A knowledge base is a collection of documents your chatbot can search."
            />
          </Card>
        )}
      </div>

      {creating && (
        <CreateKbModal
          onClose={() => setCreating(false)}
          onCreated={(kb) => {
            setCreating(false);
            toast("ok", `Created "${kb.name}"`);
            loadKbs(kb.id);
          }}
          onError={(m) => toast("err", m)}
        />
      )}
      {toastNode}
    </>
  );
}

// ─── Detail ─────────────────────────────────────────────────

function KnowledgeBaseDetail({
  kb,
  toast,
  onChanged,
  onDeleted,
}: {
  kb: KnowledgeBase;
  toast: (k: "ok" | "err", t: string) => void;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [docs, setDocs] = useState<RagDocument[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [deletingKb, setDeletingKb] = useState(false);

  const loadDocs = useCallback(async () => {
    try {
      setDocs(await apiFetch<RagDocument[]>(`${KB_API}/knowledge-bases/${kb.id}/documents`));
    } catch (e) {
      toast("err", (e as ApiError).message);
      setDocs([]);
    }
  }, [kb.id, toast]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  const removeDoc = async (d: RagDocument) => {
    try {
      await apiFetch(`${KB_API}/documents/${d.id}`, { method: "DELETE" });
      toast("ok", `Deleted "${d.title}"`);
      loadDocs();
      onChanged();
    } catch (e) {
      toast("err", (e as ApiError).message);
    }
  };

  const removeKb = async () => {
    try {
      await apiFetch(`${KB_API}/knowledge-bases/${kb.id}`, { method: "DELETE" });
      toast("ok", `Deleted "${kb.name}"`);
      onDeleted();
    } catch (e) {
      toast("err", (e as ApiError).message);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{kb.name}</h2>
            {kb.description && <p className="mt-0.5 text-sm text-slate-400">{kb.description}</p>}
          </div>
          <Btn variant="danger" onClick={() => setDeletingKb(true)}>
            <Trash2 className="h-4 w-4" /> Delete
          </Btn>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3">
          <Stat label="Documents" value={kb.document_count} />
          <Stat label="Chunks" value={kb.chunk_count} />
          <Stat label="Tokens (est.)" value={kb.total_tokens.toLocaleString()} />
        </div>
      </Card>

      <Card className="p-4">
        <SectionTitle
          title="Documents"
          right={
            <Btn onClick={() => setAdding(true)}>
              <Plus className="h-4 w-4" /> Add document
            </Btn>
          }
        />
        {docs === null ? (
          <Spinner />
        ) : docs.length === 0 ? (
          <Empty icon={<FileText className="h-8 w-8" />} title="No documents yet" text="Paste text or upload a .txt / .md file." />
        ) : (
          <ul className="divide-y divide-white/5">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{d.title}</p>
                  <p className="text-xs text-slate-400">
                    {d.chunk_count} {d.chunk_count === 1 ? "chunk" : "chunks"} · {d.token_count.toLocaleString()} tokens · {fmtDate(d.created_at)}
                    {d.filename && ` · ${d.filename}`}
                  </p>
                </div>
                <button
                  onClick={() => removeDoc(d)}
                  aria-label={`Delete ${d.title}`}
                  className="rounded-lg p-2 text-slate-400 hover:bg-rose-500/10 hover:text-rose-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <TryItPanel kbId={kb.id} disabled={kb.chunk_count === 0} toast={toast} />

      {adding && (
        <AddDocumentModal
          kbId={kb.id}
          onClose={() => setAdding(false)}
          onAdded={(d) => {
            setAdding(false);
            toast("ok", `Indexed "${d.title}" into ${d.chunk_count} chunks`);
            loadDocs();
            onChanged();
          }}
          onError={(m) => toast("err", m)}
        />
      )}
      {deletingKb && (
        <Modal title="Delete knowledge base?" onClose={() => setDeletingKb(false)}>
          <p className="text-sm text-slate-300">
            “{kb.name}” and its {kb.document_count} document(s) will be permanently removed.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Btn variant="ghost" onClick={() => setDeletingKb(false)}>
              Cancel
            </Btn>
            <Btn variant="danger" onClick={removeKb}>
              Delete
            </Btn>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ─── Try it: search + LLM context ───────────────────────────

function TryItPanel({
  kbId,
  disabled,
  toast,
}: {
  kbId: number;
  disabled: boolean;
  toast: (k: "ok" | "err", t: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [context, setContext] = useState<AugmentResult | null>(null);

  const run = async () => {
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    setContext(null);
    try {
      const enc = encodeURIComponent(q);
      const [res, ctx] = await Promise.all([
        apiFetch<SearchResult>(`${KB_API}/knowledge-bases/${kbId}/search?query=${enc}&top_k=5`, { method: "POST" }),
        apiFetch<AugmentResult>(`${KB_API}/knowledge-bases/${kbId}/augment?query=${enc}&top_k=5`, { method: "POST" }),
      ]);
      setResult(res);
      setContext(ctx);
    } catch (e) {
      toast("err", (e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-4">
      <SectionTitle title="Try a question" hint="See exactly which passages the chatbot would use to answer." />
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className={`${inputCls} pl-9`}
            placeholder={disabled ? "Add a document first" : "e.g. How long does shipping take?"}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={disabled}
            aria-label="Question"
          />
        </div>
        <Btn type="submit" loading={busy} disabled={disabled || !query.trim()}>
          Search
        </Btn>
      </form>

      {result && (
        <div className="mt-4">
          <p className="mb-2 text-xs text-slate-400">
            {result.chunks_retrieved} passage(s) in {result.retrieval_time_ms} ms
          </p>
          {result.chunks.length === 0 ? (
            <Empty title="No matching passages" text="None of your documents share words with that question." />
          ) : (
            <ul className="space-y-2">
              {result.chunks.map((c) => (
                <li key={c.id} className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="truncate text-xs font-semibold text-amber-300">{c.document_title}</span>
                    <span className="flex shrink-0 items-center gap-2 text-[11px] text-slate-400">
                      keyword match {Math.round(c.similarity_score * 100)}%
                      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
                        <span className="block h-full bg-amber-400" style={{ width: `${Math.round(c.similarity_score * 100)}%` }} />
                      </span>
                    </span>
                  </div>
                  <p className="line-clamp-4 whitespace-pre-line text-sm text-slate-200">{c.content}</p>
                </li>
              ))}
            </ul>
          )}
          {context && context.context && (
            <details className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
              <summary className="cursor-pointer text-xs font-medium text-slate-300">
                Context sent to the AI ({context.source_documents} document(s), ~{context.tokens_added} tokens)
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-slate-400">{context.context}</pre>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}

// ─── Modals ─────────────────────────────────────────────────

function CreateKbModal({
  onClose,
  onCreated,
  onError,
}: {
  onClose: () => void;
  onCreated: (kb: KnowledgeBase) => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const kb = await apiFetch<KnowledgeBase>(`${KB_API}/knowledge-bases`, {
        method: "POST",
        body: { name: name.trim(), description: description.trim() || null },
      });
      onCreated(kb);
    } catch (e) {
      onError((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="New knowledge base" onClose={onClose}>
      <div className="space-y-3">
        <Field label="Name">
          <input className={inputCls} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} placeholder="e.g. Store policies" autoFocus />
        </Field>
        <Field label="Description (optional)">
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is in here?" />
        </Field>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Btn variant="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn onClick={submit} loading={busy} disabled={!name.trim()}>
          Create
        </Btn>
      </div>
    </Modal>
  );
}

function AddDocumentModal({
  kbId,
  onClose,
  onAdded,
  onError,
}: {
  kbId: number;
  onClose: () => void;
  onAdded: (d: RagDocument) => void;
  onError: (m: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      onError("File is too large (max 1 MB). Split it into smaller documents.");
      return;
    }
    if (!/\.(txt|md|markdown|csv)$/i.test(file.name)) {
      onError("Only .txt, .md and .csv files are supported. For PDFs, paste the text instead.");
      return;
    }
    const text = await file.text();
    setContent(text);
    setFilename(file.name);
    if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
  };

  const submit = async () => {
    if (!title.trim() || !content.trim()) return;
    setBusy(true);
    try {
      const ext = filename?.split(".").pop()?.toLowerCase();
      const doc = await apiFetch<RagDocument>(`${KB_API}/knowledge-bases/${kbId}/documents`, {
        method: "POST",
        body: {
          title: title.trim(),
          content,
          filename,
          file_type: ext === "md" || ext === "markdown" ? "md" : ext === "csv" ? "csv" : "text",
        },
      });
      onAdded(doc);
    } catch (e) {
      onError((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Add document" onClose={onClose}>
      <div className="space-y-3">
        <Field label="Title">
          <input className={inputCls} value={title} maxLength={255} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Refund policy" autoFocus />
        </Field>
        <Field label="Content" hint={filename ? `Loaded from ${filename}` : "Paste text, or upload a file below."}>
          <textarea
            className={`${inputCls} min-h-[160px] resize-y`}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setFilename(null);
            }}
            placeholder="Paste your document text here…"
          />
        </Field>
        <input ref={fileRef} type="file" accept=".txt,.md,.markdown,.csv,text/plain" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
        <Btn variant="ghost" onClick={() => fileRef.current?.click()}>
          <Upload className="h-4 w-4" /> Upload .txt / .md
        </Btn>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Btn variant="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn onClick={submit} loading={busy} disabled={!title.trim() || !content.trim()}>
          Add &amp; index
        </Btn>
      </div>
    </Modal>
  );
}
