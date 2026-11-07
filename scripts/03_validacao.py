"""Validação: índice montado com dados até o ano de validação (MT: 2023) contra o que aconteceu depois.

Resultados medidos depois do corte (nunca entram no índice):
* eventos de SE (interrupções simultâneas em >= N alimentadores da SE) no período de resultado (MT: 2024-2025);
* interrupções abertas por DISJUNTOR no ano novo (MT: 2026, campo novo do layout da ANEEL, jan-jul).
E a checagem de decisões reais: SEs sem folga N-1 em 2021/2022/2023 foram ampliadas até 2025?

Com ``qualidade.validacao`` e ``validacao.portas_ampliacao`` na configuração (MS), cada afirmação só é publicada se
passar a porta pré-registrada em docs/decisoes_ems.md: o resultado que não passa não gera correlação, captura nem
baseline, só a contagem e o motivo em validacao_portas.json. Em MT (sem as portas) tudo é publicado, como antes.

Escolha a distribuidora com ``--config`` ou ``SEHEALTH_CONFIG`` (padrão: Energisa MT).
"""
import copy
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import dados as D  # noqa: E402
from sehealth import eventos as E  # noqa: E402
from sehealth import indice as I  # noqa: E402
from sehealth import painel as P  # noqa: E402
from sehealth import qualidade as Q  # noqa: E402
from sehealth import saidas as S  # noqa: E402
from sehealth import validacao as Va  # noqa: E402


def porta_ampliacao(base: pd.DataFrame, pareadas: int, params: dict, flag: str = "sem_folga_n1_multi") -> dict:
    """Porta (c): amostras mínimas de sinalizadas e não sinalizadas (2+ trafos) e pareamento por coordenada."""
    m = base[base.n_trafos >= 2]
    sinal, nao = int(m[flag].sum()), int((~m[flag]).sum())
    pct = pareadas / len(base) * 100 if len(base) else 0.0
    motivos = []
    if sinal < params["min_sinalizadas"]:
        motivos.append(f"só {sinal} SEs sinalizadas com 2+ trafos (mínimo {params['min_sinalizadas']})")
    if nao < params["min_nao_sinalizadas"]:
        motivos.append(f"só {nao} SEs não sinalizadas com 2+ trafos (mínimo {params['min_nao_sinalizadas']})")
    if pct < params["min_pct_pareadas"]:
        motivos.append(f"só {pct:.0f}% das SEs pareadas por coordenada (mínimo {params['min_pct_pareadas']}%)")
    return {"passou": not motivos, "sinalizadas_2mais_trafos": sinal, "nao_sinalizadas_2mais_trafos": nao,
            "ses_no_diagnostico": int(len(base)), "ses_pareadas": int(pareadas), "pct_pareadas": pct,
            "minimos": dict(params), "motivo": "; ".join(motivos)}


def amostra_minima(t: pd.DataFrame, params: dict) -> bool:
    """Um critério só é publicado se tem sinalizadas e não sinalizadas em número suficiente (``portas_ampliacao``)."""
    n = t.set_index("sinalizada").n_ses
    return bool(n.get(True, 0) >= params["min_sinalizadas"] and n.get(False, 0) >= params["min_nao_sinalizadas"])


