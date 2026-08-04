"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api, AUTH_REQUIRED_EVENT } from "@/lib/api";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const replace = router.replace;
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const redirectToLogin = () => replace("/login");
    window.addEventListener(AUTH_REQUIRED_EVENT, redirectToLogin);

    async function restoreSession() {
      try {
        await api.auth.me();
      } catch {
        try {
          await api.auth.refresh();
        } catch {
          if (active) replace("/login");
          return;
        }
      }
      if (active) setReady(true);
    }

    restoreSession();
    return () => {
      active = false;
      window.removeEventListener(AUTH_REQUIRED_EVENT, redirectToLogin);
    };
  }, [replace]);

  if (!ready) {
    return (
      <main className="auth-loading" aria-label="正在恢复会话">
        <Loader2 className="animate-spin" size={24} aria-hidden="true" />
      </main>
    );
  }

  return children;
}
