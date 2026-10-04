"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Boxes, BookOpen, Home, LogIn } from "lucide-react";
import { getToken } from "../../lib/api";
import { Card } from "./ui";

const TABS = [
  { href: "/inventory", label: "Inventory", icon: Boxes },
  { href: "/knowledge-base", label: "Knowledge Base", icon: BookOpen },
];

// Header + login guard shared by /inventory and /knowledge-base.
export function WorkspaceShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname() || "";
  const [authState, setAuthState] = useState<"checking" | "in" | "out">("checking");

  useEffect(() => {
    setAuthState(getToken() ? "in" : "out");
  }, []);

  return (
    <div className="dark min-h-screen text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#050b1a]/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-400 text-sm font-extrabold text-slate-900">
                F
              </span>
              <span className="hidden text-sm font-bold sm:block">Digital FTE</span>
            </Link>
            <nav className="flex items-center gap-1">
              {TABS.map(({ href, label, icon: Icon }) => {
                const active = pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                      active ? "bg-amber-400/15 text-amber-300" : "text-slate-300 hover:bg-white/5"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-100">
            <Home className="h-4 w-4" />
            <span className="hidden sm:inline">Dashboard</span>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-32 pt-6">
        <div className="mb-5">
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
        </div>

        {authState === "checking" && null}
        {authState === "out" && (
          <Card className="mx-auto mt-10 max-w-md p-8 text-center">
            <LogIn className="mx-auto h-8 w-8 text-amber-300" />
            <p className="mt-3 font-semibold">Please log in first</p>
            <p className="mt-1 text-sm text-slate-400">This page needs your Digital FTE account.</p>
            <Link
              href="/"
              className="mt-4 inline-block rounded-xl bg-amber-400 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-amber-300"
            >
              Go to login
            </Link>
          </Card>
        )}
        {authState === "in" && children}
      </main>
    </div>
  );
}
