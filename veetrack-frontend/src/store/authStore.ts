"use client";

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import type { AuthUser } from "@/features/auth/api/authApi";

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
}

interface AuthActions {
  setAuth: (user: AuthUser, accessToken: string) => void;
  setToken: (accessToken: string) => void;
  clearAuth: () => void;
}

// Cookie helper — sets/clears a simple session marker that middleware can read.
// The real JWT lives in memory (accessToken). The cookie only signals "logged in"
// so Next.js middleware can do server-side redirects without exposing the token.
function setSessionCookie(value: string | null) {
  if (typeof document === "undefined") return;
  if (value) {
    document.cookie = "vt_session=1; path=/; SameSite=Lax; Max-Age=86400";
  } else {
    document.cookie = "vt_session=; path=/; Max-Age=0";
  }
}

export const useAuthStore = create<AuthState & AuthActions>()(
  devtools(
    persist(
      (set) => ({
        user: null,
        accessToken: null,

        setAuth: (user, accessToken) => {
          setSessionCookie("1");
          set({ user, accessToken }, false, "setAuth");
        },

        setToken: (accessToken) =>
          set({ accessToken }, false, "setToken"),

        clearAuth: () => {
          setSessionCookie(null);
          set({ user: null, accessToken: null }, false, "clearAuth");
        },
      }),
      {
        name: "veetrack-auth",
        // Only persist user metadata — access token is re-obtained via refresh cookie
        partialize: (state) => ({ user: state.user }),
      },
    ),
    { name: "AuthStore" },
  ),
);
