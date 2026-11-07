"""Diagnósticos dos dados de uma distribuidora, para decidir antes de calcular qualquer índice.

Cada função devolve um DataFrame que ``scripts/diagnostico_ems.py`` grava em ``<reports>/diagnostico/``. Nenhuma delas
calcula nota, risco, capacidade firme ou validação: só contagens, taxas de vínculo e estabilidade do cadastro.
As decisões de ``docs/decisoes_ems.md`` citam estas tabelas.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from sehealth import cache as K
from sehealth import carregamento as C
from sehealth import config
from sehealth import dados as D
from sehealth import eventos as E
from sehealth import painel as P
from sehealth import qualidade as Q
from sehealth import topologia as T
from sehealth import validacao as Va


def _trafos_mt(cache: Path, ano: int, tensoes_mt: list[str]) -> pd.DataFrame:
    """UNTRAT + EQTRAT, com os trafos de secundário de MT marcados em ``eh_mt``."""
    u = D.camada(cache, ano, "UNTRAT")
    e = D.camada(cache, ano, "EQTRAT")[["UNI_TR_AT", "TEN_PRI", "TEN_SEC"]].drop_duplicates("UNI_TR_AT")
    t = u.merge(e, left_on="COD_ID", right_on="UNI_TR_AT", how="left")
    t["eh_mt"] = t.TEN_SEC.astype("string").str.strip().isin(tensoes_mt)
    return t


def _camadas_zip(zip_path: Path) -> dict[str, int]:
    import pyogrio

    fonte = K.fonte_do_zip(zip_path)
    return {n: int(pyogrio.read_info(fonte, layer=n)["features"]) for n, _ in pyogrio.list_layers(fonte)}


def snapshots_se_trafos(
    cache: Path,
    anos_snapshot: list[int],
    anos_cache: list[int],
    tensoes_mt: list[str],
    zips: Path | None = None,
    itens: dict | None = None,
    padrao_zip: str = K.PADRAO_ZIP,
) -> pd.DataFrame:
    """Subestações, trafos de SE e circuitos por snapshot. Os snapshots M10 (sem UNTRAT) vêm direto do zip."""
    linhas = []
    for ano in anos_snapshot:
        if ano in anos_cache and (Path(cache) / str(ano) / "UNTRAT.parquet").exists():
            t = _trafos_mt(cache, ano, tensoes_mt)
            pot = pd.to_numeric(t.POT_NOM, errors="coerce")
            mt = t[t.eh_mt]
            n_por_se = mt.groupby("SUB").size()
            linhas.append(
                {
                    "ano": ano,
                    "modelo": "V10/V11",
                    "camada_trafos": "UNTRAT",
                    "n_sub": len(D.camada(cache, ano, "SUB", ["COD_ID"])),
                    "n_ctmt": len(D.camada(cache, ano, "CTMT", ["COD_ID"])),
                    "n_trafos_se": len(t),
                    "cod_id_repetido": int(t.COD_ID.duplicated().sum()),
                    "n_trafos_mt": int(t.eh_mt.sum()),
                    "n_trafos_outra_tensao": int((~t.eh_mt).sum()),
                    "n_ses_com_trafo_mt": int(n_por_se.size),
                    "n_ses_1_trafo_mt": int((n_por_se == 1).sum()),
                    "n_ses_2mais_trafos_mt": int((n_por_se >= 2).sum()),
                    "pot_nominal_mt_mva": float(pd.to_numeric(mt.POT_NOM, errors="coerce").sum()),
                    "pot_nominal_mediana_mva": float(pot.median()),
                }
            )
        elif zips is not None and itens is not None:
            c = _camadas_zip(K.achar_zip(zips, ano, str(itens[ano]), padrao_zip))
            linhas.append(
                {
                    "ano": ano,
                    "modelo": "M10",
                    "camada_trafos": "UNTRS" if "UNTRS" in c else None,
                    "n_sub": c.get("SUB"),
                    "n_ctmt": c.get("CTMT"),
                    "n_trafos_se": c.get("UNTRS"),
                }
            )
    return pd.DataFrame(linhas)


def tensoes(cache: Path, anos: list[int]) -> pd.DataFrame:
    """Códigos de tensão (primário e secundário dos trafos de SE, tensão nominal dos circuitos) por snapshot."""
    linhas = []
    for ano in anos:
        e = D.camada(cache, ano, "EQTRAT", ["TEN_PRI", "TEN_SEC"])
        c = D.camada(cache, ano, "CTMT", ["TEN_NOM"])
        for camada, campo, s in [
            ("EQTRAT", "TEN_PRI", e.TEN_PRI),
            ("EQTRAT", "TEN_SEC", e.TEN_SEC),
            ("CTMT", "TEN_NOM", c.TEN_NOM),
        ]:
            for cod, n in s.astype("string").str.strip().fillna("(vazio)").value_counts().items():
                linhas.append({"ano": ano, "camada": camada, "campo": campo, "codigo": cod, "n": int(n)})
    return pd.DataFrame(linhas)


def vinculo_alimentador_trafo(
    cache: Path, interim: Path, anos: list[int], tensoes_mt: list[str], cobertura_minima: float
) -> pd.DataFrame:
    """Como o circuito (CTMT) se liga ao trafo e à SE, pela regra de MT e pela regra de MS (``decisoes_ems.md``)."""
    linhas = []
    for ano in anos:
        c = D.camada(cache, ano, "CTMT")
        u = D.camada(cache, ano, "UNTRAT", ["COD_ID", "SUB"])
        vazio = c.UNI_TR_AT.isna() | c.UNI_TR_AT.astype("string").str.strip().eq("")
        achado = c.UNI_TR_AT.isin(u.COD_ID)
        sub_tr = c.merge(u.rename(columns={"COD_ID": "UNI_TR_AT", "SUB": "SUB_TR"}), on="UNI_TR_AT", how="left")
        diverge = sub_tr.SUB_TR.notna() & (sub_tr.SUB != sub_tr.SUB_TR)
        ses_mt = set(_trafos_mt(cache, ano, tensoes_mt).query("eh_mt").SUB.astype(str))
        prefixo = c.NOME.astype(str).str.strip().str[:3]
        subs_por_prefixo = c.groupby(prefixo).SUB.nunique()
        linha = {
            "ano": ano,
            "n_ctmt": len(c),
            "uni_tr_at_vazio": int(vazio.sum()),
            "uni_tr_at_fora_de_untrat": int((~achado & ~vazio).sum()),
            "ctmt_sub_diferente_do_sub_do_trafo": int(diverge.sum()),
            "prefixos_de_3_letras": int(len(subs_por_prefixo)),
            "prefixos_com_mais_de_uma_ctmt_sub": int((subs_por_prefixo > 1).sum()),
        }
        for nome, opt in [
            ("mt", {"se_do_alimentador": "trafo", "vinculo": "trafo"}),
            ("ms", {"se_do_alimentador": "ctmt", "vinculo": "se"}),
        ]:
            a = D.alimentadores(cache, interim, ano, tensoes_mt=tensoes_mt, **opt)
            e = a[[f"ene_{m}" for m in D.MESES]].abs().sum(axis=1)
            cob = C.cobertura_vinculo(a)
            universo = cob[cob.index.isin(ses_mt)]
            linha |= {
                f"regra_{nome}_alimentadores_coerentes": int(a.vinculo_ok.sum()),
                f"regra_{nome}_pct_alimentadores": float(a.vinculo_ok.mean() * 100),
                f"regra_{nome}_pct_energia": float(e[a.vinculo_ok].sum() / e.sum() * 100),
                f"regra_{nome}_ses_no_universo": int(len(universo)),
                f"regra_{nome}_ses_cobertura_abaixo_do_minimo": int((universo < cobertura_minima).sum()),
            }
        linhas.append(linha)
    return pd.DataFrame(linhas)


def vinculo_se_registrada(
    cache: Path, interim: Path, interrupcoes: Path, anos_snapshot: list[int], ano_evento: int
) -> pd.DataFrame:
    """A SE gravada nas interrupções do ano novo (``subestacao``) bate com a SE do circuito: regra de MT ou de MS?

    O campo das interrupções do layout novo é independente do cadastro de trafos: serve de árbitro entre
    ``CTMT.SUB`` e ``UNTRAT.SUB`` do trafo apontado por ``CTMT.UNI_TR_AT``.
    """
    arq = Path(interrupcoes).as_posix()
    ev = duckdb.sql(f"""select alimentador_cod_id as codigo, subestacao from read_parquet('{arq}')
                        where ano = {ano_evento} and alimentador_cod_id is not null""").df()
    linhas = []
    for ano in anos_snapshot:
        cw = pd.read_parquet(Path(interim) / f"crosswalk_{ano}.parquet")
        c = D.camada(cache, ano, "CTMT", ["NOME", "SUB", "UNI_TR_AT"])
        c["alimentador"] = c.NOME.astype(str).str.strip().str.zfill(6)
        u = D.camada(cache, ano, "UNTRAT", ["COD_ID", "SUB"]).rename(columns={"COD_ID": "UNI_TR_AT", "SUB": "SUB_TR"})
        c = c.merge(u, on="UNI_TR_AT", how="left").drop_duplicates("alimentador")
        sub_ids = set(D.camada(cache, ano, "SUB", ["COD_ID"]).COD_ID.astype(str))
        e = ev.merge(cw, on="codigo", how="left")
        casado = e.dropna(subset=["alimentador"]).merge(
            c[["alimentador", "SUB", "SUB_TR"]], on="alimentador", how="inner"
        )
        div = casado[casado.SUB_TR.notna() & (casado.SUB != casado.SUB_TR)]
        linhas.append(
            {
                "snapshot": ano,
                "eventos": len(ev),
                "pct_casados_a_circuito_pelo_crosswalk": float(e.alimentador.notna().mean() * 100),
                "eventos_com_circuito_no_snapshot": len(casado),
                "pct_subestacao_existe_em_sub": float(casado.subestacao.astype(str).isin(sub_ids).mean() * 100),
                "pct_igual_a_ctmt_sub": float((casado.subestacao == casado.SUB).mean() * 100),
                "pct_igual_ao_sub_do_trafo": float((casado.subestacao == casado.SUB_TR).mean() * 100),
                "eventos_onde_as_duas_regras_divergem": len(div),
                "div_pct_igual_a_ctmt_sub": float((div.subestacao == div.SUB).mean() * 100) if len(div) else np.nan,
                "div_pct_igual_ao_sub_do_trafo": float((div.subestacao == div.SUB_TR).mean() * 100)
                if len(div)
                else np.nan,
            }
        )
    return pd.DataFrame(linhas)


def transferencia_na(cache: Path, interim: Path, anos: list[int], opcoes_alim: dict) -> pd.DataFrame:
    """Chaves normalmente abertas (NA) que ligam circuitos de SEs diferentes, por snapshot."""
    linhas = []
    for ano in anos:
        seg = Path(cache) / str(ano) / "SSDMT.parquet"
        if not seg.exists():
            continue
        k = D.camada(cache, ano, "UNSEMT", ["COD_ID", "PAC_1", "PAC_2", "P_N_OPE"])
        s = pd.read_parquet(seg, columns=["PAC_1", "PAC_2", "CTMT"])
        alim = D.alimentadores(cache, interim, ano, **opcoes_alim)
        na = k[k.P_N_OPE.astype(str).str.strip().eq("A")]
        pa = T.pac_alimentador(s)
        p1, p2 = na.PAC_1.isin(pa.pac), na.PAC_2.isin(pa.pac)
        pares = T.interligacoes(k, s, alim.set_index("alimentador_cod_id").se)
        com = T.alimentadores_com_transferencia(pares)
        uc = pd.to_numeric(alim.n_uc, errors="coerce").fillna(0.0)
        linhas.append(
            {
                "ano": ano,
                "chaves": len(k),
                "chaves_na": len(na),
                "pct_na": len(na) / len(k) * 100,
                "na_pac1_em_segmento_pct": float(p1.mean() * 100),
                "na_pac2_em_segmento_pct": float(p2.mean() * 100),
                "na_os_dois_pacs_em_segmento_pct": float((p1 & p2).mean() * 100),
                "pares_de_circuitos": len(pares),
                "pares_entre_ses": int(pares.entre_ses.sum()),
                "pares_na_mesma_se": int((~pares.entre_ses).sum()),
                "circuitos_com_transferencia": len(com),
                "circuitos": len(alim),
                "pct_uc_sem_transferencia": float(uc[~alim.alimentador_cod_id.isin(com)].sum() / uc.sum() * 100),
            }
        )
    return pd.DataFrame(linhas)


def vinculo_interrupcoes(
    interrupcoes: Path, interim: Path, cache: Path, anos_snapshot: list[int], ano_novo: int, opcoes_alim: dict
) -> pd.DataFrame:
    """Que fração das interrupções de MT (internas, não programadas) liga a um circuito e a uma SE do snapshot."""
    linhas = []
    for snap in anos_snapshot:
        alim = D.alimentadores(cache, interim, snap, **opcoes_alim)
        cw = P.crosswalk(interim, snap)
        anos_ev = list(range(snap - 2, snap + 1)) + ([ano_novo] if snap == max(anos_snapshot) else [])
        ev = E.eventos_mt(Path(interrupcoes), anos_ev)
        v = E.vincular(ev, cw, alim)
        for a, g in v.groupby("ano"):
            linhas.append(
                {
                    "snapshot": snap,
                    "ano_evento": int(a),
                    "eventos_mt": len(g),
                    "pct_com_circuito": float(g.alimentador.notna().mean() * 100),
                    "pct_com_se": float(g.se.notna().mean() * 100),
                    "pct_chi_com_se": float(g.chi[g.se.notna()].sum() / g.chi.sum() * 100),
                }
            )
    return pd.DataFrame(linhas)


def campos_cadastro(cache: Path, anos: list[int], tensoes_mt: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cobertura de cada campo dos trafos de MT por snapshot e estabilidade entre snapshots seguidos (mesmo COD_ID)."""
    cob, est = [], []
    por_ano = {}
    for ano in anos:
        t = _trafos_mt(cache, ano, tensoes_mt)
        t = t[t.eh_mt].copy()
        for c in ("POT_NOM", "POT_F01", "POT_F02", "PER_FER"):
            t[c] = pd.to_numeric(t[c], errors="coerce")
        t["ano_con"] = pd.to_datetime(t.DAT_CON, format="%d/%m/%Y", errors="coerce").dt.year
        por_ano[ano] = t
        n = len(t)
        validos = {
            "DAT_CON": t.ano_con.between(1950, ano),
            "POT_NOM": t.POT_NOM > 0,
            "POT_F01": t.POT_F01 > 0,
            "POT_F02": t.POT_F02 > 0,
            "PER_FER": t.PER_FER > 0,
        }
        valores = {
            "DAT_CON": t.DAT_CON,
            "POT_NOM": t.POT_NOM,
            "POT_F01": t.POT_F01,
            "POT_F02": t.POT_F02,
            "PER_FER": t.PER_FER,
        }
        for campo, ok in validos.items():
            v = valores[campo][ok]
            cob.append(
                {
                    "ano": ano,
                    "campo": campo,
                    "trafos_mt": n,
                    "validos": int(ok.sum()),
                    "pct_validos": ok.mean() * 100,
                    "valores_distintos": int(v.nunique()),
                    "pct_valor_mais_comum": float(v.value_counts(normalize=True).iloc[0] * 100) if len(v) else np.nan,
                }
            )
        r1 = (t.POT_F01 / t.POT_NOM)[t.POT_F01 > 0]
        r2 = (t.POT_F02 / t.POT_NOM)[t.POT_F02 > 0]
        cob.append(
            {
                "ano": ano,
                "campo": "POT_F01/POT_NOM",
                "trafos_mt": n,
                "validos": len(r1),
                "pct_validos": len(r1) / n * 100,
                "valores_distintos": int(r1.round(3).nunique()),
                "pct_valor_mais_comum": float(r1.round(3).value_counts(normalize=True).iloc[0] * 100),
            }
        )
        cob.append(
            {
                "ano": ano,
                "campo": "POT_F02/POT_NOM",
                "trafos_mt": n,
                "validos": len(r2),
                "pct_validos": len(r2) / n * 100,
                "valores_distintos": int(r2.round(3).nunique()),
                "pct_valor_mais_comum": float(r2.round(3).value_counts(normalize=True).iloc[0] * 100),
            }
        )
    for a, b in zip(anos[:-1], anos[1:], strict=True):
        for campo, casas in [("DAT_CON", None), ("POT_NOM", 4), ("POT_F01", 4), ("POT_F02", 4), ("PER_FER", 4)]:
            r = Q.estabilidade(por_ano[a], por_ano[b], "COD_ID", campo, casas)
            est.append(
                {"de": a, "para": b, "campo": campo, **r, "passa_criterio": Q.passa_estabilidade(r["frac_mudou"])}
            )
    return pd.DataFrame(cob), pd.DataFrame(est)


