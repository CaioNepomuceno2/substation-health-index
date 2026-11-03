"""Leitura do cache da BDGD e montagem das tabelas de trafos de SE e alimentadores por snapshot.

O cache (uma pasta por ano com uma camada por Parquet) é gerado por
``scripts/00_cache_bdgd.py``. As tabelas de interrupções e os crosswalks de
código de alimentador vêm do projeto irmão distribution-asset-risk.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MESES = [f"{m:02d}" for m in range(1, 13)]


def camada(cache: Path, ano: int, nome: str, colunas: list[str] | None = None) -> pd.DataFrame:
    p = Path(cache) / str(ano) / f"{nome}.parquet"
    if not p.exists():
        raise FileNotFoundError(p)
    return pd.read_parquet(p, columns=colunas)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _ano_data(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce").dt.year


def normalizar_potencia(pot: pd.Series) -> pd.Series:
    """MVA. O snapshot de 2021 grava a potência em outra unidade (ex.: 0,03 para 30 MVA)."""
    pot = _num(pot)
    if pot.median() < 1:
        pot = pot * 1000
    return pot


def trafos_se(cache: Path, ano: int, tensoes_mt: list[str], sobrecarga_emergencia: float = 1.0) -> pd.DataFrame:
    """Transformadores de subestação (UNTRAT + EQTRAT) com idade e capacidade de emergência."""
    u = camada(cache, ano, "UNTRAT")
    e = camada(cache, ano, "EQTRAT")
    cols_e = [c for c in ["UNI_TR_AT", "TEN_PRI", "TEN_SEC", "DAT_IMO"] if c in e.columns]
    e = e[cols_e].drop_duplicates("UNI_TR_AT")
    t = u.merge(e, left_on="COD_ID", right_on="UNI_TR_AT", how="left")
    out = pd.DataFrame({
        "trafo": t.COD_ID.astype(str),
        "se": t.SUB.astype(str),
        "mun": t.MUN.astype(str),
        "pot_mva": normalizar_potencia(t.POT_NOM),
        "pot_f01": normalizar_potencia(t.POT_F01),
        "pot_f02": normalizar_potencia(t.POT_F02),
        "per_fer": _num(t.PER_FER),
        "per_tot": _num(t.PER_TOT),
        "ten_sec": t.TEN_SEC.astype("string").str.strip() if "TEN_SEC" in t else pd.NA,
        "lon": _num(t.lon), "lat": _num(t.lat),
    })
    # capacidade de emergência: maior estágio de ventilação forçada cadastrado
    emerg = out[["pot_mva", "pot_f01", "pot_f02"]].max(axis=1)
    out["pot_emerg_mva"] = emerg * sobrecarga_emergencia
    out["eh_mt"] = out.ten_sec.isin(tensoes_mt)
    # idade: data de conexão; datas fora do intervalo plausível caem para a data de imobilização
    ano_con = _ano_data(t.DAT_CON)
    ano_imo = _ano_data(t.DAT_IMO) if "DAT_IMO" in t else pd.Series(np.nan, index=t.index)
    valido = ano_con.between(1950, ano)
    out["ano_instalacao"] = ano_con.where(valido, ano_imo.where(ano_imo.between(1950, ano)))
    out["data_suspeita"] = ~valido
    out["idade_anos"] = ano - out.ano_instalacao
    out["ano_snapshot"] = ano
    return out


def alimentadores(cache: Path, interim: Path, ano: int) -> pd.DataFrame:
    """Alimentadores do snapshot com a SE que os supre, energia mensal e consumidores.

    A SE é a do transformador de origem (CTMT.UNI_TR_AT → UNTRAT.SUB); quando o
    alimentador não aponta para um trafo cadastrado, usa CTMT.SUB.
    """
    c = camada(cache, ano, "CTMT")
    u = camada(cache, ano, "UNTRAT", ["COD_ID", "SUB"]).rename(columns={"COD_ID": "UNI_TR_AT", "SUB": "SUB_TR"})
    e = camada(cache, ano, "EQTRAT", ["UNI_TR_AT", "TEN_SEC"]).drop_duplicates("UNI_TR_AT")
    c = c.merge(u, on="UNI_TR_AT", how="left").merge(e, on="UNI_TR_AT", how="left")
    df = pd.DataFrame({
        "alimentador_cod_id": c.COD_ID.astype(str),
        "alimentador": c.NOME.astype(str).str.strip().str.zfill(6),
        "se": c.SUB_TR.fillna(c.SUB).astype(str),
        "trafo": c.UNI_TR_AT.astype(str),
        "ten_nom": c.TEN_NOM.astype(str),
        # vínculo coerente: a tensão do alimentador é a do secundário do trafo apontado
        "vinculo_ok": c.TEN_NOM.astype(str).str.strip().eq(c.TEN_SEC.astype(str).str.strip()),
    })
    for m in MESES:
        df[f"ene_{m}"] = _num(c[f"ENE_{m}"]).fillna(0.0)   # kWh
    feeders = Path(interim) / f"bdgd_feeders_{ano}.parquet"
    if feeders.exists():
        f = pd.read_parquet(feeders, columns=["alimentador_cod_id", "n_uc", "rede_mt_km", "frac_rural"])
        f["alimentador_cod_id"] = f.alimentador_cod_id.astype(str)
        df = df.merge(f, on="alimentador_cod_id", how="left")
        for c in ["n_uc", "rede_mt_km", "frac_rural"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["ano_snapshot"] = ano
    return df


def subestacoes(cache: Path, ano: int) -> pd.DataFrame:
    s = camada(cache, ano, "SUB", ["COD_ID", "NOME", "lon", "lat"])
    return s.rename(columns={"COD_ID": "se", "NOME": "nome"}).assign(se=lambda d: d.se.astype(str))
