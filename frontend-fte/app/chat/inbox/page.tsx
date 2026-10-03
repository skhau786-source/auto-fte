"use client";

import { useCallback, useState } from "react";
import { buildApiUrl } from "../../lib/config";

type Handoff = {
  id: string;
  store_id: string;
  customer_name: string | null;
  customer_contact: string | null;
  message: string;
  language: string;
  status: string;
  created_at: string;
};
type StoreRow = { id: string; shopify_domain: string };

/** Owner inbox: customers who asked for a human. Logs in with the normal /auth/login. */
export default function InboxPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [stores, setStores] = useState<StoreRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (tk: string) => {
    const headers = { Authorization: `Bearer ${tk}` };
    const [h, s] = await Promise.all([
      fetch(buildApiUrl("/support-chat/handoffs?status=open"), { headers }),
      fetch(buildApiUrl("/support-chat/my-stores"), { headers }),
    ]);
    if (!h.ok || !s.ok) throw new Error("Could not load your inbox");
    setHandoffs(await h.json());
    setStores(await s.json());
  }, []);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await fetch(buildApiUrl("/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok || !data.access_token) throw new Error(data?.detail || "Login failed");
      setToken(data.access_token);
      await load(data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function resolve(id: string) {
    if (!token) return;
    setError(null);
    try {
      const res = await fetch(buildApiUrl(`/support-chat/handoffs/${id}/resolve`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Could not resolve");
      await load(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resolve");
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-12 text-slate-800">
      <h1 className="text-2xl font-semibold">Support inbox</h1>

      {!token ? (
        <form onSubmit={login} className="mt-6 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            aria-label="Email"
            className="w-full rounded border border-slate-300 px-3 py-2"
          />
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            aria-label="Password"
            className="w-full rounded border border-slate-300 px-3 py-2"
          />
          <button className="rounded bg-violet-600 px-4 py-2 text-white">Sign in</button>
        </form>
      ) : (
        <>
          <section className="mt-6">
            <h2 className="text-sm font-semibold uppercase text-slate-500">Your chat links</h2>
            {stores.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No store connected to this account yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {stores.map((s) => (
                  <li key={s.id}>
                    {s.shopify_domain}:{" "}
                    <a className="text-violet-700 underline" href={`/chat?store=${s.id}`}>
                      /chat?store={s.id}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-sm font-semibold uppercase text-slate-500">Customers waiting ({handoffs.length})</h2>
            {handoffs.length === 0 && <p className="mt-2 text-sm text-slate-500">Nobody is waiting.</p>}
            <ul className="mt-2 space-y-3">
              {handoffs.map((h) => (
                <li key={h.id} className="rounded border border-slate-200 bg-white p-3">
                  <p className="text-sm">&ldquo;{h.message}&rdquo;</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {new Date(h.created_at).toLocaleString()} · {h.language === "ur" ? "Roman Urdu" : "English"} ·{" "}
                    {h.customer_contact ? `contact: ${h.customer_contact}` : "no contact left"}
                  </p>
                  <button onClick={() => resolve(h.id)} className="mt-2 rounded border border-violet-300 px-3 py-1 text-xs text-violet-700">
                    Mark resolved
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
      {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}
    </main>
  );
}
