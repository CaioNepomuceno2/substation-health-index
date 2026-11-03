"""Interligações entre subestações pelas chaves normalmente abertas (NA) da rede de MT.

Uma chave NA (UNSEMT.P_N_OPE = 'A') liga dois pontos (PAC_1, PAC_2). Os segmentos
de MT (SSDMT) que tocam cada ponto dizem a que alimentador cada lado pertence. Se
os dois lados são de alimentadores supridos por SEs diferentes, existe uma rota
para transferir carga entre elas.
"""
from __future__ import annotations

import pandas as pd


def pac_alimentador(segmentos: pd.DataFrame) -> pd.DataFrame:
    """Tabela (pac, ctmt) a partir das duas pontas de cada segmento."""
    a = segmentos[["PAC_1", "CTMT"]].rename(columns={"PAC_1": "pac"})
    b = segmentos[["PAC_2", "CTMT"]].rename(columns={"PAC_2": "pac"})
    return pd.concat([a, b]).dropna().drop_duplicates()


def interligacoes(chaves: pd.DataFrame, segmentos: pd.DataFrame, se_do_ctmt: pd.Series) -> pd.DataFrame:
    """Pares de alimentadores (CTMT) ligados por chave NA e as SEs de cada lado.

    ``se_do_ctmt``: Series indexada pelo COD_ID do CTMT com a SE que o supre.
    """
    na = chaves[chaves.P_N_OPE.astype(str).str.strip().eq("A")][["COD_ID", "PAC_1", "PAC_2"]]
    pa = pac_alimentador(segmentos)
    lado1 = na.merge(pa, left_on="PAC_1", right_on="pac").rename(columns={"CTMT": "ctmt_1"})[["COD_ID", "ctmt_1"]]
    lado2 = na.merge(pa, left_on="PAC_2", right_on="pac").rename(columns={"CTMT": "ctmt_2"})[["COD_ID", "ctmt_2"]]
    pares = lado1.merge(lado2, on="COD_ID")
    pares = pares[pares.ctmt_1 != pares.ctmt_2].copy()
    pares["se_1"] = pares.ctmt_1.map(se_do_ctmt)
    pares["se_2"] = pares.ctmt_2.map(se_do_ctmt)
    pares["entre_ses"] = pares.se_1.notna() & pares.se_2.notna() & (pares.se_1 != pares.se_2)
    return pares.drop_duplicates(["COD_ID", "ctmt_1", "ctmt_2"])


def alimentadores_com_transferencia(pares: pd.DataFrame) -> set[str]:
    """CTMTs com pelo menos uma chave NA para alimentador de outra SE."""
    p = pares[pares.entre_ses]
    return set(p.ctmt_1.astype(str)) | set(p.ctmt_2.astype(str))
