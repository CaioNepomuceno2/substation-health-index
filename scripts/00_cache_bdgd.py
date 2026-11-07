"""Cache da BDGD: grava as camadas usadas em Parquet (<ano>/<CAMADA>.parquet, ponto/polígono como lon/lat, EPSG:4326).

Duas origens, escolhidas pela configuração (``--config``; padrão = Energisa MT):

* **MT (padrão):** baixa cada snapshot da ANEEL, uma vez, grava as camadas e apaga o GDB. Reaproveita o leitor da BDGD
  do projeto irmão distribution-asset-risk (https://github.com/CaioNepomuceno2/distribution-asset-risk, pacote
  ``gridrisk``), que precisa estar clonado ao lado deste repositório. Camadas de topologia (SSDMT, UNTRMT, UCBT/UCMT
  agregados) só para os anos em TOPO.
* **Zips locais (MS):** com ``--zips <pasta>``, ``SEHEALTH_BDGD_ZIPS`` ou ``bdgd.zips_locais``, lê os zips já baixados
  (``bdgd_<ano>_<item>.gdb.zip``) no próprio zip, pelo GDAL (``/vsizip/``), só nas camadas de ``bdgd.camadas``. Nada é
  baixado, extraído nem alterado na pasta de zips. O inventário é somado ao que já existe, então o script é retomável.

Camadas, anos e colunas de topologia vêm de ``bdgd.*`` da configuração; sem a chave, valem os padrões de MT abaixo.
No fim grava DONE com o inventário.
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyogrio
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import cache as K  # noqa: E402
from sehealth import config  # noqa: E402

# padrões de MT
ATIVOS = ["UNSEMT", "EQSE", "UNTRAT", "EQTRAT", "SUB", "BAY", "CTMT", "UNREMT", "EQRE", "BAR", "CONJ"]
COM_GEOM = {"UNSEMT", "SUB", "UNTRAT", "UNREMT"}
TOPO = {2024, 2025}
TOPO_CAMADAS = {"SSDMT": ["COD_ID", "PAC_1", "PAC_2", "CTMT", "COMP", "FAS_CON", "TIP_CND", "SUB", "CONJ"],
                "UNTRMT": None}
INVENT = {}


def _grava(fonte, camada: str, ano: int, out: Path, colunas=None, geom=False, aliases=None):
    n = K.gravar_camada(fonte, camada, out / str(ano), colunas=colunas, geom=geom, aliases=aliases)
    INVENT.setdefault(ano, {})[camada] = "ausente" if n is None else n


def _ucs(gdb: Path, ano: int, out: Path):
    """Consumidores por trafo MT (BT) e por PAC (MT), para a topologia."""
    nomes = {n for n, _ in pyogrio.list_layers(gdb)}
    for lay, chave in [("UCBT_tab", "UNI_TR_MT"), ("UCMT_tab", "PAC")]:
        if lay not in nomes:
            continue
        campos = list(pyogrio.read_info(gdb, layer=lay)["fields"])
        cols = [c for c in [chave, "CTMT", "CAR_INST"] + [f"ENE_{m:02d}" for m in range(1, 13)] if c in campos]
        df = pyogrio.read_dataframe(gdb, layer=lay, columns=cols, read_geometry=False, use_arrow=True)
        ene = [c for c in df.columns if c.startswith("ENE_")]
        df["ene_ano_kwh"] = df[ene].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        agg = df.groupby([chave, "CTMT"], dropna=False).agg(n_uc=("ene_ano_kwh", "size"),
                                                             ene_ano_kwh=("ene_ano_kwh", "sum")).reset_index()
        for c in [chave, "CTMT"]:
            agg[c] = agg[c].astype("string")
        agg.to_parquet(out / str(ano) / f"{lay}_agg.parquet", index=False)
        INVENT.setdefault(ano, {})[f"{lay}_agg"] = len(agg)


def main(argv=None):
    ap = config.parser(__doc__)
    ap.add_argument("saida", nargs="?", default=None, help="pasta do cache (padrão: dados.cache_bdgd da configuração)")
    ap.add_argument("--zips", default=None, help="pasta com os zips da BDGD já baixados (somente leitura)")
    args = ap.parse_args(argv)
    cfg = config.carregar(args.config, resolver_valor=False)
    b = cfg.get("bdgd", {})
    out = Path(args.saida) if args.saida else Path(cfg["dados"]["cache_bdgd"])
    zips = config.zips_locais(cfg, args.zips)
    ativos = list(b.get("camadas", ATIVOS))
    com_geom = set(b.get("com_geometria", COM_GEOM))
    topo_cfg = b.get("topologia", {})
    topo = set(topo_cfg.get("anos", TOPO))
    topo_camadas = topo_cfg.get("camadas", TOPO_CAMADAS)
    com_ucs = topo_cfg.get("ucs", True)

    if zips is None:
        gridrisk = ROOT.parent / "distribution-asset-risk"
        sys.path.insert(0, str(gridrisk / "src"))
        from gridrisk.ingest import bdgd  # noqa: E402
        snaps = b.get("snapshots") or yaml.safe_load(open(gridrisk / "configs" / "emt.yaml"))["bdgd"]["snapshots"]
        aliases = bdgd.LAYER_ALIASES
        raw = out / "_raw"
    else:
        snaps = b["snapshots"]
        aliases = None
    anos = sorted((int(a) for a in snaps), reverse=zips is None)
    if zips is not None and b.get("anos_cache"):
        anos = [a for a in anos if a in set(b["anos_cache"])]

    for ano in anos:
        if (out / str(ano) / "_ok").exists():
            print(ano, "já em cache", flush=True)
            continue
        if zips is not None:
            fonte = K.fonte_do_zip(K.achar_zip(zips, ano, str(snaps[ano] if ano in snaps else snaps[str(ano)]),
                                               b.get("padrao_zip", K.PADRAO_ZIP)))
            print(ano, "lendo", fonte.rsplit("/", 1)[-1], flush=True)
            apaga = None
        else:
            gridrisk_raw = list((gridrisk / "data" / "raw" / "bdgd" / str(ano)).glob("*.gdb"))
            fonte = gridrisk_raw[0] if gridrisk_raw else bdgd.download(snaps[ano], raw / str(ano))
            print(ano, "lendo", fonte.name, flush=True)
            apaga = None if gridrisk_raw else raw / str(ano)
        for camada in ativos:
            _grava(fonte, camada, ano, out, geom=camada in com_geom, aliases=aliases)
        if ano in topo:
            for camada, cols in topo_camadas.items():
                _grava(fonte, camada, ano, out, colunas=cols, geom=(camada == "UNTRMT"), aliases=aliases)
            if com_ucs and zips is None:
                _ucs(fonte, ano, out)
        (out / str(ano) / "_ok").write_text("ok")
        if apaga is not None:
            shutil.rmtree(apaga, ignore_errors=True)
        print(ano, INVENT.get(ano), flush=True)

    inv = INVENT
    if zips is not None and (out / "inventario.json").exists():
        antigo = json.loads((out / "inventario.json").read_text())
        inv = {**antigo, **{str(k): v for k, v in INVENT.items()}}
    (out / "inventario.json").write_text(json.dumps(inv, indent=1, default=str))
    (out / "DONE").write_text("ok")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
