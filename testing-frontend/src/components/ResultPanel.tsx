import StatusBadge from "./StatusBadge";
import JsonView from "./JsonView";
import type { ApiResult } from "../lib/api";

export default function ResultPanel({
  loading,
  result,
}: {
  loading: boolean;
  result: ApiResult | null;
}) {
  if (loading) return <div className="mt-3 text-sm font-medium text-blue-600">Loading...</div>;
  if (!result) return null;

  if (result.ok) {
    return (
      <div className="mt-3 rounded border border-green-200 bg-green-50 p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-green-800">
          <StatusBadge status={result.status} />
          <span>Success</span>
          {result.ms !== undefined && <span className="font-normal text-green-600">{result.ms} ms</span>}
        </div>
        {result.data !== undefined && <JsonView data={result.data} />}
      </div>
    );
  }

  return (
    <div className="mt-3 rounded border border-red-200 bg-red-50 p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-red-800">
        <StatusBadge status={result.status} />
        <span>Error</span>
        {result.ms !== undefined && <span className="font-normal text-red-600">{result.ms} ms</span>}
      </div>
      {result.error && <p className="mt-1 text-xs text-red-700">{result.error}</p>}
      {result.data !== undefined && <JsonView data={result.data} />}
    </div>
  );
}
