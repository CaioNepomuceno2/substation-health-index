"""Configuração por distribuidora.

Cada distribuidora tem um YAML em ``configs/`` (``premissas.yaml`` = Energisa MT, ``premissas_ems.yaml`` = Energisa MS).
A escolha vem, nesta ordem, de:

1. o argumento ``--config`` do script (ou o ``path`` de :func:`carregar`);
2. a variável de ambiente ``SEHEALTH_CONFIG``;
3. ``configs/premissas.yaml`` (padrão: Energisa MT, caminhos e resultados publicados).

Caminhos relativos valem a partir da raiz do repositório; absolutos são respeitados. Chaves ausentes caem no valor de
MT, para que um YAML antigo continue valendo. O que não é de MT nunca grava na raiz de ``reports/`` nem em
``data/processed``: :func:`carregar` recusa a configuração.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

from sehealth import qualidade

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PADRAO = ROOT / "configs" / "premissas.yaml"
CONFIG_ENV = "SEHEALTH_CONFIG"
ZIPS_ENV = "SEHEALTH_BDGD_ZIPS"

# valores de MT, usados quando o YAML não diz outra coisa
SIGLA_MT = "EMT"
NOME_MT = "Energisa Mato Grosso"
NOME_CURTO_MT = "Energisa MT"
PATHS_MT = {"reports": "reports", "processed": "data/processed", "malha_ibge": "ref/mt_ibge.geojson"}
ANOS_PAINEIS_MT = [2021, 2022, 2023, 2024, 2025]
ANOS_INTERRUPCOES_MT = list(range(2018, 2027))
FATORES_CARGA_SENSIBILIDADE_MT = [0.62, 0.82]
VALIDACAO_MT = {"anos_diagnostico_ampliacao": [2021, 2022, 2023], "ano_disjuntor": 2026,
                "elemento_disjuntor": "DISJUNTOR"}


def caminho_config(path: str | Path | None = None) -> Path:
    """Arquivo de configuração: ``path``, senão ``SEHEALTH_CONFIG``, senão ``configs/premissas.yaml``."""
    if path is None:
        path = os.environ.get(CONFIG_ENV, "").strip() or CONFIG_PADRAO
    p = Path(path).expanduser()
    if not p.is_absolute() and not p.exists() and (ROOT / p).exists():
        p = ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"configuração não encontrada: {path}")
    return p


def _abs(p: str | Path) -> str:
    p = Path(p).expanduser()
    return str(p if p.is_absolute() else (ROOT / p).resolve())


def sigla(cfg: dict) -> str:
    return str(cfg["dados"].get("distribuidora", SIGLA_MT))


def nome(cfg: dict) -> str:
    return cfg["dados"].get("nome", NOME_MT)


def nome_curto(cfg: dict) -> str:
    return cfg["dados"].get("nome_curto", NOME_CURTO_MT)


def eh_mt(cfg: dict) -> bool:
    return sigla(cfg) == SIGLA_MT


def arquivo_interrupcoes(cfg: dict) -> Path:
    """``interrupcoes_<sigla em minúsculas>.parquet`` na pasta do projeto irmão (``interrupcoes_emt.parquet`` em MT)."""
    return Path(cfg["dados"]["interim_gridrisk"]) / f"interrupcoes_{sigla(cfg).lower()}.parquet"


def anos_paineis(cfg: dict) -> list[int]:
    """Snapshots com painel por SE (MT: 2021 a 2025, os que têm UNTRAT/EQTRAT)."""
    return [int(a) for a in cfg["dados"].get("anos_paineis", ANOS_PAINEIS_MT)]


def anos_interrupcoes(cfg: dict) -> list[int]:
    return [int(a) for a in cfg["dados"].get("anos_interrupcoes", ANOS_INTERRUPCOES_MT)]


def fatores_carga_sensibilidade(cfg: dict) -> list[float]:
    return [float(f) for f in cfg["eletrico"].get("fator_carga_sensibilidade", FATORES_CARGA_SENSIBILIDADE_MT)]


def validacao(cfg: dict) -> dict:
    """Parâmetros da validação (MT: ampliações vistas dos diagnósticos de 2021 a 2023; disjuntor em 2026)."""
    return {**VALIDACAO_MT, **cfg.get("validacao", {})}


def opcoes_alimentador(cfg: dict) -> dict:
    """Como ligar alimentador a SE e a trafo (``dados.alimentadores``); o padrão é o de MT."""
    el = cfg["eletrico"]
    return {"se_do_alimentador": el.get("se_do_alimentador", "trafo"),
            "vinculo": el.get("vinculo_alimentador", "trafo"),
            "tensoes_mt": [str(t) for t in el["tensoes_secundario_mt"]]}


def opcoes_trafos(cfg: dict) -> dict:
    """Tensões de secundário de MT e capacidade de emergência (``dados.trafos_se``); o padrão é o de MT."""
    el = cfg["eletrico"]
    return {"tensoes_mt": [str(t) for t in el["tensoes_secundario_mt"]],
            "sobrecarga_emergencia": el["sobrecarga_emergencia"],
            "capacidade_emergencia": el.get("capacidade_emergencia", "estagios")}


def reports(cfg: dict) -> Path:
    return Path(cfg["paths"]["reports"])


def processed(cfg: dict) -> Path:
    return Path(cfg["paths"]["processed"])


def figuras(cfg: dict) -> Path:
    return reports(cfg) / "figures"


def malha_ibge(cfg: dict) -> Path:
    return Path(cfg["paths"]["malha_ibge"])


def zips_locais(cfg: dict, argumento: str | Path | None = None) -> Path | None:
    """Pasta com os zips da BDGD já baixados (``bdgd_<ano>_<item>.gdb.zip``), ou None para baixar do ArcGIS.

    Vale, nesta ordem, o argumento ``--zips``, a variável ``SEHEALTH_BDGD_ZIPS`` e ``bdgd.zips_locais`` do YAML.
    Os zips só são lidos, nunca alterados.
    """
    valor = argumento or os.environ.get(ZIPS_ENV, "").strip() or cfg.get("bdgd", {}).get("zips_locais")
    return Path(_abs(valor)) if valor else None


def ler_valor_json(caminho: str | Path) -> dict:
    """R$ por CHI e rótulo de origem do efeito, do ``valor.json`` do automation-impact."""
    p = Path(caminho)
    if not p.is_file():
        raise FileNotFoundError(f"valor.json não encontrado: {p} (clone o automation-impact ao lado deste repositório)")
    v = json.loads(p.read_text(encoding="utf-8"))
    faltam = [k for k in ("rs_por_chi_social", "rs_por_chi_compensacao", "origem_efeito") if k not in v]
    if faltam:
        raise ValueError(f"{p} não tem os campos {faltam}: o rótulo origem_efeito é obrigatório fora de MT")
    return v


def verificar_saidas(cfg: dict) -> None:
    """Outra distribuidora nunca grava onde estão os resultados publicados de MT."""
    if eh_mt(cfg):
        return
    mt = {k: str((ROOT / v).resolve()) for k, v in PATHS_MT.items()}
    for k in ("reports", "processed"):
        if str(Path(cfg["paths"][k]).resolve()) == mt[k]:
            raise ValueError(f"{sigla(cfg)}: paths.{k} aponta para a pasta de MT ({mt[k]}); use uma subpasta 'ems'")


def carregar(path: str | Path | None = None, resolver_valor: bool = True) -> dict:
    """Lê as premissas e resolve os caminhos relativos à raiz do repositório.

    Com ``valor.valor_json`` (obrigatório fora de MT), o R$ por CHI e o rótulo ``origem_efeito`` vêm desse arquivo;
    ``resolver_valor=False`` pula a leitura (testes de estrutura sem o projeto irmão ao lado).
    """
    cfg = yaml.safe_load(caminho_config(path).read_text(encoding="utf-8"))
    d = cfg["dados"]
    for k in ("cache_bdgd", "interim_gridrisk"):
        d[k] = _abs(d[k])
    cfg["paths"] = {k: _abs(cfg.get("paths", {}).get(k, v)) for k, v in PATHS_MT.items()}
    verificar_saidas(cfg)
    qualidade.verificar_pesos(cfg)
    v = cfg.setdefault("valor", {})
    if v.get("valor_json"):
        v["valor_json"] = _abs(v["valor_json"])
    elif not eh_mt(cfg):
        raise ValueError(f"{sigla(cfg)}: defina valor.valor_json; o R$ por CHI de MT não vale para outra distribuidora")
    if v.get("valor_json") and resolver_valor:
        vj = ler_valor_json(v["valor_json"])
        v["rs_por_chi_social"] = float(vj["rs_por_chi_social"])
        v["rs_por_chi_compensacao"] = float(vj["rs_por_chi_compensacao"])
        v["origem_efeito"] = str(vj["origem_efeito"])
    return cfg


def parser(descricao: str) -> argparse.ArgumentParser:
    """Parser dos scripts: já traz ``--config``. Os scripts acrescentam os próprios argumentos."""
    ap = argparse.ArgumentParser(description=descricao, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None,
                    help=f"YAML da distribuidora (padrão: ${CONFIG_ENV} ou configs/premissas.yaml, Energisa MT)")
    return ap


def carregar_args(descricao: str, argv: list[str] | None = None) -> dict:
    """Atalho para scripts sem outros argumentos: lê ``--config`` e devolve a configuração."""
    return carregar(parser(descricao).parse_args(argv).config)
