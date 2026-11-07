"""Teste de fumaça de MS: os scripts 01 a 04 de ponta a ponta com a configuração de MS, em dados sintéticos.

Confere o que mudou para MS: nome de circuito alfanumérico, SE do circuito = CTMT.SUB, capacidade nominal, SE sem código
fora, saúde sem idade, rótulo ``origem_efeito`` e R$ por CHI do valor.json de MS, portas (b) e (c) e que nada é gravado
em ``reports/`` de MT.
"""

import hashlib
import importlib.util
import json

import pandas as pd
import pytest
from sintetico_ems import ROOT, config_de_teste, gravar_snapshot, montar_dados

from sehealth import config
from sehealth import dados as D
from sehealth import saidas as S

PORTAS_C_ABERTAS = {"min_sinalizadas": 1, "min_nao_sinalizadas": 1, "min_pct_pareadas": 50}


def _script(nome):
    spec = importlib.util.spec_from_file_location(f"script_{nome}", ROOT / "scripts" / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rodar_pipeline(yaml_path):
    for nome in ("01_paineis", "02_indice_decisao", "03_validacao", "04_figuras"):
        _script(nome).main(["--config", str(yaml_path)])


def _hashes(pasta):
    return {
        str(p.relative_to(pasta)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(pasta.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def dados(tmp_path):
    montar_dados(tmp_path)
    return tmp_path


def test_circuito_de_ms_ligado_pela_ctmt_sub_e_nome_canonico(dados):
    cache, interim = dados / "cache", dados / "interim"
    por_ctmt = D.alimentadores(cache, interim, 2025, se_do_alimentador="ctmt", vinculo="se", tensoes_mt=["49", "72"])
    por_trafo = D.alimentadores(cache, interim, 2025, tensoes_mt=["49", "72"])
    assert "0AJO51" in set(por_ctmt.alimentador) and por_ctmt.alimentador.str.len().eq(6).all()
    # BET52 aponta para um trafo da SE ALFA: MT (trafo apontado) a põe na SE 10, MS (CTMT.SUB) na SE 20
    assert por_trafo.set_index("alimentador").se["0BET52"] == "10"
    assert por_ctmt.set_index("alimentador").se["0BET52"] == "20"
    # circuitos de 34,5 kV numa SE que só tem trafo de 13,8 kV: incoerentes pela regra de MS
    v = por_ctmt.set_index("alimentador").vinculo_ok
    assert not v[["0DEL52", "0DEL53"]].any() and v[["0DEL51", "0AJO51", "0BET51", "0GAM51"]].all()


def test_capacidade_nominal_contra_estagios_de_ventilacao(dados):
    cache = dados / "cache"
    nominal = D.trafos_se(cache, 2025, ["49", "72"], capacidade_emergencia="nominal")
    estagios = D.trafos_se(cache, 2025, ["49", "72"])  # padrão de MT
    assert (
        nominal.set_index("trafo").pot_emerg_mva["100"] == 30 and estagios.set_index("trafo").pot_emerg_mva["100"] == 45
    )
    with pytest.raises(ValueError):
        D.trafos_se(cache, 2025, ["49"], capacidade_emergencia="outra")


def test_se_sem_codigo_sai_dos_trafos_e_dos_circuitos(dados):
    cache, interim = dados / "cache", dados / "interim"
    assert (D.trafos_se(cache, 2025, ["49"]).se.str.strip() == "").sum() == 1
    assert (D.trafos_se(cache, 2025, ["49"], excluir_se_sem_codigo=True).se.str.strip() != "").all()
    assert (D.alimentadores(cache, interim, 2025).se.str.strip() == "").sum() == 1
    assert (D.alimentadores(cache, interim, 2025, excluir_se_sem_codigo=True).se.str.strip() != "").all()


def test_fumaca_ms_pipeline_completo(dados):
    cfg_path = config_de_teste(
        dados,
        dados / "valor_ems.json",
        validacao={"min_ses_com_evento": 2, "min_eventos": 3},
        portas_ampliacao=PORTAS_C_ABERTAS,
    )
    antes = _hashes(ROOT / "reports")
    _rodar_pipeline(cfg_path)
    assert _hashes(ROOT / "reports") == antes  # nada foi gravado nos resultados publicados (MT nem MS)

    cfg = config.carregar(cfg_path)
    R = config.reports(cfg)
    assert R == dados / "reports" / "ems" and (dados / "processed" / "ems" / "painel_2025.parquet").exists()

    # --- índice: SEs, vínculo, capacidade nominal, saúde sem idade
    idx = pd.read_csv(R / "indice_2025.csv", dtype={"se": str}).set_index("se")
    assert sorted(idx.index) == ["10", "20", "30", "40"]  # a SE sem código ficou de fora
    assert "idade_anos" not in idx and "crescimento_aa" not in idx
    # a SE de carregamento incerto não tem posição no ranking complementar; as demais vão de 1 a 3
    assert pd.isna(idx.loc["40", "rank_risco_carregamento_confiavel"])
    assert sorted(idx.drop("40").rank_risco_carregamento_confiavel) == [1, 2, 3]
    assert idx.loc["10", "pico_mva"] == pytest.approx(40) and idx.loc["20", "pico_mva"] == pytest.approx(12)
    assert idx.loc["10", "pot_instalada_mva"] == 60 and idx.loc["10", "pot_firme_mva"] == 30  # nominal: 60 - 30
    assert idx.loc["10", "deficit_n1"] == pytest.approx((40 - 30) / 40) and bool(idx.loc["10", "sem_folga_n1"])
    assert idx.loc["30", "n_trafos"] == 4 and idx.loc["30", "pot_firme_mva"] == 45 and not idx.loc["30", "sem_folga_n1"]
    assert bool(idx.loc["40", "carregamento_incerto"]) and not idx.drop("40").carregamento_incerto.any()
    assert idx.loc["10", "frac_uc_sem_transferencia"] == pytest.approx(2 / 3, abs=1e-4)  # a chave NA liga AJO51 a BET51

    # --- rótulo de origem e R$ por CHI de MS (nunca os de MT)
    assert (idx.origem_efeito == "transportado de MT").all()
    assert (idx.rs_por_chi_social == 5.5604).all() and (idx.rs_por_chi_compensacao == 2.1484).all()
    assert idx.loc["10", "chi_eventos_se_ano"] == pytest.approx(1500)
    assert idx.loc["10", "rs_eventos_se_social"] == pytest.approx(1500 * 5.5604, rel=1e-3)
    assert idx.loc["10", "rs_eventos_se_social"] != pytest.approx(1500 * 5.943, rel=1e-3)
    resumo = json.loads((R / "resumo_2025.json").read_text(encoding="utf-8"))
    assert resumo["origem_efeito"] == "transportado de MT" and resumo["rs_por_chi_social"] == 5.5604
    assert resumo["n_ses"] == 4 and set(resumo["sensibilidades_da_configuracao"]) == {
        "estagios_cadastrados",
        "vinculo_regra_mt",
    }
    # a sensibilidade pelos estágios cadastrados dá firme 45 (2 x 45 - 45) para pico de 40: a SE ALFA deixa de ser
    # sinalizada
    assert resumo["sensibilidades_da_configuracao"]["estagios_cadastrados"]["ses_sem_folga_n1_com_2mais_trafos"] == 0
    assert resumo["ses_sem_folga_n1_com_2mais_trafos"] == 1

    # --- porta (b): eventos de SE passam (2 SEs, 4 eventos); disjuntor 2026 reprova (só a SE ALFA)
    portas = json.loads((R / "validacao_portas.json").read_text(encoding="utf-8"))
    a, b = portas["validacao_com_eventos"]["A_eventos_de_se"], portas["validacao_com_eventos"]["B_disjuntor"]
    assert a["passou"] and a["ses_com_evento"] == 2 and a["eventos"] == 4
    assert not b["passou"] and b["ses_com_evento"] == 1 and "1 SEs do índice" in b["motivo"]
    pred = pd.read_csv(R / "validacao_preditiva.csv")
    assert set(pred.resultado) == set(S.RESULTADOS_A)  # nada do resultado reprovado
    por_se = pd.read_csv(R / "validacao_por_se.csv")
    assert not any(c.startswith("disjuntor") for c in por_se.columns) and "eventos_se_ano_depois" in por_se
    assert "idade_anos" not in set(pred.preditor)
    # --- porta (c): a SE sinalizada (ALFA) não foi ampliada; a não sinalizada (GAMA, com o 4º trafo) foi
    amp = pd.read_csv(R / "validacao_ampliacoes.csv")
    m = amp[amp.criterio == "sem_folga_n1_multi"].set_index(["ano_base", "sinalizada"])
    assert m.loc[(2023, True), "taxa"] == 0 and m.loc[(2023, False), "taxa"] == 1
    assert all(portas["ampliacoes_reais"][str(a)]["passou"] for a in (2021, 2022, 2023))
    # nenhuma SE de teste passa de 80% de utilização: esse critério não tem sinalizadas e não é publicado
    assert set(amp.criterio) == {"sem_folga_n1", "sem_folga_n1_multi"}
    assert portas["ampliacoes_reais"]["2023"]["criterios_sem_amostra_minima"] == ["utilizacao_acima_80"]
    assert (R / "figures" / "05_validacao.png").exists() and (R / "figures" / "01_mapa_risco.png").exists()


def test_ms_com_as_duas_portas_reprovadas_publica_o_indice_sem_validacao(dados):
    cfg_path = config_de_teste(
        dados,
        dados / "valor_ems.json",
        validacao={"min_ses_com_evento": 50, "min_eventos": 1000},
        portas_ampliacao={"min_sinalizadas": 50, "min_nao_sinalizadas": 50, "min_pct_pareadas": 99},
    )
    _rodar_pipeline(cfg_path)
    R = config.reports(config.carregar(cfg_path))
    assert (R / "indice_2025.csv").exists() and (R / "figures" / "01_mapa_risco.png").exists()
    for nome in ("validacao_preditiva.csv", "validacao_por_se.csv", "validacao_ampliacoes.csv"):
        assert not (R / nome).exists(), nome
    assert not (R / "figures" / "05_validacao.png").exists()
    portas = json.loads((R / "validacao_portas.json").read_text(encoding="utf-8"))
    assert not portas["validacao_com_eventos"]["A_eventos_de_se"]["passou"]
    assert not portas["validacao_com_eventos"]["B_disjuntor"]["passou"]
    assert "mínimo 50" in portas["validacao_com_eventos"]["A_eventos_de_se"]["motivo"]
    assert all(not v["passou"] for v in portas["ampliacoes_reais"].values())
    assert "mínimo 50" in portas["ampliacoes_reais"]["2023"]["motivo"]


def test_ms_recusa_o_cache_de_outra_distribuidora(dados):
    gravar_snapshot(dados / "cache", dados / "interim", 2025, dist="405")  # cache com DIST de MT
    cfg_path = config_de_teste(dados, dados / "valor_ems.json")
    with pytest.raises(ValueError, match="distribuidora"):
        _script("01_paineis").main(["--config", str(cfg_path)])


def test_rotulo_de_origem_so_existe_fora_de_mt(cfg_ms):
    df = pd.DataFrame({"rs_risco_ano": [1.0, 2.0]})
    ms = S.anexar_rotulo(df, cfg_ms)
    assert list(ms.columns) == ["rs_risco_ano", "origem_efeito", "rs_por_chi_social", "rs_por_chi_compensacao"]
    assert (ms.origem_efeito == "transportado de MT").all() and (ms.rs_por_chi_social == 5.5604).all()
    pd.testing.assert_frame_equal(S.anexar_rotulo(df, config.carregar()), df)  # MT: o arquivo não muda
