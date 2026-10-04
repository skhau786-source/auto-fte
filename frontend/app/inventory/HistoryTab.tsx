"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Badge, Btn, Card, Empty, Spinner, fmtDate, inputCls } from "../components/workspace/ui";
import { apiFetch, ApiError, Movement, VariantLabelMap } from "../lib/api";

interface Props {
  storeId: number;
  version: number;
  variantLabels: VariantLabelMap;
  toast: (kind: "ok" | "err", text: string) => void;
}

const TYPES = ["", "adjustment", "reservation", "sale", "purchase", "return", "platform_sync"];
const PAGE_SIZE = 20;

export function HistoryTab({ storeId, version, variantLabels, toast }: Props) {
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Movement[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => setPage(1), [type, storeId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (type) qs.set("movement_type", type);
    apiFetch<{ items: Movement[]; total: number }>(`/api/v1/stores/${storeId}/inventory/history?${qs}`)
      .then((d) => {
        if (cancelled) return;
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((e: ApiError) => !cancelled && toast("err", e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [storeId, type, page, version, toast]);

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <select aria-label="Movement type" value={type} onChange={(e) => setType(e.target.value)} className={`${inputCls} !w-auto`}>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {t ? t.replace("_", " ") : "All movements"}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-500">{total} records</span>
      </div>

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Empty title="No stock movements yet" text="Every adjustment and reservation shows up here." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">When</th>
                <th className="py-2 pr-3 font-medium">Item</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 text-right font-medium">Change</th>
                <th className="py-2 pr-3 text-right font-medium">Before → After</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap py-2.5 pr-3 text-xs text-slate-400">{fmtDate(m.created_at)}</td>
                  <td className="max-w-[240px] truncate py-2.5 pr-3">{variantLabels[m.variant_id] || `Variant ${m.variant_id}`}</td>
                  <td className="py-2.5 pr-3">
                    <Badge>{m.movement_type.replace("_", " ")}</Badge>
                  </td>
                  <td className={`py-2.5 pr-3 text-right font-semibold tabular-nums ${m.quantity_change > 0 ? "text-emerald-300" : "text-rose-300"}`}>
                    {m.quantity_change > 0 ? "+" : ""}
                    {m.quantity_change}
                  </td>
                  <td className="whitespace-nowrap py-2.5 pr-3 text-right text-xs tabular-nums text-slate-400">
                    {m.quantity_before} → {m.quantity_after}
                  </td>
                  <td className="py-2.5 text-xs text-slate-400">{m.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm text-slate-400">
          <Btn variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft className="h-4 w-4" /> Prev
          </Btn>
          <span>
            Page {page} of {pages}
          </span>
          <Btn variant="ghost" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Next <ChevronRight className="h-4 w-4" />
          </Btn>
        </div>
      )}
    </Card>
  );
}
