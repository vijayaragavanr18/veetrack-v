"use client";

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { AuthUser } from "@/features/auth/api/authApi";

interface AuthState {
  user: AuthUser | null;
  /** Access token stored in memory only — never persisted to localStorage. */
  accessToken: string | null;
}

interface AuthActions {
  setAuth: (user: AuthUser, accessToken: string) => void;
  setToken: (accessToken: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  devtools(
    (set) => ({
      user: null,
      accessToken: null,
      setAuth: (user, accessToken) =>
        set({ user, accessToken }, false, "setAuth"),
      setToken: (accessToken) =>
        set({ accessToken }, false, "setToken"),
      clearAuth: () =>
        set({ user: null, accessToken: null }, false, "clearAuth"),
    }),
    { name: "AuthStore" },
  ),
);
