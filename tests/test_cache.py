"""Cache da BDGD a partir de zips locais (MS) e a gravação de camadas de MT, que não pode mudar."""

import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from sehealth import cache as K
from sehealth import config

pyogrio = pytest.importorskip("pyogrio")
gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, Polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _gdb_sintetico(pasta: Path) -> Path:
    """File Geodatabase com UNTRAT (pontos) e SUB (polígonos), como as camadas da BDGD."""
    untrat = gpd.GeoDataFrame(
        {"COD_ID": ["a", "b"], "SUB": ["10", "20"], "POT_NOM": [25.0, 30.0], "DESCR": [None, "x"]},
        geometry=[Point(-54.5, -20.5), Point(-54.6, -20.6)],
        crs=4674,
    )
    sub = gpd.GeoDataFrame(
        {"COD_ID": ["10"], "NOME": ["ALFA"]},
        crs=4674,
        geometry=[Polygon([(-54.0, -20.0), (-54.2, -20.0), (-54.2, -20.2), (-54.0, -20.2)])],
    )
    gdb = pasta / "x.gdb"
    pyogrio.write_dataframe(untrat, gdb, layer="UNTRAT", driver="OpenFileGDB")
    pyogrio.write_dataframe(sub, gdb, layer="SUB", driver="OpenFileGDB", append=True)
    return gdb


def _zip_do_gdb(gdb: Path, destino: Path) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in gdb.rglob("*"):
            zf.write(p, p.relative_to(gdb.parent).as_posix())
    return destino


def _grava_antigo(gdb, camada, out: Path, colunas=None, geom=False):
    """A função de gravação do scripts/00_cache_bdgd.py de MT antes da mudança (copiada do histórico do git)."""
    aliases = {"UNTRMT": ["UNTRMT", "UNTRD"]}
    nomes = {n for n, _ in pyogrio.list_layers(gdb)}
    real = next((c for c in aliases.get(camada, [camada]) if c in nomes), None)
    if real is None:
        return None
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
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / f"{camada}.parquet", index=False)
    return len(df)


def test_gravacao_de_camada_e_identica_a_de_mt(tmp_path):
    gdb = _gdb_sintetico(tmp_path)
    for camada, cols, geom in [
        ("UNTRAT", None, True),
        ("SUB", None, True),
        ("UNTRAT", ["COD_ID", "SUB", "NAO_EXISTE"], False),
    ]:
        a = _grava_antigo(gdb, camada, tmp_path / "antigo", cols, geom)
        b = K.gravar_camada(
            gdb, camada, tmp_path / "novo", colunas=cols, geom=geom, aliases={"UNTRMT": ["UNTRMT", "UNTRD"]}
        )
        assert a == b
        pd.testing.assert_frame_equal(
            pd.read_parquet(tmp_path / "antigo" / f"{camada}.parquet"),
            pd.read_parquet(tmp_path / "novo" / f"{camada}.parquet"),
        )
    assert _grava_antigo(gdb, "NAO_EXISTE", tmp_path / "antigo") is None
    assert K.gravar_camada(gdb, "NAO_EXISTE", tmp_path / "novo") is None
    assert not list((tmp_path / "novo").glob("*.tmp"))  # gravação atômica: nada pela metade


def test_gravar_camada_poe_lon_lat_e_texto_como_string(tmp_path):
    gdb = _gdb_sintetico(tmp_path)
    K.gravar_camada(gdb, "UNTRAT", tmp_path / "o", geom=True)
    K.gravar_camada(gdb, "SUB", tmp_path / "o", geom=True)
    u, s = pd.read_parquet(tmp_path / "o" / "UNTRAT.parquet"), pd.read_parquet(tmp_path / "o" / "SUB.parquet")
    assert u.lon.round(2).tolist() == [-54.5, -54.6] and "geometry" not in u
    assert u.SUB.tolist() == ["10", "20"] and s.lon.iloc[0] == pytest.approx(-54.1)  # ponto representativo do polígono


def test_zip_local_e_lido_sem_extrair_nem_alterar(tmp_path):
    z = _zip_do_gdb(_gdb_sintetico(tmp_path), tmp_path / "bdgd_2025_abc.gdb.zip")
    antes = hashlib.sha256(z.read_bytes()).hexdigest()
    assert K.achar_zip(tmp_path, 2025, "abc") == z
    with pytest.raises(FileNotFoundError):
        K.achar_zip(tmp_path, 2024, "abc")
    assert K.fonte_do_zip(z).startswith("/vsizip/")
    assert K.gravar_camada(K.fonte_do_zip(z), "UNTRAT", tmp_path / "cache" / "2025", geom=True) == 2
    assert hashlib.sha256(z.read_bytes()).hexdigest() == antes
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_dir()) == ["cache", "x.gdb"]  # nada foi extraído


def test_script_00_le_zips_locais_so_das_camadas_pedidas(tmp_path, valor_json_ms, capsys):
    import yaml

    z = _zip_do_gdb(_gdb_sintetico(tmp_path), tmp_path / "bdgd_2025_abc.gdb.zip")
    cfg = yaml.safe_load((ROOT / "configs" / "premissas_ems.yaml").read_text(encoding="utf-8"))
    cfg["valor"]["valor_json"] = valor_json_ms.as_posix()
    cfg["bdgd"].update(snapshots={2025: "abc"}, anos_cache=[2025], camadas=["UNTRAT", "SUB"], com_geometria=["UNTRAT"])
    cfg["bdgd"]["topologia"] = {"anos": [], "camadas": {}, "ucs": False}
    p = tmp_path / "ems.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("script_00", ROOT / "scripts" / "00_cache_bdgd.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    saida = tmp_path / "cache_ems"
    antes = hashlib.sha256(z.read_bytes()).hexdigest()
    mod.main(["--config", str(p), "--zips", str(tmp_path), str(saida)])
    assert (saida / "2025" / "UNTRAT.parquet").exists() and (saida / "2025" / "SUB.parquet").exists()
    assert (
        not (saida / "2025" / "CTMT.parquet").exists()
        and (saida / "2025" / "_ok").exists()
        and (saida / "DONE").exists()
    )
    assert set(pd.read_parquet(saida / "2025" / "UNTRAT.parquet").columns) >= {"lon", "lat"}
    assert hashlib.sha256(z.read_bytes()).hexdigest() == antes
    capsys.readouterr()
    mod.main(["--config", str(p), "--zips", str(tmp_path), str(saida)])  # retomável: o ano pronto é pulado
    assert "já em cache" in capsys.readouterr().out
    assert config.zips_locais({"bdgd": {}}, tmp_path) == tmp_path
