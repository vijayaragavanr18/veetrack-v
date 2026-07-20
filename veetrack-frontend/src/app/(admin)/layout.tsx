export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-card px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <a href="/feed" className="text-lg font-bold text-primary">
              VeeTrack
            </a>
            <span className="text-muted-foreground">/</span>
            <span className="text-sm text-muted-foreground">Admin</span>
            <nav className="flex items-center gap-3 text-sm">
              <a href="/admin/dashboard" className="text-muted-foreground hover:text-foreground transition-colors">
                Dashboard
              </a>
              <a href="/admin/sources" className="text-muted-foreground hover:text-foreground transition-colors">
                Sources
              </a>
            </nav>
          </div>
          <a href="/feed" className="text-sm text-muted-foreground hover:text-foreground">
            ← Back to Feed
          </a>
        </div>
      </header>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
