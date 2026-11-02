import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, settings, type User } from "./api";

interface SessionCtx {
  token: string | null;
  user: User | null;
  storeId: number | null;
  ready: boolean;
  login: (token: string) => void;
  logout: () => void;
  setStoreId: (id: number | null) => void;
}

const Ctx = createContext<SessionCtx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [storeId, setStore] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setToken(settings.getToken());
    setStore(settings.getStoreId());
    setReady(true);
    const onAuth = () => setToken(settings.getToken());
    window.addEventListener("qc-auth", onAuth);
    return () => window.removeEventListener("qc-auth", onAuth);
  }, []);

  const me = useQuery({
    queryKey: ["me", token],
    queryFn: () => api<User>("/me"),
    enabled: !!token,
    retry: false,
  });

  const login = useCallback((t: string) => {
    settings.setToken(t);
    setToken(t);
    qc.invalidateQueries();
  }, [qc]);
  const logout = useCallback(() => {
    settings.setToken(null);
    setToken(null);
    qc.clear();
  }, [qc]);
  const setStoreId = useCallback((id: number | null) => {
    settings.setStoreId(id);
    setStore(id);
  }, []);

  return (
    <Ctx.Provider value={{ token, user: me.data ?? null, storeId, ready, login, logout, setStoreId }}>
      {children}
    </Ctx.Provider>
  );
}

export function useSession() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useSession outside provider");
  return c;
}
