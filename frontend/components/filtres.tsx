"use client";

/** Contrôles de filtre partagés — style éditorial : chips inversées à l'encre. */

import type { TypeBien } from "@/lib/api";

export function ToggleTypeBien({
  valeur,
  onChange,
  avecTous = false,
}: {
  valeur: TypeBien | undefined;
  onChange: (t: TypeBien | undefined) => void;
  avecTous?: boolean;
}) {
  const options: { label: string; v: TypeBien | undefined }[] = [
    ...(avecTous ? [{ label: "Tous", v: undefined }] : []),
    { label: "Appartements", v: "appartement" as TypeBien },
    { label: "Maisons", v: "maison" as TypeBien },
  ];
  return (
    <div className="inline-flex border border-ink">
      {options.map((o, i) => (
        <button
          key={o.label}
          onClick={() => onChange(o.v)}
          className={`label-mono cursor-pointer px-4 py-2 transition-colors ${
            i > 0 ? "border-l border-ink" : ""
          } ${valeur === o.v ? "bg-ink !text-bg" : "hover:bg-ink/5"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ChampRecherche({
  valeur,
  onChange,
  placeholder = "Rechercher une commune…",
  liste,
  listeId,
}: {
  valeur: string;
  onChange: (v: string) => void;
  placeholder?: string;
  liste?: string[];
  listeId?: string;
}) {
  return (
    <>
      <input
        value={valeur}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        list={listeId}
        className="w-full max-w-xs border border-ink bg-panel px-4 py-2 text-sm text-ink placeholder-muted outline-none transition-shadow focus:shadow-[3px_3px_0_rgba(13,46,168,0.25)]"
      />
      {liste && listeId && (
        <datalist id={listeId}>
          {liste.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
      )}
    </>
  );
}

export function Curseur({
  label,
  valeur,
  onChange,
  min,
  max,
  pas = 1,
  format = (v: number) => String(v),
}: {
  label: string;
  valeur: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  pas?: number;
  format?: (v: number) => string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label-mono flex justify-between">
        {label}
        <span className="!text-accent tabular">{format(valeur)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={pas}
        value={valeur}
        onChange={(e) => onChange(Number(e.target.value))}
        className="cursor-pointer accent-[#ffb020]"
      />
    </label>
  );
}