def _duplicatas_parquet(arquivo: Path, rotulo: str, chave: str | None = None) -> dict:
    p = Path(arquivo).as_posix()
    n, d = duckdb.sql(
        f"select count(*), (select count(*) from (select distinct * from read_parquet('{p}'))) from read_parquet('{p}')"
    ).fetchall()[0]
    linha = {"arquivo": rotulo, "linhas": n, "distintas": d, "repetidas": n - d, "pct_repetidas": (n - d) / n * 100}
    if chave:
        linha["chaves_distintas"] = duckdb.sql(f"select count(distinct {chave}) from read_parquet('{p}')").fetchall()[
            0
        ][0]
    return linha


def duplicatas(cache: Path, interrupcoes: Path, anos_cache: list[int], camadas: list[str]) -> pd.DataFrame:
    """count(*) contra count(distinct *) de todo arquivo da ANEEL que o projeto lê (interrupções e camadas da BDGD)."""
    linhas = []
    p = Path(interrupcoes).as_posix()
    por_ano = duckdb.sql(f"""select ano, count(*) n, (select count(*) from (select distinct * from read_parquet('{p}')
                             where ano = t.ano)) d from read_parquet('{p}') t group by ano order by ano""").df()
    for r in por_ano.itertuples():
        linhas.append(
            {
                "arquivo": f"interrupções {r.ano}",
                "linhas": int(r.n),
                "distintas": int(r.d),
                "repetidas": int(r.n - r.d),
                "pct_repetidas": (r.n - r.d) / r.n * 100,
            }
        )
    for ano in anos_cache:
        for camada in camadas:
            f = Path(cache) / str(ano) / f"{camada}.parquet"
            if f.exists():
                linhas.append(_duplicatas_parquet(f, f"BDGD {ano} {camada}", "COD_ID" if camada != "SSDMT" else None))
    return pd.DataFrame(linhas)


