"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  GoogleAuthProvider,
  signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { getFirebaseAuth } from "./firebase";
import { type GestoriaProfile, fetchGestoriaProfile } from "./api";

const googleProvider = new GoogleAuthProvider();

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  gestoria: GestoriaProfile | null;
  gestoriaLoading: boolean;
  refreshGestoria: () => Promise<void>;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [gestoria, setGestoria] = useState<GestoriaProfile | null>(null);
  const [gestoriaLoading, setGestoriaLoading] = useState(false);

  const loadGestoria = useCallback(async () => {
    setGestoriaLoading(true);
    try {
      const profile = await fetchGestoriaProfile();
      setGestoria(profile);
    } catch {
      setGestoria(null);
    } finally {
      setGestoriaLoading(false);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(getFirebaseAuth(), (u) => {
      setUser(u);
      setLoading(false);
      if (!u) {
        setGestoria(null);
      }
    });
    return unsubscribe;
  }, []);

  // Fetch gestoría profile once user is authenticated
  useEffect(() => {
    if (user && !loading) {
      loadGestoria();
    }
  }, [user, loading, loadGestoria]);

  async function signIn() {
    await signInWithPopup(getFirebaseAuth(), googleProvider);
  }

  async function signOut() {
    await fbSignOut(getFirebaseAuth());
    setGestoria(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, gestoria, gestoriaLoading, refreshGestoria: loadGestoria, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
