import { useState } from "react";
import { api, execute } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

type Product = {
  id: string;
  title: string;
  status: string;
  vendor: string | null;
  product_type: string | null;
  variants?: { id: string; title: string; inventory_quantity: number; sku: string | null }[];
  created_at?: string;
};

export default function Products() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [items, setItems] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);

  const load = async () => {
    setLoading(true);
    setResult(null);
    const r = await execute<{ items: Product[]; total: number }>(() => api.get("/inventory"));
    setResult(r);
    if (r.ok && r.data) {
      setItems(r.data.items ?? []);
      setTotal(r.data.total ?? 0);
    }
    setLoading(false);
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold">Products</h2>
        <button
          onClick={load}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Load Products
        </button>
      </div>
      <p className="text-xs text-gray-500">GET /inventory (requires auth)</p>
      {!loading && items.length > 0 && (
        <div className="mt-3 overflow-auto rounded border bg-white">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-200">
              <tr>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Vendor</th>
                <th className="px-3 py-2">Variants</th>
                <th className="px-3 py-2">ID</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-t">
                  <td className="px-3 py-2 font-medium">{p.title}</td>
                  <td className="px-3 py-2">{p.status}</td>
                  <td className="px-3 py-2">{p.vendor ?? "—"}</td>
                  <td className="px-3 py-2">
                    {(p.variants ?? []).map((v) => `${v.title} (${v.inventory_quantity})`).join(", ") ||
                      "0"}
                  </td>
                  <td className="px-3 py-2 font-mono text-gray-500">{p.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="bg-gray-100 px-3 py-2 text-gray-600">Total: {total} product(s)</div>
        </div>
      )}
      <ResultPanel loading={loading} result={result} />
    </div>
  );
}
