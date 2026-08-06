import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { getToken, setToken, clearToken } from "../lib/api";

const links = [
  { to: "/login", label: "Login" },
  { to: "/register", label: "Register" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/products", label: "Products" },
  { to: "/inventory", label: "Inventory" },
  { to: "/orders", label: "Orders" },
  { to: "/health", label: "API Health" },
];

export default function Layout() {
  const [tokenInput, setTokenInput] = useState(getToken());
  const [saved, setSaved] = useState(false);

  const saveToken = () => {
    setToken(tokenInput.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-slate-800 text-white shadow">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
          <h1 className="text-base font-bold">Digital FTE · API Testing</h1>
          <nav className="flex flex-wrap gap-1">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `rounded px-2.5 py-1 text-sm ${
                    isActive ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-700"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 pb-3">
          <span className="text-xs text-slate-400">Bearer token:</span>
          <input
            type="text"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="paste a JWT (backend currently issues none)"
            className="w-72 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white placeholder-slate-500"
          />
          <button
            onClick={saveToken}
            className="rounded bg-blue-600 px-2 py-1 text-xs font-medium hover:bg-blue-500"
          >
            Save
          </button>
          <button
            onClick={() => {
              clearToken();
              setTokenInput("");
            }}
            className="rounded bg-slate-600 px-2 py-1 text-xs font-medium hover:bg-slate-500"
          >
            Clear
          </button>
          {saved && <span className="text-xs text-green-400">Token saved ✓</span>}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
