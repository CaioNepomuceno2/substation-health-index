"""Diagnósticos dos dados de uma distribuidora (padrão: use ``--config configs/premissas_ems.yaml``).

Só contagens, taxas de vínculo e estabilidade do cadastro: nenhuma nota, risco, capacidade firme nem validação.
Grava em ``<paths.reports>/diagnostico/`` as tabelas citadas por ``docs/decisoes_ems.md``:

* snapshots_se_trafos.csv, tensoes.csv: subestações, trafos e códigos de tensão por snapshot;
* vinculo_alimentador_trafo.csv, vinculo_se_registrada.csv: como o circuito se liga ao trafo e à SE;
* transferencia_na.csv: chaves normalmente abertas entre SEs;
* vinculo_interrupcoes.csv: interrupções de MT ligadas a circuito e SE;
* cobertura_campos.csv, estabilidade_campos.csv: qualidade dos campos do cadastro de trafos;
* duplicatas.csv: count(*) contra count(distinct *) de cada arquivo lido;
* energia_circuitos.csv, energia_estabilidade.csv: qualidade da energia mensal dos circuitos (base do carregamento);
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
    ap.add_argument("--so", default=None, help="só estas tabelas (nomes sem .csv, separados por vírgula)")
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

    quero = set(args.so.split(",")) if args.so else None
    zips = config.zips_locais(cfg, args.zips)
    padrao_zip = b.get("padrao_zip", "bdgd_{ano}_{item}.gdb.zip")
    camadas = ["UNTRAT", "EQTRAT", "SUB", "CTMT", "UNSEMT", "SSDMT"]
    cache_campos = {}

    def campos():
        if "campos" not in cache_campos:
            cache_campos["campos"] = Dg.campos_cadastro(cache, anos, tens)
        return cache_campos["campos"]

    tabelas = {
        "snapshots_se_trafos": lambda: Dg.snapshots_se_trafos(
            cache, snaps, anos, tens, zips, b["snapshots"], padrao_zip
        ),
        "tensoes": lambda: Dg.tensoes(cache, anos),
        "vinculo_alimentador_trafo": lambda: Dg.vinculo_alimentador_trafo(
            cache, interim, anos, tens, cfg["eletrico"]["cobertura_minima_vinculo"]
        ),
        "vinculo_se_registrada": lambda: Dg.vinculo_se_registrada(
            cache, interim, interr, [a for a in anos if a >= val["ano_disjuntor"] - 3], val["ano_disjuntor"]
        ),
        "transferencia_na": lambda: Dg.transferencia_na(cache, interim, anos, opt_a),
        "vinculo_interrupcoes": lambda: Dg.vinculo_interrupcoes(
            interr, interim, cache, anos, val["ano_disjuntor"], opt_a
        ),
        "cobertura_campos": lambda: campos()[0],
        "estabilidade_campos": lambda: campos()[1],
        "duplicatas": lambda: Dg.duplicatas(cache, interr, anos, camadas),
        "energia_circuitos": lambda: Dg.energia_circuitos(cache, interim, anos, opt_a)[0],
        "energia_estabilidade": lambda: Dg.energia_circuitos(cache, interim, anos, opt_a)[1],
        "estabilidade_se": lambda: Dg.estabilidade_se(cache, anos),
        "escalas_entradas": lambda: Dg.escalas(
            cache,
            interim,
            [d["ano_validacao"], d["ano_decisao"]],
            cfg,
            E.eventos_mt(interr, config.anos_interrupcoes(cfg)),
        ),
        "eventos_disponiveis": lambda: Dg.eventos_disponiveis(
            cache,
            interim,
            interr,
            cfg,
            d["ano_validacao"],
            d["anos_resultado"],
            val["ano_disjuntor"],
            val["elemento_disjuntor"],
        ),
    }
    for nome, fn in tabelas.items():
        if quero is None or nome in quero:
            df = fn()
            df.to_csv(out / f"{nome}.csv", index=False)
            log.info("%s.csv: %d linhas", nome, len(df))


if __name__ == "__main__":
    main()
