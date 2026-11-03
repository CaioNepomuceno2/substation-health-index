"""Carregamento das subestações e capacidade firme (critério N-1)."""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from sehealth.dados import MESES


def horas_mes(ano: int) -> np.ndarray:
    return np.array([calendar.monthrange(ano, m)[1] * 24 for m in range(1, 13)], dtype=float)


def carga_mensal_se(alim: pd.DataFrame, ano: int, so_vinculo_ok: bool = True) -> pd.DataFrame:
    """MW médio por SE e mês, somando a energia dos alimentadores supridos pela SE.

    Com ``so_vinculo_ok``, só entram alimentadores cuja tensão bate com o secundário
    do trafo cadastrado como origem: o vínculo dos demais não é confiável (ex.:
    alimentadores de 34,5 kV apontando para um trafo 138/13,8 kV).
    """
    a = alim[alim.vinculo_ok] if so_vinculo_ok and "vinculo_ok" in alim else alim
    ene = a.groupby("se")[[f"ene_{m}" for m in MESES]].sum()
    mw = ene.values / horas_mes(ano) / 1000.0
    return pd.DataFrame(mw, index=ene.index, columns=[int(m) for m in MESES])


def cobertura_vinculo(alim: pd.DataFrame) -> pd.Series:
    """Fração da energia (em módulo) dos alimentadores da SE com vínculo coerente ao trafo."""
    e = alim[[f"ene_{m}" for m in MESES]].abs().sum(axis=1)
    tot = e.groupby(alim.se).sum()
    ok = e.where(alim.vinculo_ok, 0).groupby(alim.se).sum()
    return (ok / tot.replace(0, np.nan)).rename("cobertura_vinculo")


def capacidade_se(trafos: pd.DataFrame) -> pd.DataFrame:
    """Capacidade instalada e firme (perda do maior trafo) por SE, só trafos com secundário de MT."""
    t = trafos[trafos.eh_mt & trafos.pot_mva.gt(0)]
    g = t.groupby("se")
    out = pd.DataFrame({
        "n_trafos": g.size(),
        "pot_instalada_mva": g.pot_mva.sum(),
        "pot_emerg_total_mva": g.pot_emerg_mva.sum(),
        "maior_trafo_emerg_mva": g.pot_emerg_mva.max(),
    })
    out["pot_firme_mva"] = out.pot_emerg_total_mva - out.maior_trafo_emerg_mva
    return out


def indicadores_carregamento(carga_mw: pd.DataFrame, cap: pd.DataFrame, fator_carga: float,
                             fator_potencia: float) -> pd.DataFrame:
    """Pico estimado, utilização e déficit N-1 por SE.

    pico (MVA) = maior MW médio mensal / fator de carga / fator de potência.
    deficit_n1 = parcela do pico que não cabe nos trafos restantes se o maior sair.
    """
    # fluxo pelo trafo em módulo: SEs com exportação líquida (GD) também carregam o trafo
    df = cap.join(pd.DataFrame({
        "mw_medio": carga_mw.mean(axis=1).abs(),
        "mw_mes_pico": carga_mw.abs().max(axis=1),
        "fluxo_reverso": carga_mw.mean(axis=1) < 0,
        "meses_fluxo_reverso": (carga_mw < 0).sum(axis=1),
    }), how="inner")
    df["energia_gwh"] = df.mw_medio * 8760 / 1000
    df["pico_mva"] = df.mw_mes_pico / fator_carga / fator_potencia
    df["media_mva"] = df.mw_medio / fator_potencia
    df["utilizacao_pico"] = df.pico_mva / df.pot_instalada_mva
    df["folga_n1_mva"] = df.pot_firme_mva - df.pico_mva
    df["deficit_n1_mva"] = (-df.folga_n1_mva).clip(lower=0)
    df["deficit_n1"] = np.where(df.pico_mva > 0, df.deficit_n1_mva / df.pico_mva, 0.0)
    df["sem_folga_n1"] = df.folga_n1_mva < 0
    return df


def crescimento(carga_atual: pd.Series, carga_anterior: pd.Series, anos: int) -> pd.Series:
    """Taxa anual de crescimento da energia; NaN se a SE não existia antes."""
    r = carga_atual / carga_anterior.reindex(carga_atual.index)
    return (r ** (1 / anos) - 1).where(carga_anterior.reindex(carga_atual.index) > 0)


def perdas_z(trafos: pd.DataFrame) -> pd.Series:
    """Perda no ferro (% da potência) acima do esperado para o porte, em desvios-padrão (pior trafo da SE).

    Esperado: regressão de log(perda) em log(potência) na frota do mesmo snapshot.
    """
    t = trafos[trafos.eh_mt & trafos.per_fer.gt(0) & trafos.pot_mva.gt(0)].copy()
    if len(t) < 5:
        return pd.Series(dtype=float)
    x, y = np.log(t.pot_mva), np.log(t.per_fer)
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    t["z"] = (res - res.mean()) / res.std(ddof=0)
    return t.groupby("se").z.max()
