"use client";

/** Mini hook de données : fetch + états, avec re-fetch quand les params changent. */

import { useEffect, useState } from "react";
import { apiGet } from "./api";

export function useApi<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined | null> = {},
) {
  const [data, setData] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const cle = JSON.stringify([path, params]);

  useEffect(() => {
    let actif = true;
    setErreur(null);
    apiGet<T>(path, params)
      .then((d) => actif && setData(d))
      .catch((e) => actif && setErreur(e.message));
    return () => {
      actif = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cle]);

  return { data, erreur, chargement: data === null && erreur === null };
}
