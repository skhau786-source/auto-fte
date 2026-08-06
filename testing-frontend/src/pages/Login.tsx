import { useState } from "react";
import type { FormEvent } from "react";
import { api, execute } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    const r = await execute(() => api.post("/auth/login", { email, password }));
    setResult(r);
    setLoading(false);
  };

  return (
    <div className="mx-auto max-w-md">
      <h2 className="mb-4 text-xl font-bold">Login</h2>
      <form onSubmit={submit} className="space-y-3 rounded border bg-white p-4 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Password</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            placeholder="••••••••"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? "Logging in..." : "Login"}
        </button>
      </form>
      <p className="mt-2 text-xs text-gray-500">
        POST /auth/login — note: this backend currently returns no access token, so protected pages
        will show 401 unless you paste a token in the header.
      </p>
      <ResultPanel loading={loading} result={result} />
    </div>
  );
}
