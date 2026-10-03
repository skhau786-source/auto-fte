"use client";

import { useEffect, useState } from "react";
import { tokenStore } from "@/lib/api";
import SupportChatWidget from "./SupportChatWidget";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const POLL_MS = 30_000;

type StoreRow = { id: string; shopify_domain: string };

/**
 * Support chat for the logged-in owner's dashboard.
 * - Shows the same chat customers see (a live preview, so the owner can try it).
 * - Shows how many customers asked for a human, linking to the inbox.
 * Renders nothing until the owner has a connected store.
 */
export default function DashboardChatWidget() {
  const [store, setStore] = useState<StoreRow | null>(null);
  const [waiting, setWaiting] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function call<T>(path: string): Promise<T | null> {
      const token = tokenStore.get();
      if (!token) return null;
      try {
        const res = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
        return res.ok ? ((await res.json()) as T) : null;
      } catch {
        return null; // backend unreachable: the dashboard keeps working without the widget
      }
    }

    async function refreshWaiting() {
      const open = await call<unknown[]>("/support-chat/handoffs?status=open");
      if (!cancelled && open) setWaiting(open.length);
    }

    (async () => {
      const stores = await call<StoreRow[]>("/support-chat/my-stores");
      if (cancelled || !stores || stores.length === 0) return;
      setStore(stores[0]);
      await refreshWaiting();
      timer = setInterval(refreshWaiting, POLL_MS);
    })();

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, []);

  if (!store) return null;

  return (
    <>
      <a
        href="/chat/inbox"
        className="fixed bottom-5 right-24 z-50 rounded-full border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-700 shadow-lg hover:bg-violet-50"
        aria-label={`Customer chat inbox, ${waiting} waiting`}
      >
        {waiting > 0 ? `${waiting} customer${waiting === 1 ? "" : "s"} waiting` : "Chat inbox"}
      </a>
      <SupportChatWidget storeId={store.id} storeName={`${store.shopify_domain} (preview)`} />
    </>
  );
}
