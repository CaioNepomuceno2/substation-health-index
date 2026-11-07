"""Índice de saúde, criticidade e risco (Health Index × Criticality, inspirado no CNAIM/ISO 55000).

Cada indicador vira um score 0-100 por interpolação linear entre um valor "bom"
(0) e um "ruim" (100), com saturação. Os scores são combinados por média
ponderada; dimensões sem dado têm o peso redistribuído entre as disponíveis.
risco = saúde × criticidade / 100.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sehealth import qualidade


def score(x: pd.Series, bom: float, ruim: float, log: bool = False) -> pd.Series:
    x = pd.to_numeric(x, errors="coerce").astype(float)
    if log:
        x, bom, ruim = np.log10(x.clip(lower=1e-9)), np.log10(bom), np.log10(ruim)
    s = (x - bom) / (ruim - bom) * 100
    return s.clip(0, 100)


def media_ponderada(scores: pd.DataFrame, pesos: dict[str, float]) -> pd.Series:
    """Média ponderada linha a linha; ignora NaN e renormaliza os pesos disponíveis."""
    w = pd.Series(pesos, dtype=float)
    s = scores[w.index]
    ww = s.notna().mul(w, axis=1)
    return (s.fillna(0).mul(w, axis=1).sum(axis=1) / ww.sum(axis=1)).where(ww.sum(axis=1) > 0)


def calcular(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Adiciona colunas score_*, saude, criticidade, risco, quadrante e fatores principais."""
    qualidade.verificar_pesos(cfg)
    out = df.copy()
    for nome, p in cfg["scores"].items():
        if nome in out:
            out[f"score_{nome}"] = score(out[nome], p["bom"], p["ruim"], p.get("log", False))
        else:
            out[f"score_{nome}"] = np.nan
    pesos = cfg["pesos"]
    for dim in ["saude", "criticidade"]:
        cols = {f"score_{k}": v for k, v in pesos[dim].items()}
        out[dim] = media_ponderada(out[list(cols)], cols)
    out["risco"] = out.saude * out.criticidade / 100
    cs, cc = cfg["matriz"]["corte_saude"], cfg["matriz"]["corte_criticidade"]
    out["quadrante"] = np.select(
        [(out.saude >= cs) & (out.criticidade >= cc), out.saude >= cs, out.criticidade >= cc],
        ["agir: ampliar/substituir", "planejar: condição ruim, baixa consequência",
         "monitorar: condição boa, alta consequência"],
        default="manter")
    out["fatores_saude"] = _fatores(out, pesos["saude"])
    return out


def _fatores(out: pd.DataFrame, pesos: dict[str, float], k: int = 2) -> pd.Series:
    """Os k indicadores que mais contribuem para o score de saúde de cada SE."""
    contrib = pd.DataFrame({n: out[f"score_{n}"].fillna(0) * w for n, w in pesos.items()})

    def top(row):
        r = row[row > 0].sort_values(ascending=False).head(k)
        return ", ".join(r.index)

    return contrib.apply(top, axis=1)


def sensibilidade_pesos(df: pd.DataFrame, cfg: dict, n: int = 1000, concentracao: float = 20.0,
                        seed: int = 0, k: int = 10) -> dict:
    """Sorteia pesos ao redor dos definidos (Dirichlet) e mede a estabilidade do ranking de risco."""
    rng = np.random.default_rng(seed)
    base = calcular(df, cfg)
    base_rank = base.risco.rank(ascending=False)
    topk = set(base.risco.nlargest(k).index)
    rhos, presenca = [], pd.Series(0.0, index=df.index)
    for _ in range(n):
        c = {**cfg, "pesos": {}}
        for dim, pesos in cfg["pesos"].items():
            w = np.array(list(pesos.values()))
            novo = rng.dirichlet(w / w.sum() * concentracao)
            c["pesos"][dim] = dict(zip(pesos, novo, strict=True))
        r = calcular(df, c).risco
        rhos.append(r.rank(ascending=False).corr(base_rank, method="spearman"))
        presenca[r.nlargest(k).index] += 1
    presenca /= n
    return {
        "spearman_mediano": float(np.median(rhos)),
        "spearman_p05": float(np.quantile(rhos, 0.05)),
        "top_k": k,
        "top_k_estaveis_80pct": int((presenca[list(topk)] >= 0.8).sum()),
        "presenca_top_k": presenca.sort_values(ascending=False),
    }
