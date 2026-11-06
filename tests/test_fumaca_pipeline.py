"""Teste de fumaça: a cadeia dos scripts 01 e 02 (cache BDGD -> painel -> índice -> valor), em 5 subestações sintéticas.

Cada subestação tem carga, trafos e interrupções escolhidos de modo que o resultado esperado se calcula à mão.
O cache da BDGD e as bases de interrupções são gerados aqui, em disco temporário, sem rede nem arquivos baixados.
"""
import numpy as np
import pandas as pd
import pytest

from sehealth import config
from sehealth import dados as D
from sehealth import eventos as E
from sehealth import indice as I
from sehealth import painel as P
from sehealth import validacao as Va
from sehealth import valor as V
from sehealth.carregamento import horas_mes

ANO = 2025
FP, FC = 0.92, 0.72  # fator de potência e razão média/pico do config padrão
# se: (potência de cada trafo em MVA, nº de trafos, pico mensal em MW, ano de instalação, UC por alimentador, município)
SES = {
    "A": (30, 2, 45 * FC * FP, 1985, 20000, "M0"),   # 45 MVA de pico: acima da capacidade firme (30 MVA)
    "B": (25, 2, 12 * FC * FP, 2015, 5000, "M1"),    # folgada
    "C": (20, 1, 15 * FC * FP, 2000, 8000, "M2"),    # um trafo só: sem capacidade firme
    "D": (15, 3, 24 * FC * FP, 2010, 10000, "M1"),   # divide o município com B
    "E": (25, 1, 10 * FC * FP, 2020, 1000, "M3"),    # vínculo trafo-alimentador incoerente: carga incerta
}
PERFIL = [1.0] + [0.8] * 11  # janeiro é o mês de pico
CRESCIMENTO_AA = 0.10


def _energia_kwh(pico_mw, mes, ano, escala):
    return pico_mw * PERFIL[mes - 1] * horas_mes(ano)[mes - 1] * 1000 * escala


def _gravar_snapshot(cache, interim, ano, escala):
    """Camadas da BDGD (Parquet) e a base de alimentadores do snapshot; ``escala`` multiplica a energia."""
    pasta = cache / str(ano)
    pasta.mkdir(parents=True)
    sub, untrat, eqtrat, ctmt, feeders, ssdmt = [], [], [], [], [], []
    for i, (se, (mva, n_tr, pico_mw, ano_inst, n_uc, mun)) in enumerate(SES.items()):
        sub.append({"COD_ID": se, "NOME": f"SUBESTACAO {se}", "lon": -56.0 - 0.1 * i, "lat": -15.0})
        for j in range(n_tr):
            untrat.append({"COD_ID": f"{se}{j}", "SUB": se, "MUN": mun, "POT_NOM": mva + 5 * j, "POT_F01": mva + 5 * j,
                           "POT_F02": mva + 5 * j, "PER_FER": 0.1 + 0.03 * i + 0.01 * j, "PER_TOT": 0.5,
                           "DAT_CON": f"01/06/{ano_inst}", "lon": -56.0 - 0.1 * i, "lat": -15.0})
            eqtrat.append({"UNI_TR_AT": f"{se}{j}", "TEN_PRI": "138", "TEN_SEC": "49", "DAT_IMO": f"01/06/{ano_inst}"})
        pesos = [1, 2, 2] if se == "E" else [1, 1, 1]  # em E, só o 1º alimentador tem vínculo coerente (20% da energia)
        for k, w in enumerate(pesos):
            cod = f"{se}_C{k}"
            ok = not (se == "E" and k > 0)
            ctmt.append({"COD_ID": cod, "NOME": f"{i * 3 + k + 1}", "SUB": se, "UNI_TR_AT": f"{se}{k % n_tr}",
                         "TEN_NOM": "49" if ok else "72",
                         **{f"ENE_{m:02d}": _energia_kwh(pico_mw, m, ano, escala) * w / sum(pesos)
                            for m in range(1, 13)}})
            feeders.append({"alimentador_cod_id": cod, "n_uc": float(n_uc), "rede_mt_km": 100.0, "frac_rural": 0.5})
            ssdmt.append({"PAC_1": f"{cod}_p1", "PAC_2": f"{cod}_p2", "CTMT": cod})
    # chave normalmente aberta entre A_C0 e B_C0 (SEs diferentes) e outra entre dois alimentadores da mesma SE (D)
    unsemt = [{"COD_ID": "k1", "PAC_1": "A_C0_p2", "PAC_2": "B_C0_p2", "P_N_OPE": "A"},
              {"COD_ID": "k2", "PAC_1": "D_C0_p2", "PAC_2": "D_C1_p2", "P_N_OPE": "A"},
              {"COD_ID": "k3", "PAC_1": "C_C0_p2", "PAC_2": "E_C0_p2", "P_N_OPE": "F"}]  # fechada: não é rota
    for nome, linhas in [("SUB", sub), ("UNTRAT", untrat), ("EQTRAT", eqtrat), ("CTMT", ctmt), ("SSDMT", ssdmt),
                         ("UNSEMT", unsemt)]:
        pd.DataFrame(linhas).to_parquet(pasta / f"{nome}.parquet", index=False)
    pd.DataFrame(feeders).to_parquet(interim / f"bdgd_feeders_{ano}.parquet", index=False)