def estabilidade_se(cache: Path, anos: list[int], max_km: float = 1.0) -> pd.DataFrame:
    """Os códigos de SE (``SUB.COD_ID``) se mantêm entre snapshots? E as coordenadas?"""
    linhas = []
    sub = {a: D.subestacoes(cache, a) for a in anos}
    for a, b in zip(anos[:-1], anos[1:], strict=True):
        x, y = sub[a], sub[b]
        mapa = Va.casar_por_proximidade(x, y, max_km)
        pares = x.merge(y, left_on=x.se.map(mapa), right_on="se", suffixes=("", "_depois"))
        linhas.append(
            {
                "de": a,
                "para": b,
                "ses_de": len(x),
                "ses_para": len(y),
                "codigos_mantidos": len(set(x.se) & set(y.se)),
                "pct_codigos_mantidos": len(set(x.se) & set(y.se)) / len(x) * 100,
                "pareadas_por_coordenada": int(len(mapa)),
                "pct_pareadas_por_coordenada": len(mapa) / len(x) * 100,
                "pareadas_com_o_mesmo_nome_pct": float((pares.nome == pares.nome_depois).mean() * 100)
                if len(pares)
                else np.nan,
            }
        )
    return pd.DataFrame(linhas)


def escalas(cache: Path, interim: Path, anos: list[int], cfg: dict, eventos: pd.DataFrame) -> pd.DataFrame:
    """Como as entradas dos indicadores se distribuem entre as SEs frente aos limiares bom/ruim (sem calcular notas)."""
    sc = cfg["scores"]
    linhas = []
    for ano in anos:
        alim = D.alimentadores(cache, interim, ano, **config.opcoes_alimentador(cfg))
        trafos = D.trafos_se(cache, ano, **config.opcoes_trafos(cfg))
        ses = sorted(set(trafos[trafos.eh_mt].se) & set(alim.se))
        a = alim[alim.se.isin(ses)]
        carga = C.carga_mensal_se(alim, ano)
        entradas = {"n_uc": a.groupby("se").n_uc.sum(), "energia_gwh": carga.mean(axis=1).abs() * 8760 / 1000}
        cw = P.crosswalk(interim, ano)
        ev = E.vincular(eventos[eventos.ano.isin([ano - 2, ano - 1, ano])], cw, alim)
        hist = E.resumo_por_se(
            ev, E.eventos_se(ev, cfg["eventos"]["min_alimentadores_evento_se"]), [ano - 2, ano - 1, ano]
        )
        entradas["eventos_se_por_100k_uc"] = (
            hist.eventos_se_ano.reindex(ses).fillna(0) / entradas["n_uc"].reindex(ses) * 1e5
        )
        for nome, s in entradas.items():
            s = s.reindex(ses).dropna()
            bom, ruim = sc[nome]["bom"], sc[nome]["ruim"]
            linhas.append(
                {
                    "ano": ano,
                    "indicador": nome,
                    "n_ses": len(s),
                    "p10": s.quantile(0.1),
                    "mediana": s.median(),
                    "p90": s.quantile(0.9),
                    "bom": bom,
                    "ruim": ruim,
                    "pct_ses_no_bom_ou_melhor": float((s <= bom).mean() * 100),
                    "pct_ses_no_ruim_ou_pior": float((s >= ruim).mean() * 100),
                }
            )
    return pd.DataFrame(linhas)


