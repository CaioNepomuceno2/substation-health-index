"""Cache da BDGD (Energisa MT, 2018-2025): baixa cada snapshot da ANEEL e grava as camadas usadas.

Reaproveita o leitor da BDGD do projeto irmão distribution-asset-risk
(https://github.com/CaioNepomuceno2/distribution-asset-risk, pacote ``gridrisk``),
que precisa estar clonado ao lado deste repositório (caminho em GRIDRISK abaixo).

Para cada snapshot: baixa o GDB uma vez, grava as camadas necessárias em Parquet
(<ano>/<CAMADA>.parquet, geometria pontual como lon/lat em EPSG:4326) e apaga o GDB.
Camadas de topologia (SSDMT, UNTRMT, UCBT/UCMT agregados) só para os anos em TOPO.
No fim grava DONE com o inventário.
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyogrio
import yaml

GRIDRISK = Path(__file__).resolve().parents[2] / "distribution-asset-risk"
sys.path.insert(0, str(GRIDRISK / "src"))
from gridrisk.ingest import bdgd  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "bdgd-cache"
RAW = OUT / "_raw"
SNAPS = yaml.safe_load(open(GRIDRISK / "configs" / "emt.yaml"))["bdgd"]["snapshots"]
ATIVOS = ["UNSEMT", "EQSE", "UNTRAT", "EQTRAT", "SUB", "BAY", "CTMT", "UNREMT", "EQRE", "BAR", "CONJ"]
COM_GEOM = {"UNSEMT", "SUB", "UNTRAT", "UNREMT"}
TOPO = {2024, 2025}
TOPO_CAMADAS = {"SSDMT": ["COD_ID", "PAC_1", "PAC_2", "CTMT", "COMP", "FAS_CON", "TIP_CND", "SUB", "CONJ"],
                "UNTRMT": None}
INVENT = {}


def _grava(gdb: Path, camada: str, ano: int, colunas=None, geom=False):
    nomes = {n for n, _ in pyogrio.list_layers(gdb)}
    real = next((c for c in bdgd.LAYER_ALIASES.get(camada, [camada]) if c in nomes), None)
    if real is None:
        INVENT.setdefault(ano, {})[camada] = "ausente"
        return
    campos = list(pyogrio.read_info(gdb, layer=real)["fields"])
    cols = [c for c in (colunas or campos) if c in campos]
    df = pyogrio.read_dataframe(gdb, layer=real, columns=cols, read_geometry=geom, use_arrow=True)
    if geom and "geometry" in df:
        g = df.geometry.to_crs(4326)
        if g.geom_type.isin(["Point"]).all():
            df["lon"], df["lat"] = g.x, g.y
        else:
            c = g.representative_point()
            df["lon"], df["lat"] = c.x, c.y
        df = pd.DataFrame(df.drop(columns="geometry"))
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype("string")
    (OUT / str(ano)).mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / str(ano) / f"{camada}.parquet", index=False)
    INVENT.setdefault(ano, {})[camada] = len(df)


def _ucs(gdb: Path, ano: int):
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
        agg.to_parquet(OUT / str(ano) / f"{lay}_agg.parquet", index=False)
        INVENT.setdefault(ano, {})[f"{lay}_agg"] = len(agg)


for ano in sorted(SNAPS, reverse=True):
    ano = int(ano)
    if (OUT / str(ano) / "_ok").exists():
        print(ano, "já em cache", flush=True)
        continue
    destino = RAW / str(ano)
    gdb_existente = list((GRIDRISK / "data" / "raw" / "bdgd" / str(ano)).glob("*.gdb"))
    gdb = gdb_existente[0] if gdb_existente else bdgd.download(SNAPS[ano], destino)
    print(ano, "lendo", gdb.name, flush=True)
    for camada in ATIVOS:
        _grava(gdb, camada, ano, geom=camada in COM_GEOM)
    if ano in TOPO:
        for camada, cols in TOPO_CAMADAS.items():
            _grava(gdb, camada, ano, colunas=cols, geom=(camada == "UNTRMT"))
        _ucs(gdb, ano)
    (OUT / str(ano) / "_ok").write_text("ok")
    if not gdb_existente:
        shutil.rmtree(destino, ignore_errors=True)
    print(ano, INVENT.get(ano), flush=True)

(OUT / "inventario.json").write_text(json.dumps(INVENT, indent=1, default=str))
(OUT / "DONE").write_text("ok")
print("DONE", flush=True)