def _gravar_interrupcoes(interim):
    """Três anos de interrupções: A tem um evento de SE por ano (3 alimentadores no mesmo minuto)."""
    base = {"alimentador_nome": None, "uc_afetadas": 1000, "duracao_h": 1.0, "elemento": "DISJUNTOR",
            "origem_mt": True, "origem": "INTERNA", "tipo": "NAO PROGRAMADA"}
    linhas = []
    for ano in (2023, 2024, 2025):
        t = pd.Timestamp(f"{ano}-03-10 14:05:20")
        linhas += [{**base, "alimentador_cod_id": f"A_C{k}", "subestacao": "A", "inicio": t, "chi": 500.0, "ano": ano}
                   for k in range(3)]
        linhas += [{**base, "alimentador_cod_id": f"D_C{k}", "subestacao": "D", "inicio": t, "chi": 100.0, "ano": ano}
                   for k in range(2)]  # só 2 alimentadores: não é evento de SE
        linhas += [{**base, "alimentador_cod_id": f"B_C{k}", "subestacao": "B", "inicio": t, "chi": 1e6, "ano": ano,
                    "tipo": "PROGRAMADA"} for k in range(3)]  # programada: não entra
    pd.DataFrame(linhas).to_parquet(interim / "interrupcoes_emt.parquet", index=False)
    cw = pd.DataFrame([{"codigo": f"{se}_C{k}", "alimentador": f"{i * 3 + k + 1}".zfill(6)}
                       for i, se in enumerate(SES) for k in range(3)])
    cw.to_parquet(interim / f"crosswalk_{ANO}.parquet", index=False)


