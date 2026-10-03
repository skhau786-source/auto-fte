"use client";

import { useEffect, useState } from "react";
import SupportChatWidget from "../components/SupportChatWidget";

/** Customer-facing chat page: /chat?store=<store id>. The widget can also be embedded elsewhere. */
export default function ChatPage() {
  const [storeId, setStoreId] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setStoreId(new URLSearchParams(window.location.search).get("store"));
  }, []);

  return (
    <main className="mx-auto max-w-xl px-4 py-16 text-slate-800">
      <h1 className="text-2xl font-semibold">Customer support chat</h1>
      {storeId === undefined ? null : storeId ? (
        <>
          <p className="mt-2 text-sm text-slate-600">
            Use the chat bubble at the bottom right. Ask in English or Roman Urdu about prices, stock and orders, or
            ask to talk to the owner.
          </p>
          <SupportChatWidget storeId={storeId} storeName="Store support" startOpen />
        </>
      ) : (
        <p className="mt-2 text-sm text-red-600">
          Missing store. Open this page as <code>/chat?store=&lt;store id&gt;</code>. Store owners can find their id
          in <a className="underline" href="/chat/inbox">the inbox</a>.
        </p>
      )}
    </main>
  );
}
