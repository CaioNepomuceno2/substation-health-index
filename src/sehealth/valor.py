"""Valor do risco em R$ e ordem de investimento (premissas em configs/premissas.yaml)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ens_n1_esperada_mwh(trafos: pd.DataFrame, media_mva: pd.Series, taxa_falha: float, horas: float,
                        fator_potencia: float) -> pd.Series:
    """Energia não suprida esperada por ano se um trafo de MT falha e a carga média não cabe nos demais.

    Para cada trafo i da SE: corte_i = max(0, carga média - (capacidade de emergência da SE - emergência_i)).
    ENS = soma_i taxa_falha × horas × corte_i × fp.
    """
    t = trafos[trafos.eh_mt & trafos.pot_mva.gt(0)][["se", "pot_emerg_mva"]].copy()
    t["emerg_total"] = t.groupby("se").pot_emerg_mva.transform("sum")
    t["media"] = t.se.map(media_mva)
    t["corte_mva"] = (t.media - (t.emerg_total - t.pot_emerg_mva)).clip(lower=0)
    return (t.groupby("se").corte_mva.sum() * taxa_falha * horas * fator_potencia).rename("ens_n1_mwh_ano")


def fator_recuperacao(taxa: float, anos: int) -> float:
    return taxa * (1 + taxa) ** anos / ((1 + taxa) ** anos - 1)


def priorizar(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """R$ de risco anual e, para SEs sem folga N-1, custo e benefício ilustrativos de ampliar."""
    v = cfg["valor"]
    out = df.copy()
    out["rs_eventos_se_social"] = out.chi_eventos_se_ano * v["rs_por_chi_social"]
    out["rs_eventos_se_compensacao"] = out.chi_eventos_se_ano * v["rs_por_chi_compensacao"]
    out["rs_ens_n1"] = out.ens_n1_mwh_ano * v["custo_ens_rs_mwh"]
    out["rs_risco_ano"] = out.rs_eventos_se_social.fillna(0) + out.rs_ens_n1.fillna(0)
    precisa = out.sem_folga_n1 & ~out.carregamento_incerto
    out["mva_ampliacao"] = np.where(precisa, out.deficit_n1_mva, 0.0)
    out["capex_ampliacao_rs"] = out.mva_ampliacao * v["custo_ampliacao_rs_mva"]
    crf = fator_recuperacao(v["taxa_desconto"], v["vida_util_anos"])
    out["capex_anualizado_rs"] = out.capex_ampliacao_rs * crf
    out["beneficio_custo_ampliacao"] = np.where(
        out.capex_anualizado_rs > 0, out.rs_ens_n1 / out.capex_anualizado_rs, np.nan)
    return out
