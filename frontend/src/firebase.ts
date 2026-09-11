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