def main(argv=None):
    cfg = config.carregar_args(__doc__, argv)
    d = cfg["dados"]
    val = config.validacao(cfg)
    t0, anos_res = d["ano_validacao"], d["anos_resultado"]
    ano_dec = d["ano_decisao"]
    cache, interim = Path(d["cache_bdgd"]), Path(d["interim_gridrisk"])
    PR, R = config.processed(cfg), config.reports(cfg)
    R.mkdir(parents=True, exist_ok=True)
    minimos = Q.minimos_validacao(cfg)

    base = pd.read_parquet(PR / f"painel_{t0}.parquet").set_index("se")
    idx = I.calcular(base, cfg)
    cfg_cad = copy.deepcopy(cfg)
    cfg_cad["pesos"]["saude"].pop("eventos_se_por_100k_uc")
    idx["saude_cadastral"] = I.calcular(base, cfg_cad).saude
    idx["risco_cadastral"] = idx.saude_cadastral * idx.criticidade / 100

    # --- resultados depois do corte, ligados com o snapshot mais recente (medição, não feature)
    ev = pd.read_parquet(PR / "eventos_mt.parquet")
    alim_res = D.alimentadores(cache, interim, max(anos_res), **config.opcoes_alimentador(cfg))
    evv = E.vincular(ev[ev.ano.isin(anos_res)], P.crosswalk(interim, max(anos_res)), alim_res)
    ev_se = E.eventos_se(evv, cfg["eventos"]["min_alimentadores_evento_se"])
    res = E.resumo_por_se(evv, ev_se, anos_res).add_suffix("_depois")

    dj = ev[(ev.ano == val["ano_disjuntor"]) & (ev.elemento == val["elemento_disjuntor"])]
    res = res.join(
        dj.groupby("cod_subestacao").agg(disjuntor_2026_n=("chi", "size"), disjuntor_2026_chi=("chi", "sum")),
        how="outer")
    removidas = []
    if val["so_ses_presentes_no_resultado"]:
        # uma SE cujo código não existe no snapshot do resultado não pode receber eventos: sai da amostra
        removidas = sorted(set(idx.index) - set(alim_res.se))
        idx = idx.drop(index=removidas)
    v = idx.join(res, how="left")
    cols_res = list(res.columns)
    v[cols_res] = v[cols_res].fillna(0)
    v["eventos_se_por_100k_uc_depois"] = v.eventos_se_ano_depois / v.n_uc * 1e5
    v["chi_eventos_se_por_uc_depois"] = v.chi_eventos_se_ano_depois / v.n_uc

    # --- porta (b): cada resultado só vira afirmação se tiver SEs e eventos suficientes
    portas, resultados = {}, []
    cols_por_se = ["se", "nome", "risco", "saude", "criticidade", "saude_cadastral", "chi_eventos_se_ano"]
    for rotulo, cols_resultado, cols_saida, contagem in [
        ("A_eventos_de_se", S.RESULTADOS_A, S.COLUNAS_POR_SE_A,
         Va.contagem_resultado(v, "eventos_se_ano_depois", len(anos_res))),
        ("B_disjuntor", S.RESULTADOS_B, S.COLUNAS_POR_SE_B,
         Va.contagem_resultado(v, coluna_eventos="disjuntor_2026_n")),
    ]:
        if minimos is None:
            portas[rotulo] = {"avaliada": False, "ses_com_evento": contagem[0], "eventos": contagem[1]}
        else:
            portas[rotulo] = {"avaliada": True, **Q.porta_validacao(*contagem, *minimos)}
        if minimos is None or portas[rotulo]["passou"]:
            resultados += cols_resultado
            cols_por_se += cols_saida

    tab = Va.comparar(v, S.preditores(cfg), resultados) if resultados else pd.DataFrame()
    if len(tab):
        tab.round(4).to_csv(R / "validacao_preditiva.csv", index=False)
        v.reset_index()[cols_por_se].round(3).to_csv(R / "validacao_por_se.csv", index=False)

    # --- decisões reais: ampliações depois do diagnóstico
    depois = pd.read_parquet(PR / f"painel_{ano_dec}.parquet")
    pa = val["portas_ampliacao"]
    multi_so_2mais = pa is not None
    amp, portas_amp = [], {}
    for ano in val["anos_diagnostico_ampliacao"]:
        b = pd.read_parquet(PR / f"painel_{ano}.parquet")
        b = b[~b.carregamento_incerto].copy()
        b["sem_folga_n1_multi"] = b.sem_folga_n1 & (b.n_trafos >= 2)
        b["utilizacao_acima_80"] = b.utilizacao_pico > 0.8
        if pa is not None:
            portas_amp[str(ano)] = porta_ampliacao(b, len(Va.ampliacoes(b, depois)), pa)
            if not portas_amp[str(ano)]["passou"]:
                continue
        sem_amostra = []
        for flag in ("sem_folga_n1", "sem_folga_n1_multi", "utilizacao_acima_80"):
            t = Va.taxa_ampliacao(b, depois, flag, min_trafos=2 if (multi_so_2mais and flag == "sem_folga_n1_multi")
                                  else None).assign(ano_base=ano, criterio=flag)
            if pa is not None and not amostra_minima(t, pa):
                sem_amostra.append(flag)       # a mesma amostra mínima da porta (c) vale para cada critério
                continue
            amp.append(t)
        if pa is not None:
            portas_amp[str(ano)]["criterios_sem_amostra_minima"] = sem_amostra
    if amp:
        pd.concat(amp, ignore_index=True).to_csv(R / "validacao_ampliacoes.csv", index=False)
    amp = pd.concat(amp, ignore_index=True) if amp else pd.DataFrame()

    cobertura = {
        f"ses_no_indice_{t0}": int(len(idx)) + len(removidas),
        "ses_com_resultado": int(v.chi_eventos_se_ano_depois.notna().sum()),
        f"eventos_se_{anos_res[0]}_{anos_res[-1]}": int(len(ev_se)),
        f"chi_eventos_se_{anos_res[0]}_{anos_res[-1]}": float(ev_se.chi.sum()),
        f"disjuntor_{val['ano_disjuntor']}_eventos_total": int(len(dj)),
        f"disjuntor_{val['ano_disjuntor']}_eventos_em_ses_do_indice": int(v.disjuntor_2026_n.sum()),
    }
    (R / "validacao_resumo.json").write_text(json.dumps(cobertura, indent=2, default=float))
    if minimos is not None or pa is not None:
        saida = {"ses_no_indice": int(len(idx)), "ses_removidas_por_ausencia_no_snapshot_do_resultado": removidas,
                 "validacao_com_eventos": portas, "ampliacoes_reais": portas_amp}
        (R / "validacao_portas.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=float))
    pd.set_option("display.width", 220)
    print(json.dumps(cobertura, indent=1))
    print(json.dumps({"portas": portas, "ampliacoes": portas_amp}, indent=1, ensure_ascii=False, default=float))
    if len(tab):
        print(tab.round(3).to_string())
    if len(amp):
        print(amp.round(3).to_string())


if __name__ == "__main__":
    main()
