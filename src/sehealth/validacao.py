"""Validação preditiva: o índice montado com dados até o ano t aponta as SEs com mais problemas depois?"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def captura_top(pred: pd.Series, real: pd.Series, frac: float) -> float:
    """Fração do total de ``real`` que cai nas ``frac`` SEs de maior ``pred``."""
    k = max(1, int(round(len(pred) * frac)))
    top = pred.sort_values(ascending=False, kind="mergesort").index[:k]
    tot = real.sum()
    return float(real.loc[top].sum() / tot) if tot > 0 else np.nan


def comparar(df: pd.DataFrame, preditores: list[str], resultados: list[str],
             fracs: tuple[float, ...] = (0.1, 0.2)) -> pd.DataFrame:
    linhas = []
    for y in resultados:
        for p in preditores:
            d = df[[p, y]].dropna()
            rho, pval = spearmanr(d[p], d[y]) if len(d) > 3 else (np.nan, np.nan)
            linha = {"resultado": y, "preditor": p, "n": len(d), "spearman": rho, "p_valor": pval}
            for f in fracs:
                linha[f"captura_top{int(f * 100)}"] = captura_top(d[p], d[y], f)
            linhas.append(linha)
    return pd.DataFrame(linhas)


def casar_por_proximidade(base: pd.DataFrame, alvo: pd.DataFrame, max_km: float = 1.0) -> pd.Series:
    """Mapeia o id de SE de um snapshot para outro pela SE mais próxima (< max_km).

    Os códigos de SE mudaram entre os snapshots de 2022 e 2023; as coordenadas não.
    """
    b = base.dropna(subset=["lat", "lon"])
    a = alvo.dropna(subset=["lat", "lon"])
    la1, lo1 = np.radians(b.lat.values)[:, None], np.radians(b.lon.values)[:, None]
    la2, lo2 = np.radians(a.lat.values)[None, :], np.radians(a.lon.values)[None, :]
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    dist = 2 * 6371 * np.arcsin(np.sqrt(h))
    j, dmin = dist.argmin(axis=1), dist.min(axis=1)
    m = pd.Series(a.se.values[j], index=b.se.values)
    return m[dmin < max_km]


def ampliacoes(base: pd.DataFrame, depois: pd.DataFrame, limiar: float = 0.10) -> pd.DataFrame:
    """SEs que ganharam capacidade de MT (>= limiar) ou mais trafos entre dois snapshots."""
    mapa = casar_por_proximidade(base, depois)
    b = base[["se", "pot_instalada_mva", "n_trafos"]].assign(se_depois=lambda x: x.se.map(mapa)).dropna(
        subset=["se_depois"])
    j = b.merge(depois[["se", "pot_instalada_mva", "n_trafos"]].rename(columns={"se": "se_depois"}),
                on="se_depois", suffixes=("", "_depois"))
    j["ampliou"] = (j.pot_instalada_mva_depois >= j.pot_instalada_mva * (1 + limiar)) | (
        j.n_trafos_depois > j.n_trafos)
    return j


def taxa_ampliacao(base: pd.DataFrame, depois: pd.DataFrame, flag: str) -> pd.DataFrame:
    j = ampliacoes(base, depois).merge(base[["se", flag]], on="se")
    g = j.groupby(flag).ampliou.agg(["size", "sum", "mean"]).rename(
        columns={"size": "n_ses", "sum": "ampliadas", "mean": "taxa"})
    return g.reset_index().rename(columns={flag: "sinalizada"})
