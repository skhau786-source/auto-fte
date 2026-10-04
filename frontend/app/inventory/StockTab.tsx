"use client";

import { useMemo, useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";
import { Badge, Btn, Card, Empty, Field, Modal, inputCls } from "../components/workspace/ui";
import { apiFetch, ApiError, ProductRow, VariantRow } from "../lib/api";

interface Props {
  storeId: number;
  products: ProductRow[];
  toast: (kind: "ok" | "err", text: string) => void;
  onChange: () => void;
}

function stockStatus(v: VariantRow): "in_stock" | "low_stock" | "out_of_stock" {
  if (v.inventory_quantity <= 0) return "out_of_stock";
  if (v.inventory_quantity <= v.low_stock_threshold) return "low_stock";
  return "in_stock";
}

const STATUS_LABEL = { in_stock: "In stock", low_stock: "Low", out_of_stock: "Out of stock" };

export function StockTab({ storeId, products, toast, onChange }: Props) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "low_stock" | "out_of_stock">("all");
  const [adjusting, setAdjusting] = useState<{ product: ProductRow; variant: VariantRow } | null>(null);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return products.flatMap((p) =>
      p.variants
        .filter((v) => {
          if (filter !== "all" && stockStatus(v) !== filter) return false;
          if (!q) return true;
          return p.title.toLowerCase().includes(q) || v.title.toLowerCase().includes(q) || (v.sku || "").toLowerCase().includes(q);
        })
        .map((v) => ({ product: p, variant: v }))
    );
  }, [products, search, filter]);

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className={`${inputCls} pl-9`}
            placeholder="Search product, variant or SKU"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search stock"
          />
        </div>
        <select
          aria-label="Stock filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as typeof filter)}
          className={`${inputCls} !w-auto`}
        >
          <option value="all">All stock</option>
          <option value="low_stock">Low stock</option>
          <option value="out_of_stock">Out of stock</option>
        </select>
      </div>

      {rows.length === 0 ? (
        <Empty
          title={products.length === 0 ? "No products synced yet" : "No variants match"}
          text={products.length === 0 ? "Run a sync from your connected store to import products." : "Try a different search or filter."}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Product</th>
                <th className="py-2 pr-3 font-medium">SKU</th>
                <th className="py-2 pr-3 text-right font-medium">Price</th>
                <th className="py-2 pr-3 text-right font-medium">Stock</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map(({ product, variant }) => {
                const status = stockStatus(variant);
                return (
                  <tr key={variant.id}>
                    <td className="py-2.5 pr-3">
                      <p className="font-medium">{product.title}</p>
                      <p className="text-xs text-slate-400">{variant.title}</p>
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-xs text-slate-400">{variant.sku || "—"}</td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">{Number(variant.price).toLocaleString()}</td>
                    <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">{variant.inventory_quantity}</td>
                    <td className="py-2.5 pr-3">
                      <Badge tone={status}>{STATUS_LABEL[status]}</Badge>
                    </td>
                    <td className="py-2.5 text-right">
                      <Btn variant="ghost" onClick={() => setAdjusting({ product, variant })}>
                        <SlidersHorizontal className="h-3.5 w-3.5" /> Adjust
                      </Btn>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {adjusting && (
        <AdjustModal
          storeId={storeId}
          product={adjusting.product}
          variant={adjusting.variant}
          onClose={() => setAdjusting(null)}
          onDone={(msg) => {
            toast("ok", msg);
            setAdjusting(null);
            onChange();
          }}
          onError={(msg) => toast("err", msg)}
        />
      )}
    </Card>
  );
}

function AdjustModal({
  storeId,
  product,
  variant,
  onClose,
  onDone,
  onError,
}: {
  storeId: number;
  product: ProductRow;
  variant: VariantRow;
  onClose: () => void;
  onDone: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [mode, setMode] = useState<"add" | "remove">("add");
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const amount = Math.floor(Number(qty));
  const valid = Number.isFinite(amount) && amount > 0;
  const change = mode === "add" ? amount : -amount;
  const after = variant.inventory_quantity + (valid ? change : 0);
  const negative = valid && after < 0;

  const submit = async () => {
    if (!valid || negative) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/stores/${storeId}/inventory/adjust`, {
        method: "POST",
        body: { variant_id: variant.id, quantity_change: change, reason: reason.trim() || null },
      });
      onDone(`Stock ${mode === "add" ? "increased" : "decreased"} by ${amount} (now ${after})`);
    } catch (e) {
      onError((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Adjust stock" onClose={onClose}>
      <p className="text-sm font-medium">{product.title}</p>
      <p className="mb-4 text-xs text-slate-400">
        {variant.title} · currently <span className="font-semibold text-slate-200">{variant.inventory_quantity}</span> in stock
      </p>
      <div className="mb-3 grid grid-cols-2 gap-2">
        {(["add", "remove"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-xl border px-3 py-2 text-sm font-medium ${
              mode === m
                ? m === "add"
                  ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
                  : "border-rose-400/50 bg-rose-500/15 text-rose-200"
                : "border-white/10 text-slate-300 hover:bg-white/5"
            }`}
          >
            {m === "add" ? "+ Add stock" : "− Remove stock"}
          </button>
        ))}
      </div>
      <div className="space-y-3">
        <Field label="Quantity">
          <input className={inputCls} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} autoFocus />
        </Field>
        <Field label="Reason (optional)" hint="Shown in the stock history.">
          <input className={inputCls} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Supplier delivery, damaged goods" />
        </Field>
      </div>
      <p className={`mt-3 text-sm ${negative ? "text-rose-300" : "text-slate-400"}`}>
        {negative ? "Not enough stock to remove that many." : valid ? `New stock level: ${after}` : "Enter a quantity greater than 0."}
      </p>
      <div className="mt-4 flex justify-end gap-2">
        <Btn variant="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn onClick={submit} loading={busy} disabled={!valid || negative}>
          Apply
        </Btn>
      </div>
    </Modal>
  );
}
