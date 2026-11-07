"""Multi-distribuidora: a configuração padrão é a de MT (caminhos e parâmetros de hoje) e MS entra só por --config."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from conftest import ROOT, yaml_ems_com_valor

from sehealth import config, qualidade
from sehealth import saidas as S

# --- guarda de MT: o que a configuração padrão resolve hoje, escrito por extenso (não derivado da própria configuração)


def test_padrao_resolve_exatamente_os_caminhos_de_mt():
    cfg = config.carregar()
    assert cfg["dados"]["distribuidora"] == "EMT"
    assert cfg["dados"]["cache_bdgd"] == str(ROOT / "data" / "bdgd-cache")
    assert Path(cfg["dados"]["interim_gridrisk"]) == (ROOT.parent / "distribution-asset-risk" / "data" / "interim")
    assert config.arquivo_interrupcoes(cfg) == (
        ROOT.parent / "distribution-asset-risk" / "data" / "interim" / "interrupcoes_emt.parquet"
    )
    assert config.reports(cfg) == ROOT / "reports"
    assert config.figuras(cfg) == ROOT / "reports" / "figures"
    assert config.processed(cfg) == ROOT / "data" / "processed"
    assert config.malha_ibge(cfg) == ROOT / "ref" / "mt_ibge.geojson"
    assert config.nome_curto(cfg) == "Energisa MT" and config.nome(cfg) == "Energisa Mato Grosso"
    assert config.eh_mt(cfg)


def test_padrao_mantem_parametros_e_listas_de_mt():
    cfg = config.carregar()
    assert cfg["valor"]["rs_por_chi_social"] == 5.943 and cfg["valor"]["rs_por_chi_compensacao"] == 1.926
    assert "origem_efeito" not in cfg["valor"] and "valor_json" not in cfg["valor"]
    assert cfg["eletrico"]["tensoes_secundario_mt"] == ["38", "49", "72"]
    assert cfg["pesos"]["saude"] == {
        "utilizacao_pico_pontuado": 0.30,
        "deficit_n1_pontuado": 0.30,
        "idade_anos": 0.20,
        "perdas_z": 0.05,
        "eventos_se_por_100k_uc": 0.15,
    }
    assert config.anos_paineis(cfg) == [2021, 2022, 2023, 2024, 2025]
    assert config.anos_interrupcoes(cfg) == list(range(2018, 2027))
    assert config.fatores_carga_sensibilidade(cfg) == [0.62, 0.82]
    assert config.validacao(cfg) == {
        "anos_diagnostico_ampliacao": [2021, 2022, 2023],
        "ano_disjuntor": 2026,
        "elemento_disjuntor": "DISJUNTOR",
        "so_ses_presentes_no_resultado": False,
        "portas_ampliacao": None,
    }
    assert qualidade.minimos_validacao(cfg) is None  # MT não tem a porta (b)
    assert config.opcoes_alimentador(cfg) == {
        "se_do_alimentador": "trafo",
        "vinculo": "trafo",
        "tensoes_mt": ["38", "49", "72"],
        "excluir_se_sem_codigo": False,
    }
    assert config.opcoes_trafos(cfg) == {
        "tensoes_mt": ["38", "49", "72"],
        "sobrecarga_emergencia": 1.0,
        "capacidade_emergencia": "estagios",
        "excluir_se_sem_codigo": False,
    }
    assert config.zips_locais(cfg) is None and cfg.get("sensibilidades") is None


def test_padrao_mt_publica_as_listas_literais_de_hoje():
    cfg = config.carregar()
    assert S.colunas_indice(cfg) == S.COLUNAS_INDICE_MT and "idade_anos" in S.colunas_indice(cfg)
    assert S.preditores(cfg) == [
        "risco",
        "saude",
        "risco_cadastral",
        "saude_cadastral",
        "chi_eventos_se_ano",
        "eventos_se_por_100k_uc",
        "n_uc",
        "idade_anos",
    ]
    assert S.COLUNAS_INDICE_MT[:6] == ["rank_risco", "nome", "quadrante", "risco", "saude", "criticidade"]
    assert S.RESULTADOS_A + S.RESULTADOS_B == [
        "chi_eventos_se_ano_depois",
        "eventos_se_ano_depois",
        "eventos_se_por_100k_uc_depois",
        "chi_eventos_se_por_uc_depois",
        "disjuntor_2026_n",
        "disjuntor_2026_chi",
    ]
    assert S.rotulo_valor(cfg) == {}  # nenhum rótulo, nenhuma coluna nova nos arquivos de MT
    assert S.nome_painel_fc(2025, 0.62) == "painel_2025_fc62.parquet" and S.chave_fc(0.82) == "fc_0.82"


def test_yaml_antigo_sem_as_chaves_novas_cai_nos_padroes_de_mt(tmp_path):
    cfg = yaml.safe_load((ROOT / "configs" / "premissas.yaml").read_text(encoding="utf-8"))
    for k in ("paths", "cod_aneel", "nome", "nome_curto"):
        cfg.pop(k, None)
        cfg["dados"].pop(k, None)
    p = tmp_path / "antigo.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    antigo, atual = config.carregar(p), config.carregar()
    assert antigo["paths"] == atual["paths"] and config.nome_curto(antigo) == "Energisa MT"
    assert config.arquivo_interrupcoes(antigo) == config.arquivo_interrupcoes(atual)


def test_configuracao_de_mt_nao_perdeu_nenhum_parametro():
    """As seções de parâmetros de premissas.yaml seguem as de MT (a configuração de MS não as altera por engano)."""
    cfg = yaml.safe_load((ROOT / "configs" / "premissas.yaml").read_text(encoding="utf-8"))
    assert cfg["eletrico"] == {
        "fator_potencia": 0.92,
        "fator_carga_se": 0.72,
        "sobrecarga_emergencia": 1.0,
        "tensoes_secundario_mt": ["38", "49", "72"],
        "cobertura_minima_vinculo": 0.8,
    }
    assert cfg["scores"]["idade_anos"] == {"bom": 10, "ruim": 40} and cfg["matriz"] == {
        "corte_saude": 50,
        "corte_criticidade": 50,
    }
    assert cfg["valor"]["rs_por_chi_social"] == 5.943 and cfg["valor"]["custo_ens_rs_mwh"] == 7000
    assert cfg["dados"]["ano_decisao"] == 2025 and cfg["dados"]["ano_validacao"] == 2023


# --- seleção da distribuidora: --config, variável de ambiente, padrão


def test_variavel_de_ambiente_e_argumento_escolhem_a_configuracao(tmp_path, valor_json_ms, monkeypatch):
    ems = yaml_ems_com_valor(tmp_path, valor_json_ms)
    monkeypatch.setenv(config.CONFIG_ENV, str(ems))
    assert config.sigla(config.carregar()) == "EMS"
    outra = config.carregar(ROOT / "configs" / "premissas.yaml")  # o argumento vence a variável
    assert config.sigla(outra) == "EMT"
    monkeypatch.delenv(config.CONFIG_ENV)
    assert config.sigla(config.carregar()) == "EMT"
    with pytest.raises(FileNotFoundError):
        config.carregar(tmp_path / "nao_existe.yaml")


def test_scripts_aceitam_config_na_linha_de_comando(tmp_path, valor_json_ms):
    ems = yaml_ems_com_valor(tmp_path, valor_json_ms)
    cfg = config.carregar_args("teste", ["--config", str(ems)])
    assert config.sigla(cfg) == "EMS"
    assert config.sigla(config.carregar_args("teste", [])) == "EMT"


def test_ms_resolve_para_subpastas_ems_e_para_o_valor_de_ms(cfg_ms):
    assert config.sigla(cfg_ms) == "EMS" and config.nome_curto(cfg_ms) == "Energisa MS"
    assert config.reports(cfg_ms) == ROOT / "reports" / "ems"
    assert config.processed(cfg_ms) == ROOT / "data" / "ems" / "processed"
    assert cfg_ms["dados"]["cache_bdgd"] == str(ROOT / "data" / "ems" / "bdgd-cache")
    assert Path(cfg_ms["dados"]["interim_gridrisk"]) == (
        ROOT.parent / "distribution-asset-risk" / "data" / "ems" / "interim"
    )
    assert config.arquivo_interrupcoes(cfg_ms).name == "interrupcoes_ems.parquet"
    assert config.malha_ibge(cfg_ms) == ROOT / "ref" / "ms_ibge.geojson" and config.malha_ibge(cfg_ms).exists()
    assert [int(a) for a in cfg_ms["bdgd"]["snapshots"]] == list(range(2018, 2026))
    assert cfg_ms["eletrico"]["tensoes_secundario_mt"] == ["49", "72"]
    # R$ por CHI e rótulo vêm do valor.json de MS, nunca os de MT
    assert cfg_ms["valor"]["rs_por_chi_social"] == 5.5604 != 5.943
    assert cfg_ms["valor"]["rs_por_chi_compensacao"] == 2.1484 != 1.926
    assert cfg_ms["valor"]["origem_efeito"] == "transportado de MT"


def test_ms_nunca_grava_nas_pastas_de_mt(cfg_ms):
    for chave, mt in [("reports", "reports"), ("processed", "data/processed")]:
        ruim = copy.deepcopy(cfg_ms)
        ruim["paths"][chave] = str((ROOT / mt).resolve())
        with pytest.raises(ValueError, match="pasta de MT"):
            config.verificar_saidas(ruim)
    config.verificar_saidas(cfg_ms)


def test_ms_recusa_yaml_com_saida_na_pasta_de_mt(tmp_path, valor_json_ms):
    cfg = yaml.safe_load(yaml_ems_com_valor(tmp_path, valor_json_ms).read_text(encoding="utf-8"))
    cfg["paths"]["reports"] = "reports"
    p = tmp_path / "ruim.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="pasta de MT"):
        config.carregar(p)


def test_outra_distribuidora_exige_valor_json_com_origem_efeito(tmp_path, valor_json_ms):
    sem = yaml.safe_load((ROOT / "configs" / "premissas_ems.yaml").read_text(encoding="utf-8"))
    sem["valor"].pop("valor_json")
    p = tmp_path / "sem_valor.yaml"
    p.write_text(yaml.safe_dump(sem), encoding="utf-8")
    with pytest.raises(ValueError, match="valor_json"):
        config.carregar(p)
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps({"rs_por_chi_social": 1.0, "rs_por_chi_compensacao": 1.0}))
    with pytest.raises(ValueError, match="origem_efeito"):
        config.carregar(yaml_ems_com_valor(tmp_path, ruim))
    with pytest.raises(FileNotFoundError):
        config.carregar(yaml_ems_com_valor(tmp_path, tmp_path / "nao_existe.json"))
    assert (
        config.carregar(ROOT / "configs" / "premissas_ems.yaml", resolver_valor=False)["valor"].get("origem_efeito")
        is None
    )


def test_ms_tira_idade_e_crescimento_das_saidas_e_leva_o_rotulo(cfg_ms):
    assert "idade_anos" not in cfg_ms["pesos"]["saude"] and "idade_anos" not in cfg_ms["scores"]
    assert abs(sum(cfg_ms["pesos"]["saude"].values()) - 1.0) < 1e-12
    assert "idade_anos" not in S.colunas_indice(cfg_ms) and "crescimento_aa" not in S.colunas_indice(cfg_ms)
    assert "idade_anos" not in S.preditores(cfg_ms)
    assert S.rotulo_valor(cfg_ms) == {
        "origem_efeito": "transportado de MT",
        "rs_por_chi_social": 5.5604,
        "rs_por_chi_compensacao": 2.1484,
    }
    assert qualidade.minimos_validacao(cfg_ms) == (30, 200)


def test_cache_de_outra_distribuidora_e_recusado(tmp_path):
    import pandas as pd

    from sehealth import cache as K

    (tmp_path / "2025").mkdir()
    pd.DataFrame({"COD_ID": ["a", "b"], "DIST": ["405", "405"]}).to_parquet(tmp_path / "2025" / "CTMT.parquet")
    K.verificar_distribuidora(tmp_path, 2025, 405)
    K.verificar_distribuidora(tmp_path, 2025, None)
    with pytest.raises(ValueError, match="404"):
        K.verificar_distribuidora(tmp_path, 2025, 404)
    # DIST inteiro com nulos volta do Parquet como float: 405.0 é a distribuidora 405 (MT não pode abortar por isso)
    arq = tmp_path / "2025" / "CTMT.parquet"
    pd.DataFrame({"COD_ID": ["a", "b", "c"], "DIST": [405.0, None, 405.0]}).to_parquet(arq)
    K.verificar_distribuidora(tmp_path, 2025, 405)
    pd.DataFrame({"COD_ID": ["a", "b"], "DIST": ["405", " 405"]}).to_parquet(arq)
    K.verificar_distribuidora(tmp_path, 2025, 405)
    with pytest.raises(ValueError, match="404"):
        K.verificar_distribuidora(tmp_path, 2025, 404)
