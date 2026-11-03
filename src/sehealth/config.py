from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def carregar(path: str | Path = ROOT / "configs" / "premissas.yaml") -> dict:
    """Lê as premissas e resolve os caminhos de dados relativos à raiz do repositório."""
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for k in ("cache_bdgd", "interim_gridrisk"):
        p = Path(cfg["dados"][k])
        cfg["dados"][k] = str(p if p.is_absolute() else (ROOT / p).resolve())
    return cfg
