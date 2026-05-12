import { Link } from "@tanstack/react-router";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link to="/" className={`flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      <span className="relative inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-primary text-primary-foreground glow-primary">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M4 6h2M9 6h1M13 6h2M18 6h2M4 18h2M9 18h1M13 18h2M18 18h2M4 6v12M20 6v12" strokeLinecap="round" />
        </svg>
      </span>
      <span className="text-lg">
        Bool<span className="text-gradient-primary">Eto</span>
      </span>
    </Link>
  );
}
