"""Diagnósticos dos dados de uma distribuidora (padrão: use ``--config configs/premissas_ems.yaml``).

Só contagens, taxas de vínculo e estabilidade do cadastro: nenhuma nota, risco, capacidade firme nem validação.
Grava em ``<paths.reports>/diagnostico/`` as tabelas citadas por ``docs/decisoes_ems.md``:

* snapshots_se_trafos.csv, tensoes.csv: subestações, trafos e códigos de tensão por snapshot;
* vinculo_alimentador_trafo.csv, vinculo_se_registrada.csv: como o circuito se liga ao trafo e à SE;
* transferencia_na.csv: chaves normalmente abertas entre SEs;
* vinculo_interrupcoes.csv: interrupções de MT ligadas a circuito e SE;
* cobertura_campos.csv, estabilidade_campos.csv: qualidade dos campos do cadastro de trafos;
* duplicatas.csv: count(*) contra count(distinct *) de cada arquivo lido;
* estabilidade_se.csv, escalas_entradas.csv, eventos_disponiveis.csv.

O cache da BDGD (``scripts/00_cache_bdgd.py``) e os intermediários do distribution-asset-risk precisam existir.
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import diagnostico as Dg  # noqa: E402
from sehealth import eventos as E  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("diagnostico")


def main(argv=None):
    ap = config.parser(__doc__)
    ap.add_argument("--zips", default=None, help="pasta com os zips da BDGD (só para contar os snapshots M10)")
    args = ap.parse_args(argv)
    cfg = config.carregar(args.config, resolver_valor=False)
    d, b = cfg["dados"], cfg.get("bdgd", {})
    cache, interim = Path(d["cache_bdgd"]), Path(d["interim_gridrisk"])
    interr = config.arquivo_interrupcoes(cfg)
    out = config.reports(cfg) / "diagnostico"
    out.mkdir(parents=True, exist_ok=True)
    anos = config.anos_paineis(cfg)
    snaps = sorted(int(a) for a in b["snapshots"])
    tens = [str(t) for t in cfg["eletrico"]["tensoes_secundario_mt"]]
    opt_a = config.opcoes_alimentador(cfg)
    val = config.validacao(cfg)

    def grava(nome, df):
        df.to_csv(out / nome, index=False)
        log.info("%s: %d linhas", nome, len(df))

    grava(
        "snapshots_se_trafos.csv",
        Dg.snapshots_se_trafos(
            cache,
            snaps,
            anos,
            tens,
            config.zips_locais(cfg, args.zips),
            b["snapshots"],
            b.get("padrao_zip", "bdgd_{ano}_{item}.gdb.zip"),
        ),
    )
    grava("tensoes.csv", Dg.tensoes(cache, anos))
    grava(
        "vinculo_alimentador_trafo.csv",
        Dg.vinculo_alimentador_trafo(cache, interim, anos, tens, cfg["eletrico"]["cobertura_minima_vinculo"]),
    )
    grava(
        "vinculo_se_registrada.csv",
        Dg.vinculo_se_registrada(
            cache, interim, interr, [a for a in anos if a >= val["ano_disjuntor"] - 3], val["ano_disjuntor"]
        ),
    )
    grava("transferencia_na.csv", Dg.transferencia_na(cache, interim, anos, opt_a))
    grava(
        "vinculo_interrupcoes.csv", Dg.vinculo_interrupcoes(interr, interim, cache, anos, val["ano_disjuntor"], opt_a)
    )
    cobertura, estabilidade = Dg.campos_cadastro(cache, anos, tens)
    grava("cobertura_campos.csv", cobertura)
    grava("estabilidade_campos.csv", estabilidade)
    grava("duplicatas.csv", Dg.duplicatas(cache, interr, anos, ["UNTRAT", "EQTRAT", "SUB", "CTMT", "UNSEMT", "SSDMT"]))
    grava("estabilidade_se.csv", Dg.estabilidade_se(cache, anos))
    ev = E.eventos_mt(interr, config.anos_interrupcoes(cfg))
    grava("escalas_entradas.csv", Dg.escalas(cache, interim, [d["ano_validacao"], d["ano_decisao"]], cfg, ev))
    grava(
        "eventos_disponiveis.csv",
        Dg.eventos_disponiveis(
            cache,
            interim,
            interr,
            cfg,
            d["ano_validacao"],
            d["anos_resultado"],
            val["ano_disjuntor"],
            val["elemento_disjuntor"],
        ),
    )


if __name__ == "__main__":
    main()
