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
    <header className="sticky top-0 z-50 border-b border-ink bg-bg/95 backdrop-blur-sm">
      <nav className="mx-auto flex max-w-7xl items-center gap-6 overflow-x-auto px-4 py-3 sm:px-6">
        <Link href="/" className="flex shrink-0 items-baseline gap-2">
          <span className="font-display text-xl font-black tracking-tight">Immo Insights</span>
          <span className="label-mono !text-accent">N°06</span>
        </Link>
        <div className="ml-auto flex items-center gap-5">
          {LIENS.map(({ href, label }) => {
            const actif = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`label-mono shrink-0 pb-0.5 transition-colors ${
                  actif
                    ? "!text-accent border-b-2 border-accent"
                    : "hover:!text-ink border-b-2 border-transparent"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
