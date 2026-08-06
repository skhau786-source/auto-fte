import { useCallback, useEffect, useState } from "react";
import { api, execute } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import JsonView from "../components/JsonView";

type Check = {
  id: string;
  method: string;
  path: string;
  loading: boolean;
  result: any;
};

const endpoints = [
  { id: "health", method: "GET", path: "/health" },
  { id: "live", method: "GET", path: "/live" },
  { id: "version", method: "GET", path: "/version" },
  { id: "ready", method: "GET", path: "/ready" },
  { id: "metrics", method: "GET", path: "/metrics" },
];

export default function Health() {
  const [checks, setChecks] = useState<Record<string, Check>>(() =>
    Object.fromEntries(
      endpoints.map((e) => [e.id, { ...e, loading: false, result: null }])
    )
  );

  const runAll = useCallback(async () => {
    setChecks((prev) => {
      const next: Record<string, Check> = {};
      for (const [k, v] of Object.entries(prev)) next[k] = { ...v, loading: true, result: null };
      return next;
    });
    for (const e of endpoints) {
      const r = await execute(() => api.get(e.path));
      setChecks((prev) => ({ ...prev, [e.id]: { ...prev[e.id], loading: false, result: r } }));
    }
  }, []);

  useEffect(() => {
    runAll();
  }, [runAll]);

  const ready = checks.ready?.result;
  const readyData = (ready?.data ?? {}) as { checks?: { database?: string } };
  const database = readyData.checks?.database ?? "unknown";
  const dbOk = database === "ok";

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold">API Health</h2>
        <button
          onClick={runAll}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Re-run Checks
        </button>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded border bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Backend status</p>
          <p
            className={`text-lg font-bold ${
              checks.health?.result?.ok ? "text-green-600" : "text-red-600"
            }`}
          >
            {checks.health?.result?.ok ? "UP" : "DOWN"}
          </p>
          <p className="text-xs text-gray-400">GET /health</p>
        </div>
        <div className="rounded border bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Database status</p>
          <p className={`text-lg font-bold ${dbOk ? "text-green-600" : "text-amber-600"}`}>
            {database}
          </p>
          <p className="text-xs text-gray-400">from GET /ready</p>
        </div>
        <div className="rounded border bg-white p-3 shadow-sm">
          <p className="text-xs text-gray-500">Response time</p>
          <p className="text-lg font-bold text-gray-800">
            {checks.health?.result?.ms ?? "—"} ms
          </p>
          <p className="text-xs text-gray-400">GET /health</p>
        </div>
      </div>

      <div className="space-y-3">
        {Object.values(checks).map((c) => (
          <div key={c.id} className="rounded border bg-white p-3 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-gray-400">{c.method}</span>
              <span className="font-mono text-sm font-medium">{c.path}</span>
              {c.loading && <span className="text-xs text-blue-600">Loading...</span>}
              {!c.loading && c.result && (
                <>
                  <StatusBadge status={c.result.status} />
                  <span className="text-xs text-gray-500">{c.result.ms} ms</span>
                </>
              )}
            </div>
            {!c.loading && c.result && c.result.data !== undefined && (
              <JsonView data={c.result.data} />
            )}
            {!c.loading && c.result && !c.result.ok && c.result.error && (
              <p className="mt-1 text-xs text-red-700">{c.result.error}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
