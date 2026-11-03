"""Interrupções por subestação: exposição (CHI dos alimentadores) e eventos de SE.

Evento de SE: interrupções que começam no mesmo minuto em >= N alimentadores da
mesma subestação. É o rastro que uma falha de barramento, de trafo de potência ou
do suprimento em alta tensão deixa na base de interrupções, que não identifica o
equipamento de SE que falhou.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def eventos_mt(interrupcoes: Path, anos: list[int]) -> pd.DataFrame:
    """Interrupções não programadas, de origem interna, em média tensão."""
    lista = ", ".join(str(a) for a in anos)
    return duckdb.sql(f"""
        select coalesce(alimentador_cod_id, alimentador_nome) as codigo, subestacao as cod_subestacao,
               inicio, chi, uc_afetadas, duracao_h, ano, elemento
        from read_parquet('{interrupcoes}')
        where origem_mt and origem = 'INTERNA' and tipo = 'NAO PROGRAMADA' and ano in ({lista})
    """).df()


def vincular(ev: pd.DataFrame, crosswalk: pd.DataFrame, alim: pd.DataFrame) -> pd.DataFrame:
    """Liga cada interrupção ao alimentador canônico (crosswalk) e à SE que o supre no snapshot ``alim``."""
    se = alim[["alimentador", "se"]].drop_duplicates("alimentador")
    out = ev.merge(crosswalk, on="codigo", how="left").merge(se, on="alimentador", how="left")
    return out


def eventos_se(ev: pd.DataFrame, min_alimentadores: int) -> pd.DataFrame:
    """Agrupa interrupções simultâneas (mesmo minuto) por SE e mantém as que atingem >= N alimentadores."""
    e = ev.dropna(subset=["se", "alimentador"]).copy()
    e["minuto"] = e.inicio.dt.floor("min")
    g = e.groupby(["se", "minuto"]).agg(
        n_alimentadores=("alimentador", "nunique"), chi=("chi", "sum"),
        uc_afetadas=("uc_afetadas", "sum"), ano=("ano", "first")).reset_index()
    return g[g.n_alimentadores >= min_alimentadores].reset_index(drop=True)


def resumo_por_se(ev: pd.DataFrame, ev_se: pd.DataFrame, anos: list[int]) -> pd.DataFrame:
    """Médias anuais por SE: CHI dos alimentadores e número/CHI dos eventos de SE."""
    n = len(anos)
    e = ev[ev.ano.isin(anos)].dropna(subset=["se"])
    s = ev_se[ev_se.ano.isin(anos)]
    out = pd.DataFrame({
        "chi_alimentadores_ano": e.groupby("se").chi.sum() / n,
        "eventos_se_ano": s.groupby("se").size() / n,
        "chi_eventos_se_ano": s.groupby("se").chi.sum() / n,
    })
    return out.fillna(0.0)
