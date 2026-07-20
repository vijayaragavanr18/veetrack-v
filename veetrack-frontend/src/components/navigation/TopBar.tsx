"use client";

import { useRouter } from "next/navigation";
import { ChevronLeft, MoreVertical } from "lucide-react";
import { useState, useRef, useEffect } from "react";

interface TopBarAction {
  label: string;
  onClick: () => void;
}

interface TopBarProps {
  title: string;
  showBack?: boolean;
  actions?: TopBarAction[];
}

export default function TopBar({ title, showBack = false, actions = [] }: TopBarProps) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [menuOpen]);

  return (
    <div className="shrink-0 h-11 flex items-center justify-between px-3 bg-background/95 backdrop-blur-sm border-b border-border/40">
      {/* Left */}
      <div className="w-9 flex items-center">
        {showBack && (
          <button
            onClick={() => router.back()}
            className="text-muted-foreground hover:text-foreground transition-colors p-1 -ml-1"
            aria-label="Go back"
          >
            <ChevronLeft className="h-5 w-5" aria-hidden />
          </button>
        )}
      </div>

      {/* Center */}
      <span className="text-sm font-semibold text-foreground truncate max-w-[180px]">
        {title}
      </span>

      {/* Right — overflow menu */}
      <div className="w-9 flex items-center justify-end relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="text-muted-foreground hover:text-foreground transition-colors p-1 -mr-1"
          aria-label="More options"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
        >
          <MoreVertical className="h-5 w-5" aria-hidden />
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute top-full right-0 mt-1 w-44 rounded-lg border border-border bg-popover text-popover-foreground shadow-lg z-50 py-1 overflow-hidden"
          >
            {actions.length > 0 ? (
              actions.map((a) => (
                <button
                  key={a.label}
                  role="menuitem"
                  className="w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors"
                  onClick={() => { a.onClick(); setMenuOpen(false); }}
                >
                  {a.label}
                </button>
              ))
            ) : (
              <span className="block px-4 py-2.5 text-sm text-muted-foreground">
                No actions available
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
