"""Indicadores por SE para cada snapshot com trafos de SE na BDGD (MT: 2021-2025).

Cada painel usa só o snapshot do ano e o histórico de interrupções dos 3 anos
até ele (inclusive). Saída: <paths.processed>/painel_<ano>.parquet (e variantes
de fator de carga para a análise de sensibilidade no snapshot de decisão e, se a
configuração declara ``sensibilidades``, uma variante por sensibilidade).

Escolha a distribuidora com ``--config`` ou ``SEHEALTH_CONFIG`` (padrão: Energisa MT).
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import eventos as E  # noqa: E402
from sehealth import painel as P  # noqa: E402
from sehealth import saidas as S  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("paineis")


def main(argv=None):
    cfg = config.carregar_args(__doc__, argv)
    out = config.processed(cfg)
    out.mkdir(parents=True, exist_ok=True)

    ev = E.eventos_mt(config.arquivo_interrupcoes(cfg), config.anos_interrupcoes(cfg))
    ev.to_parquet(out / "eventos_mt.parquet", index=False)
    for ano in config.anos_paineis(cfg):
        df = P.montar(cfg, ano, ev, [ano - 2, ano - 1, ano])
        df.to_parquet(out / f"painel_{ano}.parquet", index=False)
        log.info("%s: %d SEs, %d sem folga N-1, %d com carregamento incerto", ano, len(df),
                 int(df.sem_folga_n1.sum()), int(df.carregamento_incerto.sum()))

    ano = cfg["dados"]["ano_decisao"]
    for fc in config.fatores_carga_sensibilidade(cfg):
        P.montar(cfg, ano, ev, [ano - 2, ano - 1, ano], fator_carga=fc).to_parquet(
            out / S.nome_painel_fc(ano, fc), index=False)
    for nome, overrides in cfg.get("sensibilidades", {}).items():
        P.montar(S.variante(cfg, overrides), ano, ev, [ano - 2, ano - 1, ano]).to_parquet(
            out / S.nome_painel_sens(ano, nome), index=False)
        log.info("sensibilidade %s: %s", nome, overrides)


if __name__ == "__main__":
    main()
