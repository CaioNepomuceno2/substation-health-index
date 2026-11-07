"""Diagnósticos de dados (os números de docs/decisoes_ems.md) em dados sintéticos de MS."""

import pandas as pd
import pytest
from sintetico_ems import ANOS, montar_dados

from sehealth import config
from sehealth import diagnostico as Dg


@pytest.fixture
def dados(tmp_path):
    montar_dados(tmp_path)
    return tmp_path


def test_snapshots_se_trafos_conta_trafos_de_mt_e_ses(dados):
    t = Dg.snapshots_se_trafos(dados / "cache", ANOS, ANOS, ["49", "72"]).set_index("ano")
    assert t.loc[2025, "n_trafos_se"] == 9 and t.loc[2025, "n_trafos_mt"] == 9  # 2+1+4+1 e o trafo sem SE
    assert t.loc[2021, "n_sub"] == 4 and t.loc[2021, "cod_id_repetido"] == 0
    assert t.loc[2025, "n_ses_com_trafo_mt"] == 5 and t.loc[2025, "n_ses_1_trafo_mt"] == 3  # BETA, DELTA, sem código
    semcod = Dg.snapshots_se_trafos(dados / "cache", ANOS, ANOS, ["49", "72"], excluir_se_sem_codigo=True)
    assert semcod.set_index("ano").loc[2025, "n_ses_com_trafo_mt"] == 4


def test_vinculo_se_registrada_pelo_campo_das_interrupcoes_de_2026(dados):
    r = Dg.vinculo_se_registrada(
        dados / "cache", dados / "interim", dados / "interim" / "interrupcoes_ems.parquet", [2025], 2026
    ).iloc[0]
    assert r.pct_casados_a_circuito_pelo_crosswalk == 100 and r.pct_subestacao_existe_em_sub > 0
    assert r.pct_igual_a_ctmt_sub == 100  # a SE gravada em 2026 é a CTMT.SUB
    # BET52 aponta para um trafo da SE ALFA: nesses eventos a SE do trafo erra e CTMT.SUB acerta
    assert r.eventos_onde_as_duas_regras_divergem == 1
    assert r.div_pct_igual_a_ctmt_sub == 100 and r.div_pct_igual_ao_sub_do_trafo == 0
    assert r.pct_igual_ao_sub_do_trafo < 100


def test_vinculo_alimentador_trafo_compara_as_duas_regras(dados):
    v = Dg.vinculo_alimentador_trafo(dados / "cache", dados / "interim", [2025], ["49", "72"], 0.8).iloc[0]
    assert v.ctmt_sub_em_branco == 1 and v.untrat_sub_em_branco == 1
    assert v.ctmt_sub_diferente_do_sub_do_trafo == 1 and v.prefixos_com_mais_de_uma_ctmt_sub == 0
    assert v.regra_ms_alimentadores_coerentes > v.regra_mt_alimentadores_coerentes - 1
    assert v.regra_ms_pct_alimentadores < 100  # DEL52 e DEL53 são de 34,5 kV, a SE só tem trafo de 13,8 kV


def test_campos_cadastro_aponta_o_campo_que_muda_entre_cadastros(dados):
    from sintetico_ems import gravar_snapshot

    gravar_snapshot(dados / "cache", dados / "interim", 2025)
    u = pd.read_parquet(dados / "cache" / "2025" / "UNTRAT.parquet")
    u.loc[u.COD_ID.isin(["100", "200", "300"]), "DAT_CON"] = "01/01/2010"  # 3 de 9 trafos trocam de data
    u.loc[u.COD_ID == "400", "POT_F01"] = 99.0
    u.to_parquet(dados / "cache" / "2025" / "UNTRAT.parquet", index=False)
    cob, est = Dg.campos_cadastro(dados / "cache", [2024, 2025], ["49", "72"])
    e = est.set_index("campo")
    assert e.loc["DAT_CON", "n_mudou"] == 3 and not e.loc["DAT_CON", "passa_criterio"]
    assert e.loc["POT_NOM", "n_mudou"] == 0 and e.loc["POT_NOM", "passa_criterio"]
    assert e.loc["POT_F01", "n_mudou"] == 1
    c = cob[(cob.ano == 2025) & (cob.campo == "POT_F02/POT_NOM")].iloc[0]
    assert c.valores_distintos == 1 and c.pct_valor_mais_comum == 100  # estágios 1,5x em todos os trafos


def test_energia_e_duplicatas_e_transferencia(dados):
    opt = config.opcoes_alimentador(
        {
            "eletrico": {
                "tensoes_secundario_mt": ["49", "72"],
                "se_do_alimentador": "ctmt",
                "vinculo_alimentador": "se",
                "excluir_se_sem_codigo": True,
            }
        }
    )
    por_ano, trans = Dg.energia_circuitos(dados / "cache", dados / "interim", [2024, 2025], opt)
    assert por_ano.loc[0, "meses_negativos"] == 0 and por_ano.loc[0, "kwh_por_uc"] > 0
    assert (
        trans.loc[0, "circuito_razao_mediana"] == pytest.approx(1.0, abs=0.01)
        and trans.loc[0, "se_spearman_energia"] == 1.0
    )
    d = Dg.duplicatas(dados / "cache", dados / "interim" / "interrupcoes_ems.parquet", [2025], ["CTMT", "UNTRAT"])
    assert (d.repetidas == 0).all() and set(d.arquivo) >= {"interrupções 2026", "BDGD 2025 CTMT"}
    na = Dg.transferencia_na(dados / "cache", dados / "interim", [2025], opt).iloc[0]
    assert na.chaves_na == 2 and na.pares_entre_ses == 1 and na.pares_na_mesma_se == 1
    assert na.circuitos_com_transferencia == 2


def test_eventos_disponiveis_conta_eventos_de_se_e_disjuntor(dados, cfg_ms):
    cfg = dict(cfg_ms)
    cfg["eletrico"] = {**cfg_ms["eletrico"]}
    ev = Dg.eventos_disponiveis(
        dados / "cache",
        dados / "interim",
        dados / "interim" / "interrupcoes_ems.parquet",
        cfg,
        2023,
        [2024, 2025],
        2026,
        "DISJUNTOR",
    ).set_index(["resultado", "limite"])
    a3 = ev.loc[("eventos de SE (circuitos simultâneos no mesmo minuto)", ">= 3")]
    assert a3.eventos == 4 and a3.ses_com_evento == 2  # SEs ALFA e GAMA, 2 anos cada
    assert ev.loc[("aberturas por disjuntor em 2026", "-")].eventos == 3
