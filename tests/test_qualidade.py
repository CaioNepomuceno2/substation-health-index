"""Portas de qualidade pré-registradas (docs/decisoes_ems.md, seção 2)."""

import copy

import numpy as np
import pandas as pd
import pytest

from sehealth import config, qualidade
from sehealth import indice as I
from sehealth import validacao as Va


def test_estabilidade_mede_o_que_mudou_entre_cadastros():
    a = pd.DataFrame({"id": ["t1", "t2", "t3", "t4"], "DAT_CON": ["01/01/2000", "01/01/2001", "01/01/2002", "x"]})
    b = pd.DataFrame({"id": ["t1", "t2", "t3", "t9"], "DAT_CON": ["01/01/2000", "01/01/2010", "01/01/2002", "y"]})
    r = qualidade.estabilidade(a, b, "id", "DAT_CON")
    assert r == {"n_antes": 4, "n_comuns": 3, "n_mudou": 1, "frac_mudou": pytest.approx(1 / 3)}
    assert not qualidade.passa_estabilidade(r["frac_mudou"])
    assert qualidade.passa_estabilidade(0.10) and not qualidade.passa_estabilidade(0.1001)


def test_estabilidade_numerica_arredonda_e_trata_nulos():
    a = pd.DataFrame({"id": ["a", "b", "c"], "v": [0.04001, np.nan, 1.0]})
    b = pd.DataFrame({"id": ["a", "b", "c"], "v": [0.04002, np.nan, 2.0]})
    assert qualidade.estabilidade(a, b, "id", "v", casas=3)["n_mudou"] == 1  # só o "c"; nulo contra nulo é igual
    assert qualidade.estabilidade(a, b, "id", "v", casas=6)["n_mudou"] == 2


def test_porta_b_exige_ses_e_eventos_nos_limiares_exatos():
    ok = qualidade.porta_validacao(30, 200, 30, 200)
    assert ok["passou"] and ok["motivo"] == ""
    f_ses = qualidade.porta_validacao(29, 500, 30, 200)
    assert not f_ses["passou"] and "29 SEs" in f_ses["motivo"] and "eventos" not in f_ses["motivo"].split(";")[0]
    f_ev = qualidade.porta_validacao(45, 199, 30, 200)
    assert not f_ev["passou"] and "199 eventos" in f_ev["motivo"]
    ambos = qualidade.porta_validacao(18, 120, 30, 200)
    assert not ambos["passou"] and ambos["motivo"].count(";") == 1


def test_contagem_do_resultado_usa_so_as_ses_do_indice():
    v = pd.DataFrame({"eventos_se_ano_depois": [1.0, 0.0, 0.5, 2.0], "disjuntor_2026_n": [0, 3, 0, 4]})
    assert Va.contagem_resultado(v, "eventos_se_ano_depois", anos=2) == (3, 7)  # 1+0+0.5+2 eventos/ano x 2 anos
    assert Va.contagem_resultado(v, coluna_eventos="disjuntor_2026_n") == (2, 7)


def test_porta_a_recusa_peso_de_idade_quando_a_idade_nao_e_confiavel():
    cfg = {
        "qualidade": {"idade_trafo_confiavel": False},
        "pesos": {"saude": {"idade_anos": 0.2, "x": 0.8}},
        "scores": {},
        "matriz": {"corte_saude": 50, "corte_criticidade": 50},
    }
    with pytest.raises(ValueError, match="idade"):
        qualidade.verificar_pesos(cfg)
    with pytest.raises(ValueError, match="idade"):
        I.calcular(pd.DataFrame({"x": [1.0]}), cfg)
    ok = copy.deepcopy(cfg)
    ok["pesos"]["saude"].pop("idade_anos")
    qualidade.verificar_pesos(ok)
    qualidade.verificar_pesos({"pesos": {"saude": {"idade_anos": 0.2}}})  # padrão de MT: idade confiável


def test_configuracao_de_ms_passa_a_porta_a_e_recusa_idade(cfg_ms):
    qualidade.verificar_pesos(cfg_ms)
    assert "idade_anos" not in cfg_ms["pesos"]["saude"]
    ruim = copy.deepcopy(cfg_ms)
    ruim["pesos"]["saude"]["idade_anos"] = 0.2
    with pytest.raises(ValueError):
        qualidade.verificar_pesos(ruim)
    # a saúde de MS nem lê uma coluna de idade: o índice calcula sem ela
    df = pd.DataFrame(
        {
            "utilizacao_pico_pontuado": [0.9, 0.3],
            "deficit_n1_pontuado": [0.4, 0.0],
            "perdas_z": [1.0, 0.0],
            "eventos_se_por_100k_uc": [10.0, 0.0],
            "n_uc": [50000.0, 6000.0],
            "energia_gwh": [200.0, 30.0],
            "frac_uc_sem_transferencia": [1.0, 0.2],
            "frac_municipio": [1.0, 0.5],
        },
        index=["a", "b"],
    )
    out = I.calcular(df, cfg_ms)
    assert "score_idade_anos" not in out and out.saude.notna().all() and out.loc["a", "saude"] > out.loc["b", "saude"]


def test_ms_tem_a_porta_b_e_mt_nao(cfg_ms):
    assert qualidade.minimos_validacao(cfg_ms) == (30, 200)
    assert qualidade.minimos_validacao(config.carregar()) is None
