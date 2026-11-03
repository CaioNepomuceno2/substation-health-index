import numpy as np
import pandas as pd
import pytest

from sehealth import carregamento as C
from sehealth import eventos as E
from sehealth import indice as I
from sehealth import topologia as T
from sehealth import validacao as V
from sehealth import valor as Vl


def _trafos(linhas):
    df = pd.DataFrame(linhas, columns=["se", "pot_mva", "pot_emerg_mva"])
    df["eh_mt"] = True
    df["trafo"] = [f"t{i}" for i in range(len(df))]
    return df


def test_score_linear_satura_e_log():
    s = I.score(pd.Series([0.4, 0.75, 1.2]), bom=0.5, ruim=1.0)
    assert s.tolist() == pytest.approx([0.0, 50.0, 100.0])
    s = I.score(pd.Series([1000, 10_000, 100_000]), bom=1000, ruim=100_000, log=True)
    assert s.tolist() == pytest.approx([0.0, 50.0, 100.0])


def test_media_ponderada_renormaliza_sem_dado():
    sc = pd.DataFrame({"a": [100.0, 100.0], "b": [0.0, np.nan]})
    m = I.media_ponderada(sc, {"a": 0.5, "b": 0.5})
    assert m.tolist() == pytest.approx([50.0, 100.0])


def test_capacidade_firme_perde_maior_trafo():
    cap = C.capacidade_se(_trafos([("A", 25, 30), ("A", 25, 30), ("B", 30, 36)]))
    assert cap.loc["A", "pot_firme_mva"] == pytest.approx(30)
    assert cap.loc["B", "pot_firme_mva"] == pytest.approx(0)  # SE de um trafo não tem capacidade firme
    assert cap.loc["A", "n_trafos"] == 2


def test_indicadores_carregamento_pico_utilizacao_deficit():
    carga = pd.DataFrame([[20.0] * 11 + [36.0]], index=["A"], columns=range(1, 13))  # MW médio por mês
    cap = C.capacidade_se(_trafos([("A", 25, 30), ("A", 25, 30)]))
    df = C.indicadores_carregamento(carga, cap, fator_carga=0.8, fator_potencia=0.9)
    pico = 36 / 0.8 / 0.9  # 50 MVA
    assert df.loc["A", "pico_mva"] == pytest.approx(pico)
    assert df.loc["A", "utilizacao_pico"] == pytest.approx(pico / 50)
    assert df.loc["A", "deficit_n1"] == pytest.approx((pico - 30) / pico)
    assert bool(df.loc["A", "sem_folga_n1"])


def test_fluxo_reverso_carrega_o_trafo_em_modulo():
    carga = pd.DataFrame([[-10.0] * 12], index=["A"], columns=range(1, 13))
    cap = C.capacidade_se(_trafos([("A", 25, 25)]))
    df = C.indicadores_carregamento(carga, cap, 1.0, 1.0)
    assert df.loc["A", "utilizacao_pico"] == pytest.approx(10 / 25)
    assert bool(df.loc["A", "fluxo_reverso"])


def test_carga_ignora_vinculo_incoerente():
    alim = pd.DataFrame({"se": ["A", "A"], "vinculo_ok": [True, False]})
    for m in range(1, 13):
        alim[f"ene_{m:02d}"] = [1000.0, 9_999_999.0]
    carga = C.carga_mensal_se(alim, 2025)
    assert carga.loc["A", 1] == pytest.approx(1000 / (31 * 24) / 1000)
    assert C.cobertura_vinculo(alim).loc["A"] == pytest.approx(1000 / (1000 + 9_999_999))


def _evento(se, alim, minuto, ano=2024, chi=100.0):
    return {"se": se, "alimentador": alim, "inicio": pd.Timestamp(f"{ano}-03-01 10:{minuto:02d}:20"),
            "chi": chi, "uc_afetadas": 10, "ano": ano}


