import { useState } from "react";
import { api, execute } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

const field = "w-full rounded border border-gray-300 px-3 py-2 text-sm";
const label = "mb-1 block text-sm font-medium";
const btn =
  "rounded px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-40";

export default function Orders() {
  const [dashLoading, setDashLoading] = useState(false);
  const [dashResult, setDashResult] = useState<any>(null);
  const [orderId, setOrderId] = useState("");
  const [action, setAction] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionResult, setActionResult] = useState<any>(null);

  const loadDashboard = async () => {
    setDashLoading(true);
    setDashResult(null);
    const r = await execute(() => api.get("/orders/dashboard"));
    setDashResult(r);
    setDashLoading(false);
  };

  const runAction = async (kind: string) => {
    if (!orderId) return;
    setAction(kind);
    setActionLoading(true);
    setActionResult(null);
    const url = `/orders/${orderId}`;
    const r =
      kind === "allocation"
        ? await execute(() => api.get(`${url}/allocation`))
        : kind === "reservations"
          ? await execute(() => api.get(`${url}/reservations`))
          : kind === "allocate"
            ? await execute(() => api.post(`${url}/allocate`))
            : kind === "commit"
              ? await execute(() => api.post(`${url}/commit`))
              : await execute(() => api.post(`${url}/release`));
    setActionResult(r);
    setActionLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Orders</h2>
        <button
          onClick={loadDashboard}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Load Dashboard
        </button>
      </div>
      <p className="text-xs text-gray-500">GET /orders/dashboard (requires auth)</p>
      <ResultPanel loading={dashLoading} result={dashResult} />

      <section className="rounded border bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-lg font-semibold">Order Actions</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-64">
            <label className={label}>Order ID / Number</label>
            <input
              value={orderId}
              onChange={(e) => setOrderId(e.target.value)}
              placeholder="e.g. 12345"
              className={field}
            />
          </div>
          <button
            onClick={() => runAction("allocation")}
            disabled={!orderId}
            className={`${btn} bg-blue-600`}
          >
            Get Allocation
          </button>
          <button
            onClick={() => runAction("reservations")}
            disabled={!orderId}
            className={`${btn} bg-indigo-600`}
          >
            Get Reservations
          </button>
          <button
            onClick={() => runAction("allocate")}
            disabled={!orderId}
            className={`${btn} bg-green-600`}
          >
            Allocate
          </button>
          <button
            onClick={() => runAction("commit")}
            disabled={!orderId}
            className={`${btn} bg-teal-600`}
          >
            Commit
          </button>
          <button
            onClick={() => runAction("release")}
            disabled={!orderId}
            className={`${btn} bg-red-600`}
          >
            Release
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {"GET/POST /orders/{order_id}/allocation · reservations · allocate · commit · release"}
        </p>
        {action && !actionLoading && <p className="mt-1 text-xs text-gray-400">Last action: {action}</p>}
        <ResultPanel loading={actionLoading} result={actionResult} />
      </section>
    </div>
  );
}
