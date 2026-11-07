"""Dados sintéticos no formato da BDGD e das interrupções de MS, para os testes (sem rede e sem arquivos baixados).

O que tem de MS: nome de circuito alfanumérico de 5 caracteres (``AJO51``, canônico ``0AJO51``), circuito cujo
``UNI_TR_AT`` aponta para um trafo de outra SE, estágios de ventilação 1,25x e 1,5x em todos os trafos, uma SE com
código em branco, 2 de 3 circuitos de 34,5 kV numa SE que só tem trafo de 13,8 kV, interrupções de 2026 com o código
numérico da SE e o elemento ``DISJUNTOR``.
"""

import json
from pathlib import Path

import pandas as pd
import yaml

from sehealth.carregamento import horas_mes

ROOT = Path(__file__).resolve().parents[1]
ANOS = [2021, 2022, 2023, 2024, 2025]
FP, FC = 0.92, 0.72
PERFIL = [1.0] + [0.8] * 11
# código da SE: (nome, potências nominais dos trafos, pico mensal em MVA, município, prefixo dos circuitos,
#                nº de circuitos, UC por circuito, tensão do circuito, lon)
SES = {
    "10": ("SE ALFA", [30, 30], 40.0, "5000001", "AJO", 3, 20000, "49", -54.6),
    "20": ("SE BETA", [25], 12.0, "5000002", "BET", 2, 5000, "49", -54.5),
    "30": ("SE GAMA", [15, 15, 15], 24.0, "5000002", "GAM", 3, 8000, "49", -54.4),
    "40": (
        "SE DELTA",
        [20],
        10.0,
        "5000003",
        "DEL",
        3,
        3000,
        "72",
        -54.3,
    ),  # só 1 de 3 circuitos é de 13,8 kV, como o trafo
}
SEM_CODIGO = " "


def _energia(pico_mva, mes, ano, n_circ):
    return pico_mva * FC * FP * PERFIL[mes - 1] * horas_mes(ano)[mes - 1] * 1000 / n_circ