def eventos_disponiveis(
    cache: Path,
    interim: Path,
    interrupcoes: Path,
    cfg: dict,
    ano_universo: int,
    anos_resultado: list[int],
    ano_novo: int,
    elemento: str,
) -> pd.DataFrame:
    """Quantos eventos e quantas SEs com evento existem na janela de validação (insumo da porta (b); não valida nada).

    O universo de SEs é o do snapshot ``ano_universo``: SEs com trafo de MT e com circuitos.
    """
    opt_a, opt_t = config.opcoes_alimentador(cfg), config.opcoes_trafos(cfg)
    alim_u = D.alimentadores(cache, interim, ano_universo, **opt_a)
    trafos_u = D.trafos_se(cache, ano_universo, **opt_t)
    universo = set(trafos_u[trafos_u.eh_mt].se) & set(alim_u.se)
    ev_todos = E.eventos_mt(Path(interrupcoes), anos_resultado + [ano_novo])
    alim_r = D.alimentadores(cache, interim, max(anos_resultado), **opt_a)
    ev = E.vincular(ev_todos[ev_todos.ano.isin(anos_resultado)], P.crosswalk(interim, max(anos_resultado)), alim_r)
    linhas = [
        {
            "resultado": "alimentadores por SE (snapshot do universo)",
            "limite": "-",
            "eventos": int(len(alim_u)),
            "ses_com_evento": int(alim_u.se.nunique()),
            "ses_com_evento_no_universo": int((alim_u.groupby("se").size() >= 3).sum()),
            "observacao": "ses_com_evento_no_universo = SEs com 3 ou mais circuitos",
        },
        {
            "resultado": "interrupções de MT (internas, não programadas) ligadas a SE",
            "limite": "-",
            "eventos": int(ev.se.notna().sum()),
            "ses_com_evento": int(ev.se.nunique()),
            "ses_com_evento_no_universo": int(len(set(ev.se.dropna()) & universo)),
            "observacao": f"anos {anos_resultado}",
        },
    ]
    for k in (2, 3, 4):
        es = E.eventos_se(ev, k)
        linhas.append(
            {
                "resultado": "eventos de SE (circuitos simultâneos no mesmo minuto)",
                "limite": f">= {k}",
                "eventos": int(len(es)),
                "ses_com_evento": int(es.se.nunique()),
                "ses_com_evento_no_universo": int(len(set(es.se) & universo)),
                "observacao": f"anos {anos_resultado}; o índice usa >= {cfg['eventos']['min_alimentadores_evento_se']}",
            }
        )
    dj = ev_todos[(ev_todos.ano == ano_novo) & (ev_todos.elemento == elemento)]
    linhas.append(
        {
            "resultado": f"aberturas por {elemento.lower()} em {ano_novo}",
            "limite": "-",
            "eventos": int(len(dj)),
            "ses_com_evento": int(dj.cod_subestacao.nunique()),
            "ses_com_evento_no_universo": int(len(set(dj.cod_subestacao.dropna().astype(str)) & universo)),
            "observacao": "interrupções de MT internas e não programadas com o elemento indicado",
        }
    )
    linhas.append(
        {
            "resultado": "universo de SEs",
            "limite": "-",
            "eventos": np.nan,
            "ses_com_evento": len(universo),
            "ses_com_evento_no_universo": len(universo),
            "observacao": f"snapshot {ano_universo}",
        }
    )
    return pd.DataFrame(linhas)
