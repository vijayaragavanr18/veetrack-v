'use client';

import { useRouter } from 'next/navigation';
import { TrendingUp } from 'lucide-react';

const TRENDING_TOPICS = [
  { keyword: 'Tesla', category: 'EV & Energy', color: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  { keyword: 'Apple', category: 'Big Tech', color: 'bg-purple-500/10 text-purple-400 border-purple-500/20' },
  { keyword: 'Meta', category: 'Social Media', color: 'bg-pink-500/10 text-pink-400 border-pink-500/20' },
  { keyword: 'SpaceX', category: 'Aerospace', color: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
  { keyword: 'OpenAI', category: 'AI', color: 'bg-green-500/10 text-green-400 border-green-500/20' },
  { keyword: 'NVIDIA', category: 'Semiconductors', color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  { keyword: 'Amazon', category: 'E-Commerce', color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' },
  { keyword: 'Microsoft', category: 'Cloud', color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' },
];

export default function DiscoverPage() {
  const router = useRouter();

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-y-auto px-4 py-5">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="h-5 w-5 text-primary" aria-hidden />
        <h1 className="text-base font-semibold text-foreground">Trending Topics</h1>
      </div>

      <p className="text-xs text-muted-foreground mb-5">
        Tap a topic to explore the latest PR intelligence.
      </p>

      {/* Topic grid */}
      <div className="grid grid-cols-2 gap-3">
        {TRENDING_TOPICS.map(({ keyword, category, color }) => (
          <button
            key={keyword}
            onClick={() => router.push(`/feed?q=${encodeURIComponent(keyword)}`)}
            className={`flex flex-col items-start gap-1 rounded-xl border px-4 py-3.5 text-left transition-opacity hover:opacity-80 active:scale-95 ${color}`}
          >
            <span className="text-base font-semibold leading-tight">{keyword}</span>
            <span className="text-[11px] opacity-70 font-medium">{category}</span>
          </button>
        ))}
      </div>

      <p className="text-[11px] text-muted-foreground/60 mt-6 text-center">
        Topics update every 6 hours based on ingestion volume.
      </p>
    </div>
  );
}
