import { useState } from "react";
import type { FormEvent } from "react";
import { api, execute } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

const field =
  "w-full rounded border border-gray-300 px-3 py-2 text-sm";
const label = "mb-1 block text-sm font-medium";

export default function Inventory() {
  // List
  const [listLoading, setListLoading] = useState(false);
  const [listResult, setListResult] = useState<any>(null);
  const [listCount, setListCount] = useState<number | null>(null);

  // Create
  const [createForm, setCreateForm] = useState({
    title: "",
    description: "",
    price: "19.99",
    inventory_quantity: "10",
    status: "active",
  });
  const [createLoading, setCreateLoading] = useState(false);
  const [createResult, setCreateResult] = useState<any>(null);

  // Update / Delete
  const [targetId, setTargetId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [mutLoading, setMutLoading] = useState(false);
  const [mutResult, setMutResult] = useState<any>(null);

  const load = async () => {
    setListLoading(true);
    setListResult(null);
    const r = await execute<{ total: number }>(() => api.get("/inventory"));
    setListResult(r);
    setListCount(r.ok && r.data ? r.data.total : null);
    setListLoading(false);
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setCreateLoading(true);
    setCreateResult(null);
    const payload = {
      title: createForm.title,
      description: createForm.description || null,
      status: createForm.status,
      variants: [
        {
          title: "Default",
          price: createForm.price,
          inventory_quantity: Number(createForm.inventory_quantity),
        },
      ],
    };
    const r = await execute(() => api.post("/inventory", payload));
    setCreateResult(r);
    setCreateLoading(false);
  };

  const update = async () => {
    if (!targetId) return;
    setMutLoading(true);
    setMutResult(null);
    const r = await execute(() => api.put(`/inventory/${targetId}`, { title: newTitle }));
    setMutResult(r);
    setMutLoading(false);
  };

  const remove = async () => {
    if (!targetId) return;
    setMutLoading(true);
    setMutResult(null);
    const r = await execute(() => api.delete(`/inventory/${targetId}`));
    setMutResult(r);
    setMutLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Inventory</h2>
        <button
          onClick={load}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Load Products
        </button>
      </div>
      {listCount !== null && (
        <p className="text-xs text-gray-600">Total products: {listCount}</p>
      )}
      <ResultPanel loading={listLoading} result={listResult} />

      <section className="rounded border bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-lg font-semibold">Create Product</h3>
        <form onSubmit={create} className="grid grid-cols-2 gap-3">
          <div>
            <label className={label}>Title *</label>
            <input
              required
              value={createForm.title}
              onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
              className={field}
            />
          </div>
          <div>
            <label className={label}>Status</label>
            <select
              value={createForm.status}
              onChange={(e) => setCreateForm({ ...createForm, status: e.target.value })}
              className={field}
            >
              <option>active</option>
              <option>draft</option>
              <option>archived</option>
            </select>
          </div>
          <div>
            <label className={label}>Description</label>
            <input
              value={createForm.description}
              onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
              className={field}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={label}>Price</label>
              <input
                value={createForm.price}
                onChange={(e) => setCreateForm({ ...createForm, price: e.target.value })}
                className={field}
              />
            </div>
            <div>
              <label className={label}>Qty</label>
              <input
                value={createForm.inventory_quantity}
                onChange={(e) =>
                  setCreateForm({ ...createForm, inventory_quantity: e.target.value })
                }
                className={field}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={createLoading}
            className="rounded bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-500 disabled:opacity-50"
          >
            {createLoading ? "Creating..." : "Create Product"}
          </button>
        </form>
        <p className="mt-2 text-xs text-gray-500">POST /inventory</p>
        <ResultPanel loading={createLoading} result={createResult} />
      </section>

      <section className="rounded border bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-lg font-semibold">Update / Delete Product</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-80">
            <label className={label}>Product ID</label>
            <input
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className={field}
            />
          </div>
          <div className="w-56">
            <label className={label}>New title</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className={field}
            />
          </div>
          <button
            onClick={update}
            disabled={mutLoading || !targetId}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Update
          </button>
          <button
            onClick={remove}
            disabled={mutLoading || !targetId}
            className="rounded bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-500">{"PUT /inventory/{product_id} · DELETE /inventory/{product_id}"}</p>
        <ResultPanel loading={mutLoading} result={mutResult} />
      </section>
    </div>
  );
}
