import { useState } from "react";
import type { FormEvent } from "react";
import { api, execute } from "../lib/api";
import ResultPanel from "../components/ResultPanel";

export default function Register() {
  const [form, setForm] = useState({
    full_name: "",
    username: "",
    email: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    const r = await execute(() => api.post("/auth/signup", form));
    setResult(r);
    setLoading(false);
  };

  return (
    <div className="mx-auto max-w-md">
      <h2 className="mb-4 text-xl font-bold">Register</h2>
      <form onSubmit={submit} className="space-y-3 rounded border bg-white p-4 shadow-sm">
        {(
          [
            ["full_name", "Name", "John Doe"],
            ["username", "Username", "johndoe"],
            ["email", "Email", "john@example.com"],
            ["password", "Password (min 8, 1 digit, 1 uppercase)", "Passw0rd!"],
          ] as const
        ).map(([key, label, ph]) => (
          <div key={key}>
            <label className="mb-1 block text-sm font-medium">{label}</label>
            <input
              type={key === "password" ? "password" : key === "email" ? "email" : "text"}
              required={key !== "full_name"}
              value={form[key]}
              onChange={set(key)}
              placeholder={ph}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
        ))}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-500 disabled:opacity-50"
        >
          {loading ? "Registering..." : "Register"}
        </button>
      </form>
      <p className="mt-2 text-xs text-gray-500">POST /auth/signup</p>
      <ResultPanel loading={loading} result={result} />
    </div>
  );
}