def gravar_snapshot(cache: Path, interim: Path, ano: int, dist: str = "404") -> dict:
    """Camadas da BDGD (Parquet) e a base de circuitos do snapshot. Devolve {nome do circuito: COD_ID}."""
    pasta = Path(cache) / str(ano)
    pasta.mkdir(parents=True, exist_ok=True)
    sub, untrat, eqtrat, ctmt, feeders, ssdmt = [], [], [], [], [], []
    cod_ids = {}
    ses = dict(SES)
    if ano == 2025:  # a SE GAMA ganha um trafo: ampliação entre os snapshots
        ses["30"] = (*SES["30"][:1], [15, 15, 15, 15], *SES["30"][2:])
    for i, (se, (nome, pots, pico, mun, pref, n_circ, n_uc, ten, lon)) in enumerate(ses.items()):
        sub.append({"COD_ID": se, "NOME": nome, "lon": lon, "lat": -20.0})
        for j, p in enumerate(pots):
            untrat.append(
                {
                    "COD_ID": f"{se}{j}",
                    "SUB": se,
                    "MUN": mun,
                    "POT_NOM": float(p),
                    "POT_F01": p * 1.25,
                    "POT_F02": p * 1.5,
                    "PER_FER": 0.04 + 0.01 * i + 0.002 * j,
                    "PER_TOT": 0.5,
                    "DAT_CON": f"01/06/{1990 + 5 * i}",
                    "lon": lon,
                    "lat": -20.0,
                }
            )
            eqtrat.append(
                {"UNI_TR_AT": f"{se}{j}", "TEN_PRI": "94", "TEN_SEC": "49", "DAT_IMO": f"01/06/{1990 + 5 * i}"}
            )
        for k in range(n_circ):
            nome_c = f"{pref}{51 + k}"
            cod = f"{se}_C{k}"
            cod_ids[nome_c] = cod
            # o 2º circuito da SE BETA aponta para um trafo da SE ALFA (a SE do trafo difere de CTMT.SUB)
            trafo = "100" if (se == "20" and k == 1) else f"{se}{k % len(pots)}"
            ten_c = "49" if (se == "40" and k == 0) else ten
            ctmt.append(
                {
                    "COD_ID": cod,
                    "NOME": nome_c,
                    "SUB": se,
                    "UNI_TR_AT": trafo,
                    "TEN_NOM": ten_c,
                    "DIST": dist,
                    **{f"ENE_{m:02d}": _energia(pico, m, ano, n_circ) for m in range(1, 13)},
                }
            )
            feeders.append({"alimentador_cod_id": cod, "n_uc": float(n_uc), "rede_mt_km": 100.0, "frac_rural": 0.5})
            ssdmt.append({"PAC_1": f"{cod}_p1", "PAC_2": f"{cod}_p2", "CTMT": cod})
    # SE sem código (SUB em branco): um trafo e um circuito que não identificam subestação nenhuma
    untrat.append(
        {
            "COD_ID": "B0",
            "SUB": SEM_CODIGO,
            "MUN": "5000009",
            "POT_NOM": 20.0,
            "POT_F01": 25.0,
            "POT_F02": 30.0,
            "PER_FER": 0.05,
            "PER_TOT": 0.5,
            "DAT_CON": "01/06/2000",
            "lon": -54.0,
            "lat": -20.0,
        }
    )
    eqtrat.append({"UNI_TR_AT": "B0", "TEN_PRI": "94", "TEN_SEC": "49", "DAT_IMO": "01/06/2000"})
    ctmt.append(
        {
            "COD_ID": "B_C0",
            "NOME": "XXX01",
            "SUB": SEM_CODIGO,
            "UNI_TR_AT": "B0",
            "TEN_NOM": "49",
            "DIST": dist,
            **{f"ENE_{m:02d}": _energia(8.0, m, ano, 1) for m in range(1, 13)},
        }
    )
    cod_ids["XXX01"] = "B_C0"
    feeders.append({"alimentador_cod_id": "B_C0", "n_uc": 2000.0, "rede_mt_km": 50.0, "frac_rural": 0.5})
    ssdmt.append({"PAC_1": "B_C0_p1", "PAC_2": "B_C0_p2", "CTMT": "B_C0"})
    # chave normalmente aberta entre AJO51 (SE ALFA) e BET51 (SE BETA): rota de transferência entre SEs
    unsemt = [
        {"COD_ID": "k1", "PAC_1": "10_C0_p2", "PAC_2": "20_C0_p2", "P_N_OPE": "A"},
        {"COD_ID": "k2", "PAC_1": "30_C0_p2", "PAC_2": "30_C1_p2", "P_N_OPE": "A"},
    ]  # mesma SE: não é rota
    for nome, linhas in [
        ("SUB", sub),
        ("UNTRAT", untrat),
        ("EQTRAT", eqtrat),
        ("CTMT", ctmt),
        ("SSDMT", ssdmt),
        ("UNSEMT", unsemt),
    ]:
        pd.DataFrame(linhas).to_parquet(pasta / f"{nome}.parquet", index=False)
    Path(interim).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(feeders).to_parquet(Path(interim) / f"bdgd_feeders_{ano}.parquet", index=False)
    # crosswalk: código operacional completado a 6 caracteres e COD_ID do circuito -> circuito canônico
    cw = [{"codigo": c, "alimentador": n.zfill(6)} for n, c in cod_ids.items()]
    cw += [{"codigo": n.zfill(6), "alimentador": n.zfill(6)} for n in cod_ids]
    pd.DataFrame(cw).to_parquet(Path(interim) / f"crosswalk_{ano}.parquet", index=False)
    return cod_ids


