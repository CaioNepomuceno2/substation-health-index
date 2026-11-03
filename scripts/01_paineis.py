"""Indicadores por SE para cada snapshot com trafos de SE na BDGD (2021-2025).

Cada painel usa só o snapshot do ano e o histórico de interrupções dos 3 anos
até ele (inclusive). Saída: data/processed/painel_<ano>.parquet (e variantes
de fator de carga para a análise de sensibilidade no snapshot de decisão).
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import eventos as E  # noqa: E402
from sehealth import painel as P  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("paineis")
cfg = config.carregar()
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

ev = E.eventos_mt(Path(cfg["dados"]["interim_gridrisk"]) / "interrupcoes_emt.parquet", list(range(2018, 2027)))
ev.to_parquet(OUT / "eventos_mt.parquet", index=False)
for ano in [2021, 2022, 2023, 2024, 2025]:
    df = P.montar(cfg, ano, ev, [ano - 2, ano - 1, ano])
    df.to_parquet(OUT / f"painel_{ano}.parquet", index=False)
    log.info("%s: %d SEs, %d sem folga N-1, %d com carregamento incerto", ano, len(df),
             int(df.sem_folga_n1.sum()), int(df.carregamento_incerto.sum()))

ano = cfg["dados"]["ano_decisao"]
for fc in (0.62, 0.82):
    P.montar(cfg, ano, ev, [ano - 2, ano - 1, ano], fator_carga=fc).to_parquet(
        OUT / f"painel_{ano}_fc{int(fc * 100)}.parquet", index=False)
