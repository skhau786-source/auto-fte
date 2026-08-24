"use client";

/**
 * AIAgentsHub — AI Agent management experience for business users.
 *
 * Every number comes from the backend AI agent APIs:
 *   /ai/agents     — agent CRUD
 *   /ai/tasks/*    — task submission and lifecycle
 *   /ai/actions    — audit trail
 *
 * No mock data. If no organization is configured the backend returns 403/404
 * and we show a friendly "not authorized" state.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bot,
  Plus,
  Play,
  Pause,
  Loader2,
  AlertCircle,
  Shield,
  Activity,
  ChevronRight,
  X,
  Zap,
} from "lucide-react";
import {
  agentApi,
  type AIAgent,
  type AITask,
  type AIAgentAction,
  type AICapability,
} from "@/lib/api";

// ───────────────────────────────────────────────────────────────────
// Types & helpers
// ───────────────────────────────────────────────────────────────────

type AgentTab = "agents" | "tasks" | "capabilities" | "audit";

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Never";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const AGENT_TYPE_LABELS: Record<string, string> = {
  inventory: "📦 Inventory",
  social: "📱 Social",
  sales: "💰 Sales",
  analytics: "📊 Analytics",
  custom: "🤖 Custom",
};

const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  active: { text: "● Active", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  inactive: { text: "○ Inactive", cls: "bg-slate-50 text-slate-500 border-slate-200" },
  error: { text: "⚠ Error", cls: "bg-rose-50 text-rose-700 border-rose-200" },
};

const TASK_STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  pending: { text: "⏳ Pending", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  pending_approval: { text: "🔐 Awaiting Approval", cls: "bg-violet-50 text-violet-700 border-violet-200" },
  running: { text: "🔄 Running", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  completed: { text: "✅ Completed", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  failed: { text: "❌ Failed", cls: "bg-rose-50 text-rose-700 border-rose-200" },
  cancelled: { text: "⬜ Cancelled", cls: "bg-slate-50 text-slate-500 border-slate-200" },
  rejected: { text: "🚫 Rejected", cls: "bg-rose-50 text-rose-700 border-rose-200" },
};

const TASK_TYPES = [
  { value: "custom", label: "Custom Task" },
  { value: "inventory_check", label: "Inventory Check" },
  { value: "inventory_adjust", label: "Inventory Adjustment" },
  { value: "stock_recommendation", label: "Stock Recommendation" },
  { value: "content_generate", label: "Content Generation" },
  { value: "sales_analysis", label: "Sales Analysis" },
  { value: "price_optimization", label: "Price Optimization" },
];

function friendly(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message && err.message !== "An unexpected error occurred") {
    return err.message;
  }
  return fallback;
}

// ───────────────────────────────────────────────────────────────────
// Shared UI
// ───────────────────────────────────────────────────────────────────

function LoadingBlock() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
    </div>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="p-8 rounded-2xl bg-rose-50/70 border border-rose-100 text-center">
      <AlertCircle className="w-8 h-8 mx-auto text-rose-400 mb-2" />
      <p className="text-sm font-semibold text-rose-700">Something went wrong</p>
      <p className="text-xs text-rose-500 mt-1">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-4 px-4 py-2 bg-white border border-rose-200 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50">
          Try again
        </button>
      )}
    </div>
  );
}

function EmptyBlock({ icon, title, subtitle, action }: { icon: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="p-10 rounded-2xl bg-white/70 border border-slate-200/70 text-center">
      <div className="w-14 h-14 mx-auto rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-500 mb-3">{icon}</div>
      <p className="text-sm font-bold text-slate-800">{title}</p>
      {subtitle && <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">{subtitle}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

function Modal({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h4 className="text-lg font-bold text-slate-900">{title}</h4>
            {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Main Hub
// ───────────────────────────────────────────────────────────────────

export default function AIAgentsHub() {
  const [tab, setTab] = useState<AgentTab>("agents");
  const [agents, setAgents] = useState<AIAgent[]>([]);
  const [tasks, setTasks] = useState<AITask[]>([]);
  const [actions, setActions] = useState<AIAgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    try {
      const data = await agentApi.list();
      setAgents(data.items);
    } catch {
      setAgents([]);
    }
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      // Load tasks for all agents
      const allTasks: AITask[] = [];
      for (const agent of agents) {
        const data = await agentApi.listTasks(agent.id);
        allTasks.push(...data.items);
      }
      allTasks.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setTasks(allTasks);
    } catch {
      setTasks([]);
    }
  }, [agents]);

  const loadActions = useCallback(async () => {
    try {
      const data = await agentApi.listActions();
      setActions(data.items);
    } catch {
      setActions([]);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await loadAgents();
    } catch (err) {
      setError(friendly(err, "Couldn't load AI agents."));
    } finally {
      setLoading(false);
    }
  }, [loadAgents]);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    if (tab === "tasks" && agents.length > 0) loadTasks();
    if (tab === "audit") loadActions();
  }, [tab, agents, loadTasks, loadActions]);

  const tabs: { id: AgentTab; label: string; icon: React.ReactNode }[] = [
    { id: "agents", label: "Agents", icon: <Bot className="w-4 h-4" /> },
    { id: "tasks", label: "Tasks", icon: <Activity className="w-4 h-4" /> },
    { id: "capabilities", label: "Capabilities", icon: <Zap className="w-4 h-4" /> },
    { id: "audit", label: "Audit Log", icon: <Shield className="w-4 h-4" /> },
  ];

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorBlock message={error} onRetry={loadAll} />;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-slate-900">AI Agents</h3>
        <p className="text-xs text-slate-500">Manage your AI-powered business assistants.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
              tab === t.id ? "bg-violet-600 text-white shadow-md shadow-violet-500/20" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === "agents" && <AgentsPage agents={agents} onRefresh={loadAll} />}
      {tab === "tasks" && <TasksPage tasks={tasks} agents={agents} onRefresh={loadTasks} />}
      {tab === "capabilities" && <CapabilitiesPage />}
      {tab === "audit" && <AuditPage actions={actions} />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// AGENTS PAGE
// ───────────────────────────────────────────────────────────────────

function AgentsPage({ agents, onRefresh }: { agents: AIAgent[]; onRefresh: () => void }) {
  const [showCreate, setShowCreate] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AIAgent | null>(null);

  if (selectedAgent) {
    return <AgentDetailPage agent={selectedAgent} onBack={() => setSelectedAgent(null)} onRefresh={onRefresh} />;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">{agents.length} agent{agents.length === 1 ? "" : "s"}</p>
        <button onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Create Agent
        </button>
      </div>

      {agents.length === 0 ? (
        <EmptyBlock
          icon={<Bot className="w-7 h-7" />}
          title="No AI agents yet"
          subtitle="Create your first agent to start automating your business operations."
          action={
            <button onClick={() => setShowCreate(true)}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all">
              Create Agent
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => {
            const statusInfo = STATUS_LABELS[agent.status] || STATUS_LABELS.inactive;
            return (
              <div key={agent.id}
                className="p-5 rounded-2xl bg-white/80 border border-slate-200/60 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 cursor-pointer"
                onClick={() => setSelectedAgent(agent)}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                      agent.status === "active" ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-400"
                    }`}>
                      <Bot className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-slate-900">{agent.name}</h4>
                      <p className="text-[10px] text-slate-400">{AGENT_TYPE_LABELS[agent.agent_type] || agent.agent_type}</p>
                    </div>
                  </div>
                  <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full border ${statusInfo.cls}`}>
                    {statusInfo.text}
                  </span>
                </div>
                {agent.description && (
                  <p className="text-xs text-slate-500 mt-3 line-clamp-2">{agent.description}</p>
                )}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
                  <span className="text-[10px] text-slate-400">Created {timeAgo(agent.created_at)}</span>
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showCreate && <CreateAgentModal onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); onRefresh(); }} />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// AGENT DETAIL PAGE
// ───────────────────────────────────────────────────────────────────

function AgentDetailPage({ agent, onBack, onRefresh }: { agent: AIAgent; onBack: () => void; onRefresh: () => void }) {
  const [tasks, setTasks] = useState<AITask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showTaskModal, setShowTaskModal] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await agentApi.listTasks(agent.id);
      setTasks(data.items);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [agent.id]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const handleToggleActive = async () => {
    try {
      if (agent.status === "active") {
        await agentApi.deactivate(agent.id);
      } else {
        await agentApi.update(agent.id, { config: agent.config || undefined });
      }
      onRefresh();
    } catch {
      // Silently fail — user can retry
    }
  };

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-bold text-violet-600 hover:underline">
        ← Back to Agents
      </button>

      <div className="p-5 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-lg">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-lg font-extrabold">{agent.name}</h4>
            <p className="text-xs text-violet-200 mt-1">{AGENT_TYPE_LABELS[agent.agent_type] || agent.agent_type}</p>
          </div>
          <span className={`px-3 py-1.5 text-xs font-bold rounded-full border ${
            agent.status === "active" ? "bg-emerald-500/20 text-emerald-100 border-emerald-400/30" : "bg-white/10 text-violet-200 border-white/20"
          }`}>
            {STATUS_LABELS[agent.status]?.text || agent.status}
          </span>
        </div>
        {agent.description && <p className="text-xs text-violet-200 mt-2">{agent.description}</p>}
        <div className="flex gap-4 mt-4">
          <button onClick={handleToggleActive}
            className="px-4 py-2 rounded-xl bg-white/10 border border-white/20 text-xs font-bold hover:bg-white/20 transition-all flex items-center gap-1.5">
            {agent.status === "active" ? <><Pause className="w-3 h-3" /> Deactivate</> : <><Play className="w-3 h-3" /> Activate</>}
          </button>
          <button onClick={() => setShowTaskModal(true)}
            className="px-4 py-2 rounded-xl bg-white text-violet-700 text-xs font-bold hover:shadow-lg transition-all flex items-center gap-1.5">
            <Zap className="w-3 h-3" /> Submit Task
          </button>
        </div>
      </div>

      {/* Tasks list */}
      <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-4">Recent Tasks</h4>
        {loading ? <LoadingBlock /> : tasks.length === 0 ? (
          <p className="text-xs text-slate-400 py-6 text-center">No tasks submitted yet. Click "Submit Task" to get started.</p>
        ) : (
          <div className="space-y-2">
            {tasks.slice(0, 10).map((task) => {
              const statusInfo = TASK_STATUS_LABELS[task.status] || TASK_STATUS_LABELS.pending;
              return (
                <div key={task.id} className="flex items-center justify-between p-3 bg-slate-50/70 rounded-xl border border-slate-100/60">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">{task.task_type}</p>
                    <p className="text-[10px] text-slate-400">{timeAgo(task.created_at)}{task.execution_duration_ms ? ` · ${task.execution_duration_ms}ms` : ""}</p>
                  </div>
                  <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full border ${statusInfo.cls}`}>{statusInfo.text}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showTaskModal && (
        <SubmitTaskModal
          agent={agent}
          onClose={() => setShowTaskModal(false)}
          onDone={() => { setShowTaskModal(false); loadTasks(); }}
        />
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// CREATE AGENT MODAL
// ───────────────────────────────────────────────────────────────────

function CreateAgentModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ name: "", agent_type: "custom", description: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setError("Please enter an agent name."); return; }
    setBusy(true);
    setError(null);
    try {
      await agentApi.create({ name: form.name.trim(), agent_type: form.agent_type, description: form.description.trim() || undefined });
      onDone();
    } catch (err) {
      setError(friendly(err, "Couldn't create the agent."));
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";
  const labelCls = "block text-xs font-bold text-slate-600 mb-1";

  return (
    <Modal title="Create AI Agent" subtitle="Set up a new AI assistant for your business" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className={labelCls}>Agent Name</label>
          <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Inventory Monitor" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Agent Type</label>
          <select value={form.agent_type} onChange={(e) => setForm({ ...form, agent_type: e.target.value })} className={inputCls}>
            <option value="inventory">📦 Inventory</option>
            <option value="social">📱 Social</option>
            <option value="sales">💰 Sales</option>
            <option value="analytics">📊 Analytics</option>
            <option value="custom">🤖 Custom</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Description <span className="text-slate-400 font-medium">(optional)</span></label>
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What should this agent do?" className={inputCls} rows={3} />
        </div>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Create Agent
        </button>
      </form>
    </Modal>
  );
}

// ───────────────────────────────────────────────────────────────────
// SUBMIT TASK MODAL
// ───────────────────────────────────────────────────────────────────

function SubmitTaskModal({ agent, onClose, onDone }: { agent: AIAgent; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ task_type: "custom", input_data: "", requires_approval: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let inputData: Record<string, unknown> | undefined;
      if (form.input_data.trim()) {
        try {
          inputData = JSON.parse(form.input_data);
        } catch {
          inputData = { prompt: form.input_data.trim() };
        }
      }
      await agentApi.submitTask(agent.id, {
        task_type: form.task_type,
        input_data: inputData,
        requires_human_approval: form.requires_approval,
      });
      onDone();
    } catch (err) {
      setError(friendly(err, "Couldn't submit the task."));
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";
  const labelCls = "block text-xs font-bold text-slate-600 mb-1";

  return (
    <Modal title={`Submit Task to ${agent.name}`} subtitle="Send a task for this agent to process" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className={labelCls}>Task Type</label>
          <select value={form.task_type} onChange={(e) => setForm({ ...form, task_type: e.target.value })} className={inputCls}>
            {TASK_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Input Data <span className="text-slate-400 font-medium">(JSON or plain text)</span></label>
          <textarea value={form.input_data} onChange={(e) => setForm({ ...form, input_data: e.target.value })}
            placeholder='{"prompt": "Check low stock items"}' className={inputCls} rows={4} />
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={form.requires_approval}
            onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            className="w-4 h-4 rounded border-slate-300 text-violet-600 focus:ring-violet-500" />
          <span className="text-xs font-semibold text-slate-600">Require human approval before execution</span>
        </label>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button type="submit" disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Submit Task
        </button>
      </form>
    </Modal>
  );
}

// ───────────────────────────────────────────────────────────────────
// TASKS PAGE
// ───────────────────────────────────────────────────────────────────

function TasksPage({ tasks, agents, onRefresh }: { tasks: AITask[]; agents: AIAgent[]; onRefresh: () => void }) {
  const handleApprove = async (taskId: string) => {
    try {
      await agentApi.approveTask(taskId, "Approved from dashboard");
      onRefresh();
    } catch {
      // Silently fail
    }
  };

  const handleReject = async (taskId: string) => {
    try {
      await agentApi.rejectTask(taskId, "Rejected from dashboard");
      onRefresh();
    } catch {
      // Silently fail
    }
  };

  const agentName = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of agents) map.set(a.id, a.name);
    return map;
  }, [agents]);

  // Separate parent tasks from child (handoff) tasks
  const parentTasks = tasks.filter((t) => !t.parent_task_id);
  const childTasks = tasks.filter((t) => t.parent_task_id);
  const childTaskMap = useMemo(() => {
    const map = new Map<string, AITask[]>();
    for (const ct of childTasks) {
      const parentId = ct.parent_task_id!;
      if (!map.has(parentId)) map.set(parentId, []);
      map.get(parentId)!.push(ct);
    }
    return map;
  }, [childTasks]);

  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-500">{tasks.length} task{tasks.length === 1 ? "" : "s"} · {parentTasks.length} parent{parentTasks.length === 1 ? "" : "s"} · {childTasks.length} handoff{childTasks.length === 1 ? "" : "s"}</p>
      {tasks.length === 0 ? (
        <EmptyBlock icon={<Activity className="w-7 h-7" />} title="No tasks yet" subtitle="Submit a task from an agent to see it here." />
      ) : (
        <div className="space-y-4">
          {parentTasks.map((task) => {
            const statusInfo = TASK_STATUS_LABELS[task.status] || TASK_STATUS_LABELS.pending;
            const children = childTaskMap.get(task.id) || [];
            return (
              <div key={task.id} className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
                {/* Parent task row */}
                <div className="px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-500 shrink-0">
                      <Bot className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-slate-800">{task.task_type}</p>
                        {task.requires_human_approval && (
                          <span className="px-1.5 py-0.5 text-[8px] font-bold rounded bg-violet-100 text-violet-600">APPROVAL</span>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-400">
                        {agentName.get(task.agent_id) || "Unknown"} · {timeAgo(task.created_at)}{task.execution_duration_ms ? ` · ${task.execution_duration_ms}ms` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full border ${statusInfo.cls}`}>{statusInfo.text}</span>
                    {task.status === "pending_approval" && (
                      <div className="flex items-center gap-1">
                        <button onClick={() => handleApprove(task.id)} className="px-2 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold hover:bg-emerald-100">Approve</button>
                        <button onClick={() => handleReject(task.id)} className="px-2 py-1 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-bold hover:bg-rose-100">Reject</button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Child tasks (handoffs) */}
                {children.length > 0 && (
                  <div className="border-t border-slate-100 bg-slate-50/50">
                    {children.map((child, idx) => {
                      const childStatus = TASK_STATUS_LABELS[child.status] || TASK_STATUS_LABELS.pending;
                      const isLast = idx === children.length - 1;
                      return (
                        <div key={child.id} className={`px-4 py-2.5 flex items-center justify-between ${!isLast ? "border-b border-slate-100" : ""}`}>
                          <div className="flex items-center gap-3 min-w-0">
                            {/* Indent + handoff arrow */}
                            <div className="flex items-center gap-1 pl-4">
                              <span className="text-[10px] text-violet-400">↓</span>
                              <span className="text-[10px] text-violet-400 font-medium">Handoff</span>
                            </div>
                            <div className="w-6 h-6 rounded bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-500 shrink-0">
                              <Bot className="w-3 h-3" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-xs font-medium text-slate-700">
                                  {agentName.get(child.source_agent_id || "") || "?"}
                                  <span className="text-violet-400 mx-1">→</span>
                                  {agentName.get(child.target_agent_id || child.agent_id) || "?"}
                                </p>
                                {child.capability_name && (
                                  <span className="px-1.5 py-0.5 text-[8px] font-bold rounded bg-indigo-100 text-indigo-600">
                                    {child.capability_name}
                                  </span>
                                )}
                              </div>
                              <p className="text-[10px] text-slate-400">
                                Depth {child.handoff_depth}{child.execution_duration_ms ? ` · ${child.execution_duration_ms}ms` : ""}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-1 text-[9px] font-bold rounded-full border ${childStatus.cls}`}>{childStatus.text}</span>
                            {child.status === "pending_approval" && (
                              <div className="flex items-center gap-1">
                                <button onClick={() => handleApprove(child.id)} className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[8px] font-bold hover:bg-emerald-100">Approve</button>
                                <button onClick={() => handleReject(child.id)} className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[8px] font-bold hover:bg-rose-100">Reject</button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {/* Orphaned child tasks (if parent was deleted) */}
          {childTasks.filter((ct) => !parentTasks.some((pt) => pt.id === ct.parent_task_id)).length > 0 && (
            <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
              <div className="px-4 py-2 bg-slate-50 border-b border-slate-100">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">Handoff Tasks (Orphaned)</p>
              </div>
              {childTasks.filter((ct) => !parentTasks.some((pt) => pt.id === ct.parent_task_id)).map((task) => {
                const statusInfo = TASK_STATUS_LABELS[task.status] || TASK_STATUS_LABELS.pending;
                return (
                  <div key={task.id} className="px-4 py-2.5 flex items-center justify-between border-b border-slate-100 last:border-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[10px] text-violet-400">↓ Handoff</span>
                      <p className="text-xs font-medium text-slate-700">
                        {agentName.get(task.source_agent_id || "") || "?"}
                        <span className="text-violet-400 mx-1">→</span>
                        {agentName.get(task.target_agent_id || task.agent_id) || "?"}
                      </p>
                      {task.capability_name && (
                        <span className="px-1.5 py-0.5 text-[8px] font-bold rounded bg-indigo-100 text-indigo-600">{task.capability_name}</span>
                      )}
                    </div>
                    <span className={`px-2 py-1 text-[9px] font-bold rounded-full border ${statusInfo.cls}`}>{statusInfo.text}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// AUDIT PAGE
// ───────────────────────────────────────────────────────────────────

function CapabilitiesPage() {
  const [capabilities, setCapabilities] = useState<AICapability[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = filter === "all" ? {} : { category: filter };
      const data = await agentApi.listCapabilities(params);
      setCapabilities(data.items);
    } catch (err) {
      setError(friendly(err, "Couldn't load capabilities."));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const categories = ["all", "inventory", "social", "sales", "analytics"];

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorBlock message={error} onRetry={load} />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">{capabilities.length} capability{capabilities.length === 1 ? "" : "s"} available</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {categories.map((cat) => (
          <button key={cat} onClick={() => setFilter(cat)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all capitalize ${
              filter === cat ? "bg-violet-600 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            {cat === "all" ? "All" : cat}
          </button>
        ))}
      </div>

      {capabilities.length === 0 ? (
        <EmptyBlock icon={<Zap className="w-7 h-7" />} title="No capabilities found" subtitle="No capabilities match the selected filter." />
      ) : (
        <div className="space-y-3">
          {capabilities.map((cap) => (
            <div key={cap.name} className="p-4 rounded-2xl bg-white/80 border border-slate-200/60 hover:shadow-lg transition-all">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold text-slate-900">{cap.display_name}</h4>
                    <span className={`px-2 py-0.5 text-[9px] font-bold rounded-full ${
                      cap.capability_type === "read" ? "bg-blue-50 text-blue-700" : "bg-amber-50 text-amber-700"
                    }`}>
                      {cap.capability_type === "read" ? "READ" : "WRITE"}
                    </span>
                    {cap.requires_approval && (
                      <span className="px-2 py-0.5 text-[9px] font-bold rounded-full bg-violet-50 text-violet-700">
                        REQUIRES APPROVAL
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{cap.description}</p>
                  <p className="text-[10px] text-slate-400 mt-1">Category: {cap.category} · Agents: {cap.supported_agent_types.join(", ")}</p>
                </div>
                <span className={`px-2 py-1 text-[9px] font-bold rounded-full ${
                  cap.requires_approval ? "bg-amber-50 text-amber-700 border border-amber-200" : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                }`}>
                  {cap.requires_approval ? "Approval Required" : "Auto-Execute"}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AuditPage({ actions }: { actions: AIAgentAction[] }) {
  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-500">{actions.length} action{actions.length === 1 ? "" : "s"} recorded</p>
      {actions.length === 0 ? (
        <EmptyBlock icon={<Shield className="w-7 h-7" />} title="No audit records yet" subtitle="Agent actions will appear here once agents start working." />
      ) : (
        <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left font-bold">Action</th>
                  <th className="px-4 py-3 text-left font-bold">Target</th>
                  <th className="px-4 py-3 text-left font-bold">Result</th>
                  <th className="px-4 py-3 text-left font-bold">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {actions.map((action) => (
                  <tr key={action.id} className="hover:bg-violet-50/30 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-800">{action.action_type}</td>
                    <td className="px-4 py-3 text-slate-500">{action.target_resource ? `${action.target_resource}/${action.target_id || ""}` : "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2.5 py-1 text-[10px] font-bold rounded-full ${
                        action.result_status === "success" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                      }`}>
                        {action.result_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{timeAgo(action.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
