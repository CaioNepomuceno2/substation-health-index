"""Monta a tabela de indicadores por SE para um snapshot, usando só dados disponíveis até ele."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from sehealth import carregamento as C
from sehealth import dados as D
from sehealth import eventos as E
from sehealth import topologia as T
from sehealth import valor as V


def crosswalk(interim: Path, ano: int) -> pd.DataFrame:
    """Crosswalk código → alimentador canônico do snapshot mais recente até ``ano``."""
    disp = sorted(int(p.stem.split("_")[-1]) for p in Path(interim).glob("crosswalk_*.parquet"))
    a = max(x for x in disp if x <= ano)
    return pd.read_parquet(Path(interim) / f"crosswalk_{a}.parquet")


def transferencia(cache: Path, ano: int, alim: pd.DataFrame) -> pd.Series | None:
    """Fração das UCs de cada SE em alimentadores sem chave NA para outra SE (None se não há topologia)."""
    seg = Path(cache) / str(ano) / "SSDMT.parquet"
    if not seg.exists():
        return None
    segmentos = pd.read_parquet(seg, columns=["PAC_1", "PAC_2", "CTMT"])
    chaves = D.camada(cache, ano, "UNSEMT", ["COD_ID", "PAC_1", "PAC_2", "P_N_OPE"])
    se_do_ctmt = alim.set_index("alimentador_cod_id").se
    pares = T.interligacoes(chaves, segmentos, se_do_ctmt)
    com = T.alimentadores_com_transferencia(pares)
    uc = pd.to_numeric(alim.n_uc, errors="coerce").fillna(0).astype(float)
    sem_rota = (~alim.alimentador_cod_id.isin(com)).astype(float)
    tot = uc.groupby(alim.se).sum()
    return ((uc * sem_rota).groupby(alim.se).sum() / tot.replace(0, np.nan)).rename("frac_uc_sem_transferencia")


def montar(cfg: dict, ano: int, eventos: pd.DataFrame, anos_historico: list[int],
           fator_carga: float | None = None) -> pd.DataFrame:
    d, el = cfg["dados"], cfg["eletrico"]
    cache, interim = Path(d["cache_bdgd"]), Path(d["interim_gridrisk"])
    fc = fator_carga or el["fator_carga_se"]
    trafos = D.trafos_se(cache, ano, el["tensoes_secundario_mt"], el["sobrecarga_emergencia"])
    alim = D.alimentadores(cache, interim, ano)
    carga = C.carga_mensal_se(alim, ano)
    df = C.indicadores_carregamento(carga, C.capacidade_se(trafos), fc, el["fator_potencia"])
    df["cobertura_vinculo"] = C.cobertura_vinculo(alim)
    # carregamento só é pontuado quando o cadastro liga a SE a seus alimentadores de forma coerente
    incerto = df.cobertura_vinculo < el["cobertura_minima_vinculo"]
    df["carregamento_incerto"] = incerto
    for col in ["utilizacao_pico", "deficit_n1"]:
        df[col + "_pontuado"] = df[col].where(~incerto)

    # crescimento: energia do snapshot vs. dois anos antes (mesma SE)
    try:
        alim_ant = D.alimentadores(cache, interim, ano - 2)
        e_ant = C.carga_mensal_se(alim_ant, ano - 2).mean(axis=1)
        df["crescimento_aa"] = C.crescimento(df.mw_medio, e_ant, 2)
    except FileNotFoundError:
        df["crescimento_aa"] = np.nan

    v = cfg["valor"]
    df["ens_n1_mwh_ano"] = V.ens_n1_esperada_mwh(trafos, df.media_mva, v["taxa_falha_trafo_ano"],
                                                 v["horas_reposicao"], el["fator_potencia"])
    t = trafos[trafos.eh_mt]
    df["idade_anos"] = t.groupby("se").idade_anos.max()
    df["idade_media_anos"] = t.groupby("se").idade_anos.mean()
    df["perdas_z"] = C.perdas_z(trafos)
    df["n_alimentadores"] = alim.groupby("se").size()
    df["n_uc"] = alim.groupby("se").n_uc.sum()
    df["rede_mt_km"] = alim.groupby("se").rede_mt_km.sum()

    # municípios: SE única (com trafo de MT) no município → 1; senão 1/n
    mun = t.drop_duplicates("se").groupby("mun").se.nunique()
    se_mun = t.drop_duplicates("se").set_index("se").mun
    df["frac_municipio"] = 1 / se_mun.map(mun).reindex(df.index)

    tr = transferencia(cache, ano, alim)
    df["frac_uc_sem_transferencia"] = tr if tr is not None else np.nan

    # desempenho histórico (só anos <= snapshot)
    cw = crosswalk(interim, ano)
    ev = E.vincular(eventos[eventos.ano.isin(anos_historico)], cw, alim)
    ev_se = E.eventos_se(ev, cfg["eventos"]["min_alimentadores_evento_se"])
    hist = E.resumo_por_se(ev, ev_se, anos_historico)
    df = df.join(hist, how="left")
    df[hist.columns] = df[hist.columns].fillna(0.0)
    df["eventos_se_por_100k_uc"] = df.eventos_se_ano / df.n_uc.replace(0, np.nan) * 1e5

    nomes = D.subestacoes(cache, ano).set_index("se")
    df = df.join(nomes, how="left")
    df.index.name = "se"
    df["ano_snapshot"] = ano
    return df.reset_index()
