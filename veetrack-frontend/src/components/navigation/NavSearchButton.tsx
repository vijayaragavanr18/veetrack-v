"use client";

import { Search } from "lucide-react";

interface NavSearchButtonProps {
  onClick: () => void;
}

export default function NavSearchButton({ onClick }: NavSearchButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center w-14 h-14 rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/30 hover:bg-primary/90 active:scale-95 transition-all duration-150"
      aria-label="Open search"
    >
      <Search className="h-6 w-6" strokeWidth={2} aria-hidden />
    </button>
  );
}
