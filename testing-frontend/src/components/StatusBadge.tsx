export default function StatusBadge({ status }: { status?: number }) {
  let cls = "bg-gray-500";
  if (status !== undefined) {
    if (status >= 200 && status < 300) cls = "bg-green-600";
    else if (status === 401 || status === 403) cls = "bg-amber-500";
    else if (status >= 500) cls = "bg-red-600";
    else if (status >= 400) cls = "bg-orange-500";
  }
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 font-mono text-xs font-bold text-white ${cls}`}
    >
      {status ?? "—"}
    </span>
  );
}
