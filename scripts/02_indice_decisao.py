"""Índice de saúde × criticidade no snapshot de decisão, sensibilidade e lista priorizada."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sehealth import config  # noqa: E402
from sehealth import indice as I  # noqa: E402
from sehealth import valor as V  # noqa: E402

cfg = config.carregar()
ano = cfg["dados"]["ano_decisao"]
P = ROOT / "data" / "processed"
R = ROOT / "reports"
R.mkdir(exist_ok=True)

df = pd.read_parquet(P / f"painel_{ano}.parquet").set_index("se")
idx = V.priorizar(I.calcular(df, cfg), cfg)
idx["breakeven_horas_reposicao"] = cfg["valor"]["horas_reposicao"] / idx.beneficio_custo_ampliacao
idx = idx.sort_values("risco", ascending=False)
idx["rank_risco"] = np.arange(1, len(idx) + 1)

cols = ["rank_risco", "nome", "quadrante", "risco", "saude", "criticidade", "fatores_saude",
        "n_trafos", "pot_instalada_mva", "pico_mva", "utilizacao_pico", "pot_firme_mva", "folga_n1_mva",
        "deficit_n1", "sem_folga_n1", "carregamento_incerto", "cobertura_vinculo", "fluxo_reverso",
        "meses_fluxo_reverso", "idade_anos", "perdas_z", "crescimento_aa", "n_alimentadores", "n_uc",
        "energia_gwh", "frac_uc_sem_transferencia", "frac_municipio", "eventos_se_ano",
        "chi_eventos_se_ano", "chi_alimentadores_ano", "ens_n1_mwh_ano", "rs_eventos_se_social",
        "rs_eventos_se_compensacao", "rs_ens_n1", "rs_risco_ano", "mva_ampliacao", "capex_ampliacao_rs",
        "capex_anualizado_rs", "beneficio_custo_ampliacao", "breakeven_horas_reposicao", "lon", "lat"]
idx[cols].round(4).to_csv(R / f"indice_{ano}.csv")

# --- sensibilidade: pesos (Dirichlet) e fator de carga
sens = I.sensibilidade_pesos(df, cfg, n=1000)
fc = {}
for v in (62, 82):
    alt = I.calcular(pd.read_parquet(P / f"painel_{ano}_fc{v}.parquet").set_index("se"), cfg)
    j = idx[["risco"]].join(alt[["risco"]].rename(columns={"risco": "risco_alt"}), how="inner")
    fc[f"fc_0.{v}"] = {
        "spearman_risco": float(j.risco.corr(j.risco_alt, method="spearman")),
        "top10_em_comum": int(len(set(j.risco.nlargest(10).index) & set(j.risco_alt.nlargest(10).index))),
        "ses_sem_folga_n1": int(alt.sem_folga_n1.sum()),
        "ses_sem_folga_n1_com_2mais_trafos": int((alt.sem_folga_n1 & alt.n_trafos.ge(2)).sum()),
    }

pontuado = idx[~idx.carregamento_incerto]
multi = pontuado[pontuado.n_trafos >= 2]
uc_tot = idx.n_uc.sum()
q = idx.groupby("quadrante").agg(n_ses=("risco", "size"), n_uc=("n_uc", "sum"), rs_risco=("rs_risco_ano", "sum"))
resumo = {
    "ano": ano,
    "n_ses": int(len(idx)),
    "n_uc": float(uc_tot),
    "ses_carregamento_incerto": int(idx.carregamento_incerto.sum()),
    "ses_um_trafo": int((idx.n_trafos == 1).sum()),
    "uc_em_ses_um_trafo": float(idx.loc[idx.n_trafos == 1, "n_uc"].sum()),
    "ses_sem_folga_n1_pontuadas": int(pontuado.sem_folga_n1.sum()),
    "ses_sem_folga_n1_com_2mais_trafos": int(multi.sem_folga_n1.sum()),
    "ses_utilizacao_acima_80pct": int((pontuado.utilizacao_pico > 0.8).sum()),
    "ses_utilizacao_acima_100pct": int((pontuado.utilizacao_pico > 1.0).sum()),
    "ses_fluxo_reverso_anual": int(idx.fluxo_reverso.sum()),
    "ses_com_meses_fluxo_reverso": int((idx.meses_fluxo_reverso > 0).sum()),
    "uc_sem_transferencia": float((idx.frac_uc_sem_transferencia * idx.n_uc).sum()),
    "frac_uc_sem_transferencia": float((idx.frac_uc_sem_transferencia * idx.n_uc).sum() / uc_tot),
    "quadrantes": q.round(0).to_dict("index"),
    "top10_risco": idx.head(10)[["nome", "quadrante", "risco", "fatores_saude", "n_uc"]].round(1)
    .reset_index().to_dict("records"),
    "top10_frac_rs_risco": float(idx.head(10).rs_risco_ano.sum() / idx.rs_risco_ano.sum()),
    "top10_frac_uc": float(idx.head(10).n_uc.sum() / uc_tot),
    "rs_risco_total_ano": float(idx.rs_risco_ano.sum()),
    "rs_eventos_se_social_total": float(idx.rs_eventos_se_social.sum()),
    "rs_ens_n1_total": float(idx.rs_ens_n1.sum()),
    "ampliacoes_candidatas": int((idx.mva_ampliacao > 0).sum()),
    "mva_ampliacao_total": float(idx.mva_ampliacao.sum()),
    "capex_ampliacao_total_rs": float(idx.capex_ampliacao_rs.sum()),
    "ampliacoes_bc_maior_1": int((idx.beneficio_custo_ampliacao > 1).sum()),
    "breakeven_horas_mediana": float(idx.breakeven_horas_reposicao.median()),
    "breakeven_horas_p10": float(idx.breakeven_horas_reposicao.quantile(0.1)),
    "eventos_se_ano_total": float(idx.eventos_se_ano.sum()),
    "chi_eventos_se_ano_total": float(idx.chi_eventos_se_ano.sum()),
    "frac_chi_mt_em_eventos_se": float(idx.chi_eventos_se_ano.sum() / idx.chi_alimentadores_ano.sum()),
    "ses_top10_risco_um_trafo": int((idx.head(10).n_trafos == 1).sum()),
    "sensibilidade_pesos": {k: v for k, v in sens.items() if k != "presenca_top_k"},
    "sensibilidade_fator_carga": fc,
}
sens["presenca_top_k"].rename("frac_sorteios_no_top10").to_csv(R / "sensibilidade_pesos_top10.csv")
(R / f"resumo_{ano}.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=float))
print(json.dumps({k: v for k, v in resumo.items() if k not in ("top10_risco", "quadrantes")}, indent=1, default=float))
print(idx[cols[:12]].head(15).round(2).to_string())
