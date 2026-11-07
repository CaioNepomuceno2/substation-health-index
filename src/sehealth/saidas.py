"""O que cada distribuidora publica: colunas, preditores, nomes de arquivo e o rótulo de origem do valor.

Os padrões são os de MT (as listas literais abaixo são as que os scripts publicam hoje). Outra distribuidora tira daí o
que o cadastro dela não sustenta (idade do trafo, crescimento de energia) e acrescenta o rótulo ``origem_efeito``.
"""
from __future__ import annotations

import pandas as pd

COLUNAS_INDICE_MT = [
    "rank_risco", "nome", "quadrante", "risco", "saude", "criticidade", "fatores_saude",
    "n_trafos", "pot_instalada_mva", "pico_mva", "utilizacao_pico", "pot_firme_mva", "folga_n1_mva",
    "deficit_n1", "sem_folga_n1", "carregamento_incerto", "cobertura_vinculo", "fluxo_reverso",
    "meses_fluxo_reverso", "idade_anos", "perdas_z", "crescimento_aa", "n_alimentadores", "n_uc",
    "energia_gwh", "frac_uc_sem_transferencia", "frac_municipio", "eventos_se_ano",
    "chi_eventos_se_ano", "chi_alimentadores_ano", "ens_n1_mwh_ano", "rs_eventos_se_social",
    "rs_eventos_se_compensacao", "rs_ens_n1", "rs_risco_ano", "mva_ampliacao", "capex_ampliacao_rs",
    "capex_anualizado_rs", "beneficio_custo_ampliacao", "breakeven_horas_reposicao", "lon", "lat"]

PREDITORES_MT = ["risco", "saude", "risco_cadastral", "saude_cadastral", "chi_eventos_se_ano", "eventos_se_por_100k_uc",
                 "n_uc", "idade_anos"]

# resultados da validação, por porta: (A) eventos de SE no período de resultado; (B) aberturas por disjuntor no ano novo
RESULTADOS_A = ["chi_eventos_se_ano_depois", "eventos_se_ano_depois", "eventos_se_por_100k_uc_depois",
                "chi_eventos_se_por_uc_depois"]
RESULTADOS_B = ["disjuntor_2026_n", "disjuntor_2026_chi"]
# colunas de validacao_por_se.csv que pertencem a cada resultado (na ordem em que MT as publica)
COLUNAS_POR_SE_A = ["chi_alimentadores_ano_depois", "eventos_se_ano_depois", "chi_eventos_se_ano_depois"]
COLUNAS_POR_SE_B = ["disjuntor_2026_n", "disjuntor_2026_chi"]


def sem_idade(cfg: dict) -> bool:
    """A idade do trafo não pode ser publicada nem usada como baseline (porta (a))."""
    return not cfg.get("qualidade", {}).get("idade_trafo_confiavel", True)


def sem_crescimento(cfg: dict) -> bool:
    """O crescimento de energia entre cadastros não é publicado (``docs/decisoes_ems.md``, seção 5.1)."""
    return not cfg.get("qualidade", {}).get("crescimento_energia_confiavel", True)


def colunas_indice(cfg: dict) -> list[str]:
    cols = list(COLUNAS_INDICE_MT)
    if sem_idade(cfg):
        cols.remove("idade_anos")
    if sem_crescimento(cfg):
        cols.remove("crescimento_aa")
    if cfg.get("qualidade", {}).get("rank_entre_carregamento_confiavel", False):
        cols.insert(cols.index("rank_risco") + 1, "rank_risco_carregamento_confiavel")
    return cols


def preditores(cfg: dict) -> list[str]:
    return [p for p in PREDITORES_MT if not (p == "idade_anos" and sem_idade(cfg))]


def rotulo_valor(cfg: dict) -> dict:
    """Rótulo que toda saída de R$ repete: origem do efeito do religador e o R$ por CHI efetivamente usado.

    Vazio em MT (que não tem ``origem_efeito``), então os arquivos de MT não mudam.
    """
    v = cfg.get("valor", {})
    if "origem_efeito" not in v:
        return {}
    return {"origem_efeito": v["origem_efeito"], "rs_por_chi_social": v["rs_por_chi_social"],
            "rs_por_chi_compensacao": v["rs_por_chi_compensacao"]}


def anexar_rotulo(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Acrescenta ao CSV com R$ as colunas do rótulo (nada em MT)."""
    out = df.copy()
    for k, valor in rotulo_valor(cfg).items():
        out[k] = valor
    return out


def chave_fc(fc: float) -> str:
    return f"fc_{fc:.2f}"


def nome_painel_fc(ano: int, fc: float) -> str:
    """``painel_2025_fc62.parquet``: o mesmo nome na gravação (01) e na leitura (02)."""
    return f"painel_{ano}_fc{round(fc * 100)}.parquet"


def nome_painel_sens(ano: int, nome: str) -> str:
    return f"painel_{ano}_sens_{nome}.parquet"


def variante(cfg: dict, overrides: dict) -> dict:
    """Cópia da configuração com ``eletrico`` alterado (sensibilidades declaradas de antemão)."""
    import copy

    c = copy.deepcopy(cfg)
    c["eletrico"].update(overrides)
    return c
