"use client";

import { useState } from "react";
import { Heart, MessageCircle, Bookmark, Share2, Check } from "lucide-react";

interface EngagementRowProps {
  onSave?: () => void;
  isSaved?: boolean;
  articleUrl?: string;
  headline?: string;
}

export default function EngagementRow({ onSave, isSaved = false, articleUrl, headline }: EngagementRowProps) {
  const [liked, setLiked] = useState(false);
  const [commented, setCommented] = useState(false);
  const [shared, setShared] = useState(false);

  function handleShare() {
    const url = articleUrl || window.location.href;
    const title = headline || document.title;

    const markShared = () => {
      setShared(true);
      setTimeout(() => setShared(false), 1500);
    };

    if (navigator.share) {
      void navigator.share({ title, url }).then(markShared).catch(() => {
        // share sheet dismissed — still try clipboard
        fallbackCopy(url, markShared);
      });
    } else {
      fallbackCopy(url, markShared);
    }
  }

  function fallbackCopy(text: string, onSuccess: () => void) {
    // clipboard API requires secure context; on plain HTTP use execCommand
    if (navigator.clipboard) {
      void navigator.clipboard.writeText(text).then(onSuccess).catch(() => {
        legacyCopy(text, onSuccess);
      });
    } else {
      legacyCopy(text, onSuccess);
    }
  }

  function legacyCopy(text: string, onSuccess: () => void) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      onSuccess();
    } catch {
      // nothing more we can do
    }
  }

  return (
    <div className="flex items-center gap-5 px-1">
      {/* Like */}
      <button
        className={`flex items-center gap-1.5 transition-colors ${
          liked ? "text-red-500" : "text-muted-foreground hover:text-red-400"
        }`}
        aria-label={liked ? "Unlike" : "Like"}
        aria-pressed={liked}
        onClick={() => setLiked((v) => !v)}
      >
        <Heart
          className="h-5 w-5 transition-transform active:scale-125"
          fill={liked ? "currentColor" : "none"}
          aria-hidden
        />
      </button>

      {/* Comment */}
      <button
        className={`flex items-center gap-1.5 transition-colors ${
          commented ? "text-primary" : "text-muted-foreground hover:text-foreground"
        }`}
        aria-label={commented ? "Commented" : "Comment"}
        aria-pressed={commented}
        onClick={() => setCommented((v) => !v)}
      >
        <MessageCircle
          className="h-5 w-5"
          fill={commented ? "currentColor" : "none"}
          aria-hidden
        />
      </button>

      {/* Save */}
      <button
        className={`flex items-center gap-1.5 transition-colors ${
          isSaved ? "text-primary" : "text-muted-foreground hover:text-foreground"
        }`}
        aria-label={isSaved ? "Saved" : "Save"}
        aria-pressed={isSaved}
        onClick={onSave}
      >
        <Bookmark
          className="h-5 w-5 transition-transform active:scale-125"
          fill={isSaved ? "currentColor" : "none"}
          aria-hidden
        />
      </button>

      {/* Share */}
      <button
        className={`flex items-center gap-1.5 transition-colors ml-auto ${
          shared ? "text-primary" : "text-muted-foreground hover:text-foreground"
        }`}
        aria-label={shared ? "Link copied" : "Share"}
        onClick={handleShare}
      >
        {shared ? (
          <Check className="h-5 w-5" aria-hidden />
        ) : (
          <Share2 className="h-5 w-5" aria-hidden />
        )}
      </button>
    </div>
  );
}
