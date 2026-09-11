/** Auth layer.
 *
 * Live mode: Firebase Authentication (Google sign-in); the Firebase SDK is
 * loaded lazily so the demo bundle path never touches it.
 * Demo mode: one click into a seeded workspace; the backend maps the demo
 * token to a fixed uid.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, setTokenProvider } from "./api";
import type { AppConfig } from "./types";

export interface SessionUser {
  name: string;
  email: string;
  photo?: string;
}

interface AuthState {
  config: AppConfig | null;
  user: SessionUser | null;
  ready: boolean;
  error: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

const DEMO_USER: SessionUser = { name: "Shivam Gupta", email: "demo@offerloop.dev" };
const DEMO_FLAG = "offerloop.demo.signedIn";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.config();
        if (cancelled) return;
        setConfig(cfg);
        if (cfg.mode === "demo") {
          setTokenProvider(async () => "demo");
          if (sessionStorage.getItem(DEMO_FLAG)) setUser(DEMO_USER);
          setReady(true);
        } else {
          const { initFirebase } = await import("./firebase");
          const unsubscribe = await initFirebase(cfg.firebase, (firebaseUser) => {
            setUser(firebaseUser);
            setReady(true);
          });
          return unsubscribe;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to reach the OfferLoop API");
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async () => {
    if (!config) return;
    if (config.mode === "demo") {
      sessionStorage.setItem(DEMO_FLAG, "1");
      setUser(DEMO_USER);
      return;
    }
    const { signInWithGoogle } = await import("./firebase");
    await signInWithGoogle();
  }, [config]);

  const signOut = useCallback(async () => {
    if (config?.mode === "demo") {
      sessionStorage.removeItem(DEMO_FLAG);
      setUser(null);
      return;
    }
    const { firebaseSignOut } = await import("./firebase");
    await firebaseSignOut();
  }, [config]);

  const value = useMemo(
    () => ({ config, user, ready, error, signIn, signOut }),
    [config, user, ready, error, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
