"""Validação: índice montado com dados até 2023 contra o que aconteceu em 2024-2026.

Resultados medidos depois do corte (nunca entram no índice):
* eventos de SE (interrupções simultâneas em >= N alimentadores da SE) em 2024-2025;
* interrupções abertas por DISJUNTOR em 2026 (campo novo do layout da ANEEL, jan-jul).
E a checagem de decisões reais: SEs sem folga N-1 em 2022/2023 foram ampliadas até 2025?
"""
import copy
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import dados as D  # noqa: E402
from sehealth import eventos as E  # noqa: E402
from sehealth import indice as I  # noqa: E402
from sehealth import painel as P  # noqa: E402
from sehealth import validacao as Va  # noqa: E402

cfg = config.carregar()
d = cfg["dados"]
t0, anos_res = d["ano_validacao"], d["anos_resultado"]
PR, R = ROOT / "data" / "processed", ROOT / "reports"

base = pd.read_parquet(PR / f"painel_{t0}.parquet").set_index("se")
idx = I.calcular(base, cfg)
cfg_cad = copy.deepcopy(cfg)
cfg_cad["pesos"]["saude"].pop("eventos_se_por_100k_uc")
idx["saude_cadastral"] = I.calcular(base, cfg_cad).saude
idx["risco_cadastral"] = idx.saude_cadastral * idx.criticidade / 100

# --- resultados depois do corte, ligados com o snapshot mais recente (medição, não feature)
ev = pd.read_parquet(PR / "eventos_mt.parquet")
alim_res = D.alimentadores(Path(d["cache_bdgd"]), Path(d["interim_gridrisk"]), max(anos_res))
evv = E.vincular(ev[ev.ano.isin(anos_res)], P.crosswalk(Path(d["interim_gridrisk"]), max(anos_res)), alim_res)
ev_se = E.eventos_se(evv, cfg["eventos"]["min_alimentadores_evento_se"])
res = E.resumo_por_se(evv, ev_se, anos_res).add_suffix("_depois")

dj = ev[(ev.ano == 2026) & (ev.elemento == "DISJUNTOR")]
res = res.join(dj.groupby("cod_subestacao").agg(disjuntor_2026_n=("chi", "size"), disjuntor_2026_chi=("chi", "sum")),
               how="outer")
v = idx.join(res, how="left")
cols_res = [c for c in res.columns]
v[cols_res] = v[cols_res].fillna(0)
v["eventos_se_por_100k_uc_depois"] = v.eventos_se_ano_depois / v.n_uc * 1e5
v["chi_eventos_se_por_uc_depois"] = v.chi_eventos_se_ano_depois / v.n_uc

preditores = ["risco", "saude", "risco_cadastral", "saude_cadastral", "chi_eventos_se_ano", "eventos_se_por_100k_uc",
              "n_uc", "idade_anos"]
resultados = ["chi_eventos_se_ano_depois", "eventos_se_ano_depois", "eventos_se_por_100k_uc_depois",
              "chi_eventos_se_por_uc_depois", "disjuntor_2026_n", "disjuntor_2026_chi"]
tab = Va.comparar(v, preditores, resultados)
tab.round(4).to_csv(R / "validacao_preditiva.csv", index=False)
cols_por_se = ["se", "nome", "risco", "saude", "criticidade", "saude_cadastral", "chi_eventos_se_ano"] + cols_res
v.reset_index()[cols_por_se].round(3).to_csv(R / "validacao_por_se.csv", index=False)

# --- decisões reais: ampliações depois do diagnóstico
depois = pd.read_parquet(PR / "painel_2025.parquet")
amp = []
for ano in (2021, 2022, 2023):
    b = pd.read_parquet(PR / f"painel_{ano}.parquet")
    b = b[~b.carregamento_incerto].copy()
    b["sem_folga_n1_multi"] = b.sem_folga_n1 & (b.n_trafos >= 2)
    b["utilizacao_acima_80"] = b.utilizacao_pico > 0.8
    for flag in ("sem_folga_n1", "sem_folga_n1_multi", "utilizacao_acima_80"):
        t = Va.taxa_ampliacao(b, depois, flag).assign(ano_base=ano, criterio=flag)
        amp.append(t)
amp = pd.concat(amp, ignore_index=True)
amp.to_csv(R / "validacao_ampliacoes.csv", index=False)

cobertura = {
    "ses_no_indice_2023": int(len(idx)),
    "ses_com_resultado": int(v.chi_eventos_se_ano_depois.notna().sum()),
    "eventos_se_2024_2025": int(len(ev_se)),
    "chi_eventos_se_2024_2025": float(ev_se.chi.sum()),
    "disjuntor_2026_eventos_total": int(len(dj)),
    "disjuntor_2026_eventos_em_ses_do_indice": int(v.disjuntor_2026_n.sum()),
}
(R / "validacao_resumo.json").write_text(json.dumps(cobertura, indent=2, default=float))
pd.set_option("display.width", 220)
print(json.dumps(cobertura, indent=1))
print(tab.round(3).to_string())
print(amp.round(3).to_string())
