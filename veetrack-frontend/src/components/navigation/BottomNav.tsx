"use client";

import { usePathname, useRouter } from "next/navigation";
import { Home, Compass, Bell, User } from "lucide-react";
import NavSearchButton from "./NavSearchButton";

const NAV_ITEMS = [
  { key: "home",     href: "/feed",      icon: Home,    label: "Home" },
  { key: "discover", href: "/discover",  icon: Compass, label: "Discover" },
  { key: "search",   href: null,         icon: null,    label: "Search" }, // center FAB
  { key: "alerts",   href: "/alerts",    icon: Bell,    label: "Alerts" },
  { key: "profile",  href: "/profile",   icon: User,    label: "Profile" },
] as const;

interface BottomNavProps {
  onSearchOpen: () => void;
  unreadAlerts?: number;
}

export default function BottomNav({ onSearchOpen, unreadAlerts = 0 }: BottomNavProps) {
  const pathname = usePathname();
  const router = useRouter();

  function isActive(href: string | null): boolean {
    if (!href) return false;
    return pathname.startsWith(href);
  }

  return (
    <nav
      className="shrink-0 h-16 w-full border-t border-border bg-background/95 backdrop-blur-sm flex items-end justify-around px-2 pb-2 z-20"
      aria-label="Main navigation"
    >
      {NAV_ITEMS.map((item) => {
        // Center slot — Search FAB, elevated above the bar
        if (item.key === "search") {
          return (
            <div key="search" className="relative flex flex-col items-center -mt-7">
              <NavSearchButton onClick={onSearchOpen} />
              <span className="mt-1 text-[10px] text-muted-foreground font-medium leading-none">
                Search
              </span>
            </div>
          );
        }

        const Icon = item.icon;
        const active = isActive(item.href);

        return (
          <button
            key={item.key}
            onClick={() => router.push(item.href!)}
            className={`flex flex-col items-center gap-1 min-w-[44px] py-1 transition-colors ${
              active ? "text-primary" : "text-muted-foreground hover:text-foreground"
            }`}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
          >
            <div className="relative">
              <Icon
                className="h-5 w-5"
                strokeWidth={active ? 2.5 : 1.8}
                fill={active ? "currentColor" : "none"}
                aria-hidden
              />
              {item.key === "alerts" && unreadAlerts > 0 && (
                <span className="absolute -top-1 -right-1.5 min-w-[14px] h-3.5 px-0.5 rounded-full bg-destructive text-destructive-foreground text-[9px] font-bold flex items-center justify-center leading-none">
                  {unreadAlerts > 9 ? "9+" : unreadAlerts}
                </span>
              )}
            </div>
            <span className="text-[10px] font-medium leading-none">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
