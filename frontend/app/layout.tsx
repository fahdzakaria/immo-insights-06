import type { Metadata } from "next";
import Link from "next/link";
import { Geist_Mono, Inter, Instrument_Serif, Poppins } from "next/font/google";
import Nav from "@/components/Nav";
import { SOURCE_DONNEES } from "@/lib/api";
import meta from "@/public/data/meta.json";
import "./globals.css";

// Mêmes polices que pryzm.design : Poppins (titres), Inter (texte), Geist Mono (data).
// Le serif ne sert plus qu'au logo, comme le logo image de Pryzm.
const poppins = Poppins({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-poppins" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const geistMono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-geistmono" });
const logo = Instrument_Serif({ subsets: ["latin"], weight: "400", variable: "--font-serif-logo" });

export const metadata: Metadata = {
  title: "Immo Insights N°06 — observatoire du marché azuréen",
  description:
    "128 000 ventes analysées : prix au m² par commune et par quartier, tendances, rendement locatif, impact DPE et score d'investissement. Données publiques DVF, INSEE, ADEME.",
};

/** Date réelle du dernier export des marts (public/data/meta.json), pas une promesse. */
const DATE_DONNEES = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Paris",
}).format(new Date(meta.genere_le));

const PIED = [
  { href: "/carte", label: "Carte" },
  { href: "/tendances", label: "Tendances" },
  { href: "/comparateur", label: "Comparateur" },
  { href: "/rendement", label: "Rendement" },
  { href: "/estimateur", label: "Estimateur" },
  { href: "/opportunites", label: "Opportunités" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${poppins.variable} ${inter.variable} ${geistMono.variable} ${logo.variable}`}>
      <body className="min-h-screen antialiased">
        <Nav />
        <main className="mx-auto max-w-6xl px-4 pb-16 sm:px-6 sm:pb-24">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-10 px-4 py-16 sm:px-6">
            <div>
              <div className="font-logo text-2xl">
                Immo Insights <span className="label-mono !text-accent">N°06</span>
              </div>
              <p className="legende mt-3 max-w-sm">
                Prix immobiliers des Alpes-Maritimes, de la commune au quartier.
                {SOURCE_DONNEES === "static" ? ` Données générées le ${DATE_DONNEES}.` : " Données servies par FastAPI."}
              </p>
            </div>
            <div className="legende flex flex-col gap-1.5 sm:ml-auto sm:text-right">
              <div className="flex flex-wrap gap-x-4 gap-y-1 sm:justify-end">
                {PIED.map((l) => (
                  <Link key={l.href} href={l.href} className="transition-colors hover:text-ink">
                    {l.label}
                  </Link>
                ))}
              </div>
              <span>Sources : DVF (Etalab) · INSEE · DPE ADEME · Carte des loyers · OpenStreetMap</span>
              <span>Pipeline : Airflow · Parquet médaillon · dbt · DuckDB</span>
            </div>
          </div>
        </footer>
        <div className="grain" aria-hidden />
      </body>
    </html>
  );
}