def test_eventos_se_exige_alimentadores_simultaneos():
    ev = pd.DataFrame([_evento("A", "a1", 0), _evento("A", "a2", 0), _evento("A", "a3", 0),  # evento de SE
                       _evento("A", "a1", 5), _evento("A", "a2", 5),                        # só 2 alimentadores
                       _evento("B", "b1", 0)])
    s = E.eventos_se(ev, min_alimentadores=3)
    assert len(s) == 1 and s.iloc[0].se == "A" and s.iloc[0].chi == pytest.approx(300)


def test_resumo_so_usa_anos_pedidos():
    ev = pd.DataFrame([_evento("A", f"a{i}", 0, ano=2023) for i in range(3)]
                      + [_evento("A", f"a{i}", 0, ano=2024, chi=1e6) for i in range(3)])
    s = E.eventos_se(ev, 3)
    r = E.resumo_por_se(ev, s, [2022, 2023])
    assert r.loc["A", "eventos_se_ano"] == pytest.approx(0.5)
    assert r.loc["A", "chi_eventos_se_ano"] == pytest.approx(150)  # o evento de 2024 não vaza


def test_interligacao_entre_ses_por_chave_na():
    chaves = pd.DataFrame({"COD_ID": ["k1", "k2"], "PAC_1": ["p1", "p3"], "PAC_2": ["p2", "p4"],
                           "P_N_OPE": ["A", "F"]})
    seg = pd.DataFrame({"PAC_1": ["x", "y", "z", "w"], "PAC_2": ["p1", "p2", "p3", "p4"],
                        "CTMT": ["c1", "c2", "c1", "c3"]})
    pares = T.interligacoes(chaves, seg, pd.Series({"c1": "SE1", "c2": "SE2", "c3": "SE3"}))
    assert len(pares) == 1 and bool(pares.iloc[0].entre_ses)
    assert T.alimentadores_com_transferencia(pares) == {"c1", "c2"}


def test_ens_n1_um_trafo_perde_toda_a_carga_media():
    t = _trafos([("A", 25, 25), ("B", 25, 30), ("B", 25, 30)])
    ens = Vl.ens_n1_esperada_mwh(t, pd.Series({"A": 20.0, "B": 20.0}), taxa_falha=0.01, horas=72,
                                 fator_potencia=1.0)
    assert ens.loc["A"] == pytest.approx(0.01 * 72 * 20)
    assert ens.loc["B"] == pytest.approx(0.0)  # 20 MVA cabem nos 30 do trafo restante


def test_captura_top_e_ampliacoes_por_proximidade():
    assert V.captura_top(pd.Series([3, 2, 1, 0]), pd.Series([10, 0, 0, 0]), 0.25) == 1.0
    base = pd.DataFrame({"se": ["old1", "old2"], "lat": [-15.0, -10.0], "lon": [-56.0, -55.0],
                         "pot_instalada_mva": [50, 25], "n_trafos": [2, 1]})
    depois = pd.DataFrame({"se": ["n1", "n2"], "lat": [-15.001, -10.0], "lon": [-56.0, -55.0001],
                           "pot_instalada_mva": [75, 25], "n_trafos": [2, 1]})
    j = V.ampliacoes(base, depois).set_index("se")
    assert bool(j.loc["old1", "ampliou"]) and not bool(j.loc["old2", "ampliou"])


def test_indice_quadrantes_e_sensibilidade():
    df = pd.DataFrame({"x": [0.0, 1.0, 1.0, 0.0], "y": [0.0, 1.0, 0.0, 1.0]}, index=list("abcd"))
    cfg = {"scores": {"x": {"bom": 0, "ruim": 1}, "y": {"bom": 0, "ruim": 1}},
           "pesos": {"saude": {"x": 1.0}, "criticidade": {"y": 1.0}},
           "matriz": {"corte_saude": 50, "corte_criticidade": 50}}
    out = I.calcular(df, cfg)
    assert out.loc["b", "quadrante"].startswith("agir")
    assert out.loc["a", "quadrante"] == "manter"
    assert out.loc["b", "risco"] == pytest.approx(100)
    s = I.sensibilidade_pesos(df, cfg, n=20, k=1)
    assert s["top_k_estaveis_80pct"] == 1
