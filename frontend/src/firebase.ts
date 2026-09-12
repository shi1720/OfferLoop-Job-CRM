/** Firebase Authentication glue — imported dynamically in live mode only. */

import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  type Auth,
} from "firebase/auth";

import { setTokenProvider } from "./api";
import type { SessionUser } from "./auth";

let auth: Auth | null = null;

export async function initFirebase(
  config: Record<string, string>,
  onUser: (user: SessionUser | null) => void,
): Promise<() => void> {
  const app = initializeApp(config);
  auth = getAuth(app);

  setTokenProvider(async () => {
    const current = auth?.currentUser;
    if (!current) throw new Error("Not signed in");
    return current.getIdToken();
  });

  return onAuthStateChanged(auth, (firebaseUser) => {
    onUser(
      firebaseUser
        ? {
            name: firebaseUser.displayName ?? firebaseUser.email ?? "You",
            email: firebaseUser.email ?? "",
            photo: firebaseUser.photoURL ?? undefined,
          }
        : null,
    );
  });
}

export async function signInWithGoogle(): Promise<void> {
  if (!auth) throw new Error("Firebase not initialized");
  await signInWithPopup(auth, new GoogleAuthProvider());
}

export async function firebaseSignOut(): Promise<void> {
  if (!auth) return;
  await signOut(auth);
}

// ---------------------------------------------------------------------------
// Web push (FCM) — live mode only, and only when the server exposes a VAPID key
// ---------------------------------------------------------------------------

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window && "serviceWorker" in navigator;
}

/** Ask permission, register the messaging service worker (config travels in
 * the registration URL), and return this browser's FCM token. */
export async function enableWebPush(config: Record<string, string>, vapidKey: string): Promise<string> {
  const { getApp } = await import("firebase/app");
  const { getMessaging, getToken } = await import("firebase/messaging");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notifications are blocked for this site — allow them in your browser settings and retry.");
  }
  const encoded = encodeURIComponent(btoa(JSON.stringify(config)));
  const registration = await navigator.serviceWorker.register(`/firebase-messaging-sw.js?config=${encoded}`);
  const messaging = getMessaging(getApp());
  const token = await getToken(messaging, { vapidKey, serviceWorkerRegistration: registration });
  if (!token) throw new Error("Couldn't get a push token — try again in a moment.");
  return token;
}
