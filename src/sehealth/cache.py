"""Cache da BDGD por camada: ``<cache>/<ano>/<CAMADA>.parquet``.

Duas origens, o mesmo formato:

* download do ArcGIS Hub e leitura do .gdb (comportamento de MT, ``scripts/00_cache_bdgd.py``);
* zip já baixado (``bdgd_<ano>_<item>.gdb.zip``), lido no próprio zip pelo GDAL (``/vsizip/``): só as camadas pedidas
  são abertas, nada é extraído nem alterado (comportamento de MS).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

PADRAO_ZIP = "bdgd_{ano}_{item}.gdb.zip"


def achar_zip(pasta: Path, ano: int, item: str, padrao: str = PADRAO_ZIP) -> Path:
    """Zip do cadastro ``ano`` (item do ArcGIS ``item``) numa pasta de zips já baixados."""
    z = Path(pasta) / padrao.format(ano=ano, item=item)
    if not z.is_file():
        raise FileNotFoundError(f"zip da BDGD de {ano} não encontrado: {z}")
    return z


def fonte_do_zip(zip_path: Path) -> str:
    """Caminho virtual do GDAL para ler o .gdb de dentro do zip, sem extrair."""
    return "/vsizip/" + Path(zip_path).resolve().as_posix()


def gravar_camada(fonte: str | Path, camada: str, destino: Path, colunas: list[str] | None = None,
                  geom: bool = False, aliases: dict[str, list[str]] | None = None) -> int | None:
    """Grava ``<destino>/<camada>.parquet`` a partir de ``fonte`` (.gdb ou ``/vsizip/...``).

    Lê só as ``colunas`` que existem na camada (todas, se None). Com ``geom``, a geometria vira lon/lat em WGS84
    (ponto direto; as demais pelo ``representative_point``). Texto vira ``string``. A gravação é atômica (arquivo
    temporário e renomeação): uma queda de energia no meio não deixa um Parquet pela metade.
    Devolve o número de linhas, ou None se a camada não existe (``aliases`` lista nomes alternativos).
    """
    import pyogrio

    nomes = {n for n, _ in pyogrio.list_layers(fonte)}
    real = next((c for c in (aliases or {}).get(camada, [camada]) if c in nomes), None)
    if real is None:
        return None
    campos = list(pyogrio.read_info(fonte, layer=real)["fields"])
    cols = [c for c in (colunas or campos) if c in campos]
    df = pyogrio.read_dataframe(fonte, layer=real, columns=cols, read_geometry=geom, use_arrow=True)
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
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    final, tmp = destino / f"{camada}.parquet", destino / f"{camada}.parquet.tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, final)
    return len(df)


def verificar_distribuidora(cache: Path, ano: int, cod_aneel: int | None) -> None:
    """Recusa um cache de outra distribuidora (coluna ``DIST`` da camada CTMT diferente do código ANEEL esperado)."""
    if cod_aneel is None:
        return
    p = Path(cache) / str(ano) / "CTMT.parquet"
    if not p.exists():
        return
    cols = pd.read_parquet(p).columns
    if "DIST" not in cols:
        return
    dist = pd.read_parquet(p, columns=["DIST"]).DIST.dropna().astype(str).str.strip().unique()
    esperado = str(int(cod_aneel))
    if len(dist) and set(dist) != {esperado}:
        raise ValueError(f"cache {p} é da distribuidora {sorted(dist)}, mas a configuração é a {esperado}")
