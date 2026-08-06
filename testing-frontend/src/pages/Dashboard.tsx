import { useEffect, useState } from "react";
import { api, execute, getToken } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    setResult(null);
    const r = await execute(() => api.get("/dashboard/unified"));
    setResult(r);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold">Dashboard</h2>
        <button
          onClick={load}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Reload
        </button>
      </div>
      {!getToken() && (
        <p className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          No bearer token saved — this endpoint will return 401 until you paste a token in the
          header.
        </p>
      )}
      <p className="text-xs text-gray-500">GET /dashboard/unified (requires auth)</p>
      <ResultPanel loading={loading} result={result} />
    </div>
  );
}
