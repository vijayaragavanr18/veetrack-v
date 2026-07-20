'use client';

import { useRouter } from 'next/navigation';
import { TrendingUp, Building2, Zap, Brain, Shield, Globe, Sparkles } from 'lucide-react';

// Industry categories for PR monitoring
const INDUSTRIES = [
  {
    name: 'Technology',
    icon: Zap,
    keywords: ['AI', 'Cloud Computing', 'Cybersecurity', 'SaaS', 'Blockchain'],
    color: 'from-blue-500/10 to-cyan-500/10 border-blue-500/20 hover:border-blue-500/40',
    iconColor: 'text-blue-500',
  },
  {
    name: 'Healthcare',
    icon: Shield,
    keywords: ['Biotech', 'Pharma', 'Medical Devices', 'Telehealth', 'Clinical Trials'],
    color: 'from-green-500/10 to-emerald-500/10 border-green-500/20 hover:border-green-500/40',
    iconColor: 'text-green-500',
  },
  {
    name: 'Financial Services',
    icon: Building2,
    keywords: ['Banking', 'FinTech', 'Insurance', 'Investment', 'Crypto'],
    color: 'from-yellow-500/10 to-orange-500/10 border-yellow-500/20 hover:border-yellow-500/40',
    iconColor: 'text-yellow-600',
  },
  {
    name: 'Consumer Goods',
    icon: Sparkles,
    keywords: ['Retail', 'E-Commerce', 'CPG', 'Fashion', 'Food & Beverage'],
    color: 'from-pink-500/10 to-rose-500/10 border-pink-500/20 hover:border-pink-500/40',
    iconColor: 'text-pink-500',
  },
  {
    name: 'Energy & Environment',
    icon: Globe,
    keywords: ['Renewable Energy', 'Oil & Gas', 'Sustainability', 'Climate Tech', 'EV'],
    color: 'from-green-500/10 to-teal-500/10 border-green-600/20 hover:border-green-600/40',
    iconColor: 'text-green-600',
  },
  {
    name: 'AI & Innovation',
    icon: Brain,
    keywords: ['Machine Learning', 'Robotics', 'Quantum Computing', 'IoT', 'Automation'],
    color: 'from-purple-500/10 to-indigo-500/10 border-purple-500/20 hover:border-purple-500/40',
    iconColor: 'text-purple-500',
  },
];

// High-profile companies for PR monitoring
const FEATURED_COMPANIES = [
  { name: 'Tesla', sector: 'Automotive & Energy', risk: 'High Visibility' },
  { name: 'Apple', sector: 'Consumer Tech', risk: 'High Visibility' },
  { name: 'Microsoft', sector: 'Enterprise Software', risk: 'Medium Visibility' },
  { name: 'Meta', sector: 'Social Media', risk: 'High Visibility' },
  { name: 'Amazon', sector: 'E-Commerce & Cloud', risk: 'High Visibility' },
  { name: 'Google', sector: 'Search & Advertising', risk: 'High Visibility' },
  { name: 'OpenAI', sector: 'Artificial Intelligence', risk: 'Critical Watch' },
  { name: 'NVIDIA', sector: 'Semiconductors', risk: 'High Visibility' },
  { name: 'SpaceX', sector: 'Aerospace', risk: 'Medium Visibility' },
  { name: 'Pfizer', sector: 'Pharmaceuticals', risk: 'High Visibility' },
  { name: 'JPMorgan', sector: 'Financial Services', risk: 'High Visibility' },
  { name: 'Walmart', sector: 'Retail', risk: 'Medium Visibility' },
];

export default function DiscoverPage() {
  const router = useRouter();

  function handleSearch(keyword: string) {
    router.push(`/feed?q=${encodeURIComponent(keyword)}`);
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-y-auto px-4 py-6 space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" aria-hidden />
          <h1 className="text-lg font-bold text-foreground">Media Intelligence</h1>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Monitor breaking news, sentiment shifts, and PR risks across industries and companies.
          Real-time coverage from 50,000+ global sources.
        </p>
      </div>

      {/* Industry Categories */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Monitor by Industry
        </h2>
        <div className="grid grid-cols-1 gap-3">
          {INDUSTRIES.map(({ name, icon: Icon, keywords, color, iconColor }) => (
            <div
              key={name}
              className={`relative rounded-xl border bg-gradient-to-br ${color} p-4 transition-all`}
            >
              <div className="flex items-start gap-3">
                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-background/80 backdrop-blur-sm ${iconColor}`}>
                  <Icon className="h-5 w-5" aria-hidden />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-foreground mb-2">{name}</h3>
                  <div className="flex flex-wrap gap-1.5">
                    {keywords.map((keyword) => (
                      <button
                        key={keyword}
                        onClick={() => handleSearch(keyword)}
                        className="inline-flex items-center rounded-full bg-background/60 backdrop-blur-sm border border-border/40 px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-background hover:border-primary/60 active:scale-95 transition-all"
                      >
                        {keyword}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Featured Companies */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          High-Visibility Companies
        </h2>
        <p className="text-[11px] text-muted-foreground/80 leading-relaxed -mt-1">
          Track companies with significant media exposure and PR impact.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {FEATURED_COMPANIES.map(({ name, sector, risk }) => (
            <button
              key={name}
              onClick={() => handleSearch(name)}
              className="flex flex-col items-start gap-1.5 rounded-lg border border-border bg-card/50 backdrop-blur-sm px-3 py-2.5 text-left transition-all hover:bg-card hover:border-primary/40 active:scale-95"
            >
              <span className="text-sm font-semibold text-foreground">{name}</span>
              <span className="text-[10px] text-muted-foreground font-medium truncate w-full">
                {sector}
              </span>
              <span
                className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                  risk === 'Critical Watch'
                    ? 'bg-red-500/10 text-red-500 border border-red-500/20'
                    : risk === 'High Visibility'
                    ? 'bg-orange-500/10 text-orange-500 border border-orange-500/20'
                    : 'bg-yellow-500/10 text-yellow-600 border border-yellow-500/20'
                }`}
              >
                {risk}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Footer note */}
      <div className="rounded-lg border border-border/40 bg-muted/30 backdrop-blur-sm px-4 py-3 space-y-1">
        <p className="text-[11px] font-semibold text-foreground">For PR Professionals</p>
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          VeeTrack aggregates news from Reuters, Bloomberg, AP, industry publications, and social media
          to provide comprehensive coverage analysis and PR risk assessment.
        </p>
      </div>
    </div>
  );
}
