import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const instrument = Instrument_Sans({ subsets: ["latin"], variable: "--font-instrument" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plexmono" });

export const metadata: Metadata = {
  title: "Immo Insights N°06 — observatoire du marché azuréen",
  description:
    "128 000 ventes analysées : prix au m², tendances, rendement locatif, impact DPE et score d'investissement par commune. Données publiques DVF, INSEE, ADEME.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${fraunces.variable} ${instrument.variable} ${plexMono.variable}`}>
      <body className="min-h-screen antialiased">
        <Nav />
        <main className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">{children}</main>
        <footer className="border-t border-ink/80 py-8">
          <div className="label-mono mx-auto max-w-7xl px-4 leading-relaxed sm:px-6">
            Données publiques : DVF (Etalab) · INSEE · DPE ADEME · Carte des loyers · OpenStreetMap
            <br />
            Pipeline : Airflow · Parquet médaillon · dbt · DuckDB · FastAPI — mis à jour quotidiennement
          </div>
        </footer>
      </body>
    </html>
  );
}
