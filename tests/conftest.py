"""Fixtures comuns: isolam os testes das variáveis de ambiente e criam um valor.json de MS sintético."""

import json
import re
from pathlib import Path

import pytest

from sehealth import config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _sem_variaveis_de_ambiente(monkeypatch):
    """Um SEHEALTH_CONFIG ou SEHEALTH_BDGD_ZIPS no ambiente de quem roda não pode mudar o resultado dos testes."""
    monkeypatch.delenv(config.CONFIG_ENV, raising=False)
    monkeypatch.delenv(config.ZIPS_ENV, raising=False)


@pytest.fixture
def valor_json_ms(tmp_path):
    """valor.json de MS no esquema do automation-impact (valores que não são os de MT: 5,943 e 1,926)."""
    p = tmp_path / "valor_ems.json"
    p.write_text(
        json.dumps(
            {
                "origem_efeito": "transportado de MT",
                "rs_por_chi_social": 5.5604,
                "rs_por_chi_compensacao": 2.1484,
                "uc_total": 1458167.0,
            }
        )
    )
    return p


def yaml_ems_com_valor(tmp_path: Path, valor_json: Path, extra: str = "") -> Path:
    """Cópia de configs/premissas_ems.yaml apontando valor.valor_json para ``valor_json`` (o CI não tem os irmãos)."""
    txt = (ROOT / "configs" / "premissas_ems.yaml").read_text(encoding="utf-8")
    txt, n = re.subn(r"valor_json: .*", f"valor_json: {valor_json.as_posix()}", txt)
    assert n == 1
    p = tmp_path / "premissas_ems_teste.yaml"
    p.write_text(txt + extra, encoding="utf-8")
    return p


@pytest.fixture
def cfg_ms(tmp_path, valor_json_ms):
    return config.carregar(yaml_ems_com_valor(tmp_path, valor_json_ms))
