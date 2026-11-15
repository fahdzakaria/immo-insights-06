"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LIENS = [
  { href: "/", label: "Marché" },
  { href: "/carte", label: "Carte" },
  { href: "/tendances", label: "Tendances" },
  { href: "/comparateur", label: "Comparateur" },
  { href: "/rendement", label: "Rendement" },
  { href: "/estimateur", label: "Estimateur" },
  { href: "/opportunites", label: "Opportunités" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-black/80 backdrop-blur-md">
      <nav className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:gap-6 sm:px-6">
        <Link href="/" className="flex shrink-0 items-baseline gap-2">
          <span className="font-logo text-[1.6rem] leading-none">Immo Insights</span>
          <span className="label-mono hidden !text-accent sm:inline">N°06</span>
        </Link>
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden lg:justify-center">
          {LIENS.map(({ href, label }) => {
            const actif = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                aria-current={actif ? "page" : undefined}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  actif ? "bg-white/[0.07] text-ink" : "text-muted hover:text-ink"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
        <Link href="/carte" className="btn btn-clair btn-sm hidden shrink-0 xl:inline-flex">
          Explorer la carte
        </Link>
      </nav>
    </header>
  );
}
