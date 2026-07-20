export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh bg-background justify-center">
      <div className="w-full max-w-[430px] flex flex-col overflow-y-auto sm:shadow-2xl sm:border-x sm:border-border bg-background">
        {children}
      </div>
    </div>
  );
}
