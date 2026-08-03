"use client";

import { useState } from "react";
import { Heart, MessageCircle, Bookmark, Share2, Check, X } from "lucide-react";

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
  const [showComments, setShowComments] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [mockComments, setMockComments] = useState([
    { id: 1, user: "Alex T.", text: "This is a massive development for the industry.", time: "2h ago" },
    { id: 2, user: "Sarah J.", text: "I wonder how this will affect the markets next week?", time: "5h ago" }
  ]);

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
        aria-label="Comments"
        onClick={() => setShowComments(true)}
      >
        <MessageCircle
          className="h-5 w-5"
          fill={commented || mockComments.length > 2 ? "currentColor" : "none"}
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

      {/* Comment Bottom Sheet */}
      {showComments && (
        <div className="fixed inset-0 z-[100] flex flex-col justify-end">
          <div 
            className="absolute inset-0 bg-background/80 backdrop-blur-sm" 
            onClick={() => setShowComments(false)}
          />
          <div className="relative bg-card w-full max-w-[430px] mx-auto h-[65vh] rounded-t-2xl shadow-2xl flex flex-col border border-border animate-in slide-in-from-bottom-full duration-300">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 className="font-semibold text-foreground">Comments ({mockComments.length})</h3>
              <button onClick={() => setShowComments(false)} className="p-1 rounded-full hover:bg-muted text-muted-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {mockComments.map(c => (
                <div key={c.id} className="flex gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">
                    {c.user[0]}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-semibold text-sm text-foreground">{c.user}</span>
                      <span className="text-xs text-muted-foreground">{c.time}</span>
                    </div>
                    <p className="text-sm text-foreground/90 mt-0.5">{c.text}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="p-4 border-t border-border bg-card">
              <form 
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!commentText.trim()) return;
                  setMockComments([...mockComments, { id: Date.now(), user: "You", text: commentText, time: "Just now" }]);
                  setCommentText("");
                  setCommented(true);
                }}
              >
                <input 
                  type="text" 
                  value={commentText}
                  onChange={e => setCommentText(e.target.value)}
                  placeholder="Add a comment..." 
                  className="flex-1 bg-muted rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                />
                <button 
                  type="submit"
                  disabled={!commentText.trim()}
                  className="bg-primary text-primary-foreground px-4 py-2 rounded-full text-sm font-medium disabled:opacity-50 transition-opacity"
                >
                  Post
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