def gravar_interrupcoes(interim: Path, cod_ids: dict, nome_arquivo: str = "interrupcoes_ems.parquet"):
    """Interrupções 2021-2026: eventos de SE (3 circuitos no mesmo minuto) nas SEs ALFA e GAMA, aberturas por disjuntor
    de 2026 na SE ALFA e interrupções que não devem entrar (programada; 2 circuitos só)."""
    base = {
        "alimentador_nome": None,
        "alimentador_cod_id": None,
        "uc_afetadas": 1000,
        "duracao_h": 1.0,
        "elemento": "CHAVE FUSIVEL",
        "origem_mt": True,
        "origem": "INTERNA",
        "tipo": "NAO PROGRAMADA",
    }
    linhas = []
    for ano in range(2021, 2027):
        t = pd.Timestamp(f"{ano}-03-10 14:05:20")
        for se, pref, circs in [("10", "AJO", (51, 52, 53)), ("30", "GAM", (51, 52, 53))]:
            if se == "30" and ano < 2024:
                continue
            for c in circs:
                nome = f"{pref}{c}"
                linhas.append(
                    {
                        **base,
                        "subestacao": se if ano == 2026 else pref,
                        "inicio": t,
                        "chi": 500.0,
                        "ano": ano,
                        "alimentador_nome": None if ano == 2026 else nome.zfill(6),
                        "alimentador_cod_id": cod_ids[nome] if ano == 2026 else None,
                        "elemento": "DISJUNTOR" if (ano == 2026 and se == "10") else "CHAVE FUSIVEL",
                    }
                )
        linhas.append(
            {
                **base,
                "subestacao": "20" if ano == 2026 else "BET",
                "inicio": t,
                "chi": 1e6,
                "ano": ano,
                "alimentador_nome": None if ano == 2026 else "BET51".zfill(6),
                "alimentador_cod_id": cod_ids["BET51"] if ano == 2026 else None,
                "tipo": "PROGRAMADA",
            }
        )
        for c in (51, 52):  # só 2 circuitos da SE BETA: não é evento de SE
            linhas.append(
                {
                    **base,
                    "subestacao": "20" if ano == 2026 else "BET",
                    "inicio": t,
                    "chi": 100.0,
                    "ano": ano,
                    "alimentador_nome": None if ano == 2026 else f"BET{c}".zfill(6),
                    "alimentador_cod_id": cod_ids[f"BET{c}"] if ano == 2026 else None,
                }
            )
    pd.DataFrame(linhas).to_parquet(Path(interim) / nome_arquivo, index=False)


def config_de_teste(
    tmp: Path,
    valor_json: Path,
    validacao: dict | None = None,
    portas_ampliacao: dict | None = None,
    sobre: dict | None = None,
) -> Path:
    """Cópia de premissas_ems.yaml com os caminhos em ``tmp`` e o valor.json sintético; devolve o caminho do YAML."""
    cfg = yaml.safe_load((ROOT / "configs" / "premissas_ems.yaml").read_text(encoding="utf-8"))
    cfg["dados"]["cache_bdgd"] = str(tmp / "cache")
    cfg["dados"]["interim_gridrisk"] = str(tmp / "interim")
    cfg["paths"].update(reports=str(tmp / "reports" / "ems"), processed=str(tmp / "processed" / "ems"))
    cfg["valor"]["valor_json"] = valor_json.as_posix()
    cfg["dados"]["anos_interrupcoes"] = list(range(2021, 2027))
    if validacao is not None:
        cfg["qualidade"]["validacao"] = validacao
    if portas_ampliacao is not None:
        cfg["validacao"]["portas_ampliacao"] = portas_ampliacao
    for caminho, valor in (sobre or {}).items():
        d = cfg
        *chaves, ultima = caminho.split(".")
        for k in chaves:
            d = d[k]
        d[ultima] = valor
    p = Path(tmp) / "premissas_ems_teste.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return p


def montar_dados(tmp: Path) -> None:
    """Cache, intermediários e interrupções sintéticos em ``tmp/cache`` e ``tmp/interim``."""
    cod = {}
    for ano in ANOS:
        cod = gravar_snapshot(tmp / "cache", tmp / "interim", ano)
    gravar_interrupcoes(tmp / "interim", cod)
    (tmp / "valor_ems.json").write_text(
        json.dumps(
            {"origem_efeito": "transportado de MT", "rs_por_chi_social": 5.5604, "rs_por_chi_compensacao": 2.1484}
        )
    )