def test_fumaca_pipeline_cache_painel_indice_valor(tmp_path):
    cache, interim = tmp_path / "cache", tmp_path / "interim"
    interim.mkdir()
    _gravar_snapshot(cache, interim, ANO, 1.0)
    _gravar_snapshot(cache, interim, ANO - 2, 1 / (1 + CRESCIMENTO_AA) ** 2)
    _gravar_interrupcoes(interim)
    cfg = config.carregar()
    cfg["dados"].update(cache_bdgd=str(cache), interim_gridrisk=str(interim))
    anos = [ANO - 2, ANO - 1, ANO]

    # script 01: eventos e painel do snapshot (passando pelo Parquet, como no script)
    ev = E.eventos_mt(interim / "interrupcoes_emt.parquet", anos)
    assert set(ev.codigo) == {f"{se}_C{k}" for se in "AD" for k in range(3)} - {"D_C2"}  # sem as programadas de B
    P.montar(cfg, ANO, ev, anos).to_parquet(tmp_path / f"painel_{ANO}.parquet", index=False)

    # script 02: índice de saúde x criticidade e valor do risco
    df = pd.read_parquet(tmp_path / f"painel_{ANO}.parquet").set_index("se")
    assert sorted(df.index) == sorted(SES)
    idx = V.priorizar(I.calcular(df, cfg), cfg)

    # carregamento: kWh dos alimentadores -> MW -> MVA de pico, utilização e déficit N-1 (conta à mão)
    pico_mva = {se: pico_mw / FC / FP for se, (_, _, pico_mw, *_) in SES.items()}
    for se in "ABCD":
        assert idx.loc[se, "pico_mva"] == pytest.approx(pico_mva[se])
    assert idx.loc["A", "utilizacao_pico"] == pytest.approx(45 / 65)  # trafos de 30 e 35 MVA
    assert idx.loc["A", "pot_firme_mva"] == pytest.approx(30)
    assert idx.sem_folga_n1.to_dict() == {"A": True, "B": False, "C": True, "D": False, "E": True}
    assert idx.loc["A", "deficit_n1"] == pytest.approx((45 - 30) / 45)
    assert idx.loc["C", "deficit_n1"] == pytest.approx(1.0)  # um trafo só: perde toda a carga se falhar
    # vínculo incoerente: a carga de E não é pontuada e a ampliação de E não é proposta
    assert idx.loc["E", "carregamento_incerto"] and idx.loc["E", "cobertura_vinculo"] == pytest.approx(0.2)
    assert not idx.drop("E").carregamento_incerto.any()
    assert np.isnan(idx.loc["E", "utilizacao_pico_pontuado"]) and idx.loc["E", "mva_ampliacao"] == 0
    assert idx.loc["A", "mva_ampliacao"] == pytest.approx(15) and idx.loc["B", "mva_ampliacao"] == 0
    assert idx.loc["A", "capex_ampliacao_rs"] == pytest.approx(15 * cfg["valor"]["custo_ampliacao_rs_mva"])
    # crescimento de energia entre os snapshots e transferência de carga pelas chaves NA
    assert df.crescimento_aa.to_numpy() == pytest.approx(CRESCIMENTO_AA)
    assert df.frac_uc_sem_transferencia.to_dict() == pytest.approx(
        {"A": 2 / 3, "B": 2 / 3, "C": 1.0, "D": 1.0, "E": 1.0})

    # eventos de SE (3 alimentadores no mesmo minuto) e o R$ que deles sai
    assert idx.eventos_se_ano.to_dict() == pytest.approx({"A": 1.0, "B": 0, "C": 0, "D": 0, "E": 0})
    assert idx.loc["A", "chi_eventos_se_ano"] == pytest.approx(1500)
    assert idx.loc["D", "chi_alimentadores_ano"] == pytest.approx(200)  # exposição conta, evento de SE não
    assert idx.loc["A", "rs_eventos_se_social"] == pytest.approx(1500 * cfg["valor"]["rs_por_chi_social"])
    media_c = idx.loc["C", "mw_medio"]  # trafo único: ENS = taxa x horas x carga média (o fator de potência se cancela)
    assert idx.loc["C", "ens_n1_mwh_ano"] == pytest.approx(
        cfg["valor"]["taxa_falha_trafo_ano"] * cfg["valor"]["horas_reposicao"] * media_c)
    soma = idx.rs_eventos_se_social.fillna(0) + idx.rs_ens_n1.fillna(0)
    assert idx.rs_risco_ano.to_numpy() == pytest.approx(soma.to_numpy())

    # índice: scores, saúde, criticidade e risco em [0, 100]; risco = saúde x criticidade / 100
    for c in ["saude", "criticidade", "risco"]:
        assert idx[c].between(0, 100).all(), c
    assert idx.risco.to_numpy() == pytest.approx((idx.saude * idx.criticidade / 100).to_numpy())
    scores = idx[[c for c in idx if c.startswith("score_")]].fillna(0).to_numpy()
    assert scores.min() >= 0 and scores.max() <= 100
    assert idx.loc["A", "score_utilizacao_pico_pontuado"] > idx.loc["B", "score_utilizacao_pico_pontuado"]
    assert idx.loc["A", "score_idade_anos"] > idx.loc["E", "score_idade_anos"]  # trafo de 1985 x de 2020
    assert idx.loc["A", "criticidade"] > idx.loc["E", "criticidade"]  # 60 mil UC x 3 mil UC
    assert idx.risco.idxmax() == "A"
    assert set(idx.quadrante) <= {"agir: ampliar/substituir", "planejar: condição ruim, baixa consequência",
                                  "monitorar: condição boa, alta consequência", "manter"}

    # sensibilidade dos pesos (poucos sorteios) e validação preditiva contra o resultado do ano seguinte
    s = I.sensibilidade_pesos(df, cfg, n=20, k=2)
    assert -1 <= s["spearman_p05"] <= s["spearman_mediano"] <= 1 and 0 <= s["top_k_estaveis_80pct"] <= 2
    assert s["presenca_top_k"].between(0, 1).all()
    evv = E.vincular(ev, P.crosswalk(interim, ANO), D.alimentadores(cache, interim, ANO))
    depois = E.resumo_por_se(evv, E.eventos_se(evv, 3), [ANO]).add_suffix("_depois")
    v = idx.join(depois, how="left").fillna({"chi_eventos_se_ano_depois": 0.0})
    comp = Va.comparar(v, ["risco", "saude"], ["chi_eventos_se_ano_depois"]).set_index("preditor")
    assert comp[["captura_top10", "captura_top20"]].fillna(0).to_numpy().min() >= 0
    assert comp.loc["risco", "captura_top10"] == pytest.approx(1.0)  # o índice aponta A, onde estão os eventos
