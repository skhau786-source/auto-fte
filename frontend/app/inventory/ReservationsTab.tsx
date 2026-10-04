"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Badge, Btn, Card, Empty, Field, Modal, Spinner, fmtDate, inputCls } from "../components/workspace/ui";
import { apiFetch, ApiError, ProductRow, Reservation, VariantLabelMap } from "../lib/api";

interface Props {
  storeId: number;
  version: number;
  products: ProductRow[];
  variantLabels: VariantLabelMap;
  toast: (kind: "ok" | "err", text: string) => void;
  onChange: () => void;
}

const STATUSES = ["", "active", "committed", "released", "expired", "cancelled"];

export function ReservationsTab({ storeId, version, products, variantLabels, toast, onChange }: Props) {
  const [status, setStatus] = useState("active");
  const [items, setItems] = useState<Reservation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = new URLSearchParams({ page_size: "50" });
    if (status) qs.set("status", status);
    apiFetch<{ items: Reservation[]; total: number }>(`/api/v1/stores/${storeId}/reservations?${qs}`)
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
  }, [storeId, status, version, toast]);

  const act = async (r: Reservation, action: "commit" | "release" | "expire") => {
    setBusyId(r.id);
    try {
      await apiFetch(`/api/v1/stores/${storeId}/reservations/${r.id}/${action}`, { method: "POST" });
      toast("ok", action === "commit" ? "Reservation committed" : `Reservation ${action === "release" ? "released" : "expired"} — stock restored`);
      onChange();
    } catch (e) {
      toast("err", (e as ApiError).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <select aria-label="Reservation status" value={status} onChange={(e) => setStatus(e.target.value)} className={`${inputCls} !w-auto capitalize`}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s ? s : "All statuses"}
              </option>
            ))}
          </select>
          <span className="text-xs text-slate-500">{total} total</span>
        </div>
        <Btn onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New reservation
        </Btn>
      </div>

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Empty title="No reservations" text="Reserve stock for an order to hold it until it is committed, released or expires." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Item</th>
                <th className="py-2 pr-3 font-medium">Order</th>
                <th className="py-2 pr-3 text-right font-medium">Qty</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Expires</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((r) => (
                <tr key={r.id}>
                  <td className="max-w-[260px] truncate py-2.5 pr-3">{variantLabels[r.variant_id] || `Variant ${r.variant_id}`}</td>
                  <td className="py-2.5 pr-3 text-xs text-slate-400">
                    {r.order_id || "—"}
                    <span className="ml-1 text-slate-600">· {r.order_source}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">{r.quantity}</td>
                  <td className="py-2.5 pr-3">
                    <Badge tone={r.status}>{r.status}</Badge>
                  </td>
                  <td className="py-2.5 pr-3 text-xs text-slate-400">{fmtDate(r.expires_at)}</td>
                  <td className="py-2.5 text-right">
                    {r.status === "active" && (
                      <div className="flex justify-end gap-1.5">
                        <Btn variant="ghost" loading={busyId === r.id} onClick={() => act(r, "commit")}>
                          Commit
                        </Btn>
                        <Btn variant="danger" disabled={busyId === r.id} onClick={() => act(r, "release")}>
                          Release
                        </Btn>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <CreateModal
          storeId={storeId}
          products={products}
          onClose={() => setCreating(false)}
          onDone={() => {
            toast("ok", "Stock reserved");
            setCreating(false);
            onChange();
          }}
          onError={(m) => toast("err", m)}
        />
      )}
    </Card>
  );
}

function CreateModal({
  storeId,
  products,
  onClose,
  onDone,
  onError,
}: {
  storeId: number;
  products: ProductRow[];
  onClose: () => void;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const options = products.flatMap((p) => p.variants.map((v) => ({ id: v.id, label: `${p.title} — ${v.title}${v.sku ? ` (${v.sku})` : ""}`, stock: v.inventory_quantity })));
  const [variantId, setVariantId] = useState<number | "">(options[0]?.id ?? "");
  const [qty, setQty] = useState("1");
  const [orderId, setOrderId] = useState("");
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);

  const selected = options.find((o) => o.id === variantId);
  const amount = Math.floor(Number(qty));
  const valid = variantId !== "" && Number.isFinite(amount) && amount > 0 && (!expires || Number(expires) > 0);
  const tooMany = !!selected && amount > selected.stock;

  const submit = async () => {
    if (!valid || tooMany) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/stores/${storeId}/reservations`, {
        method: "POST",
        body: {
          variant_id: variantId,
          quantity: amount,
          order_id: orderId.trim() || null,
          expires_in_minutes: expires ? Math.floor(Number(expires)) : null,
        },
      });
      onDone();
    } catch (e) {
      onError((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <Modal title="New reservation" onClose={onClose}>
      {options.length === 0 ? (
        <Empty title="No variants to reserve" text="Sync products first." />
      ) : (
        <div className="space-y-3">
          <Field label="Item">
            <select className={inputCls} value={variantId} onChange={(e) => setVariantId(Number(e.target.value))}>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label} · {o.stock} in stock
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Quantity">
              <input className={inputCls} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
            </Field>
            <Field label="Expires in (minutes)" hint="Leave empty for no expiry.">
              <input className={inputCls} type="number" min={1} value={expires} onChange={(e) => setExpires(e.target.value)} />
            </Field>
          </div>
          <Field label="Order ID (optional)" hint="One active reservation per item and order.">
            <input className={inputCls} value={orderId} onChange={(e) => setOrderId(e.target.value)} placeholder="e.g. #1042" />
          </Field>
          {tooMany && <p className="text-sm text-rose-300">Only {selected?.stock} in stock.</p>}
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Btn variant="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn onClick={submit} loading={busy} disabled={!valid || tooMany || options.length === 0}>
          Reserve
        </Btn>
      </div>
    </Modal>
  );
}
