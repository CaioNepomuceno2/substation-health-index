"""Figuras do README (reports/figures/*.png)."""
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sehealth import config  # noqa: E402

cfg = config.carregar()
ano = cfg["dados"]["ano_decisao"]
R = ROOT / "reports"
FIG = R / "figures"
FIG.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "legend.frameon": False, "legend.labelcolor": INK2,
})


def salvar(fig, nome):
    fig.savefig(FIG / nome, dpi=170, bbox_inches="tight")
    plt.close(fig)


def curto(nome):
    return str(nome).replace("SE ", "").replace(" 138 KV", "").replace(" 69 KV", "").title()


idx = pd.read_csv(R / f"indice_{ano}.csv", dtype={"se": str})
top = idx.nsmallest(10, "rank_risco")

# 1. mapa
fig, ax = plt.subplots(figsize=(7.2, 7.6))
geo = json.loads((ROOT / "ref" / "mt_ibge.geojson").read_text())
for f in geo["features"]:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for p in polys:
        xy = np.array(p[0])
        ax.fill(xy[:, 0], xy[:, 1], color="#f1f0ea", ec=AXIS, lw=0.8, zorder=0)
sc = ax.scatter(idx.lon, idx.lat, s=np.sqrt(idx.n_uc.clip(lower=1)) * 0.9, c=idx.risco, cmap="YlOrRd",
                vmin=0, vmax=max(50, idx.risco.max()), ec=INK2, lw=0.5, zorder=2)
for _, r in top.iterrows():
    ax.annotate(f"{int(r.rank_risco)}. {curto(r.nome)}", (r.lon, r.lat), xytext=(5, 4), textcoords="offset points",
                fontsize=8, color=INK, zorder=3)
cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
cb.set_label("Risco (saúde × criticidade / 100)")
ax.set_title(f"Risco das subestações da Energisa MT ({ano})\ntamanho = consumidores atendidos")
ax.set_xticks([]), ax.set_yticks([]), ax.grid(False)
ax.set_aspect("equal")
salvar(fig, "01_mapa_risco.png")

# 2. matriz
fig, ax = plt.subplots(figsize=(8, 6))
cs, cc = cfg["matriz"]["corte_saude"], cfg["matriz"]["corte_criticidade"]
cores = {"agir: ampliar/substituir": S2, "planejar: condição ruim, baixa consequência": "#e3a21a",
         "monitorar: condição boa, alta consequência": S1, "manter": MUTED}
for q, g in idx.groupby("quadrante"):
    ax.scatter(g.criticidade, g.saude, s=np.sqrt(g.n_uc.clip(lower=1)) * 0.9, color=cores.get(q, MUTED),
               alpha=0.85, ec="white", lw=0.6, label=f"{q} ({len(g)})")
ax.axvline(cc, color=AXIS, ls="--"), ax.axhline(cs, color=AXIS, ls="--")
for i, (_, r) in enumerate(top.head(6).iterrows()):
    ax.annotate(curto(r.nome), (r.criticidade, r.saude), xytext=(5, 6 if i % 2 == 0 else -10),
                textcoords="offset points", fontsize=8, color=INK)
ax.set_xlabel("Criticidade (consequência de perder a SE), 0-100")
ax.set_ylabel("Saúde (pior condição = 100), 0-100")
ax.set_xlim(0, 100), ax.set_ylim(0, 100)
ax.set_title("Matriz de risco: condição × consequência")
ax.legend(loc="upper left", fontsize=8)
salvar(fig, "02_matriz_risco.png")

# 3. N-1
n1 = idx[~idx.carregamento_incerto].sort_values("pico_mva", ascending=False).head(20).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 6.4))
y = np.arange(len(n1))
ax.barh(y, n1.pot_instalada_mva, color=GRID, label="Potência instalada (MVA)")
ax.barh(y, n1.pot_firme_mva, color=S1, height=0.5,
        label="Capacidade firme N-1 (MVA, com ventilação forçada)")
ax.scatter(n1.pico_mva, y, color=S2, zorder=3, label="Pico estimado (MVA)")
ax.set_yticks(y, [f"{curto(n)} ({int(t)} trafo{'s' if t > 1 else ''})" for n, t in zip(n1.nome, n1.n_trafos,
                                                                                         strict=True)], fontsize=8)
ax.set_xlabel("MVA")
ax.set_title("As 20 maiores SEs: o pico cabe se o maior trafo sair?")
ax.legend(loc="lower right", fontsize=8)
salvar(fig, "03_capacidade_n1.png")

# 4. sensibilidade dos pesos
pres = pd.read_csv(R / "sensibilidade_pesos_top10.csv", dtype={"se": str}).set_index("se").iloc[:, 0]
nomes = idx.set_index("se").nome
p = pres.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(7.5, 5.2))
ax.barh([curto(nomes.get(s, s)) for s in p.index], p.values * 100,
        color=[S1 if v >= 0.8 else "#9ec5f4" for v in p.values])
ax.axvline(80, color=S2, ls="--", lw=1)
ax.set_xlabel("% dos 1.000 sorteios de pesos em que a SE fica no top 10")
ax.set_title("Robustez do top 10 à escolha dos pesos")
salvar(fig, "04_sensibilidade_pesos.png")

# 5. validação
amp = pd.read_csv(R / "validacao_ampliacoes.csv")
val = pd.read_csv(R / "validacao_preditiva.csv")
fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
a = amp[amp.criterio == "sem_folga_n1_multi"].pivot(index="ano_base", columns="sinalizada", values="taxa")
x = np.arange(len(a))
axs[0].bar(x - 0.18, a[True] * 100, 0.36, color=S2, label="Sinalizadas: sem folga N-1 (2+ trafos)")
axs[0].bar(x + 0.18, a[False] * 100, 0.36, color=GRID, label="Demais SEs com 2+ trafos")
axs[0].set_xticks(x, [f"diagnóstico {i}" for i in a.index])
axs[0].set_ylabel("% ampliadas até 2025")
axs[0].set_title("O critério N-1 acompanha decisões reais")
axs[0].set_ylim(0, 60)
axs[0].legend(fontsize=8, loc="upper right")
rot = {"risco": "Índice\nde risco", "chi_eventos_se_ano": "Eventos de SE\nanteriores",
       "n_uc": "Só o porte\n(UCs)", "saude_cadastral": "Saúde\n(só cadastro)", "idade_anos": "Idade"}
v = val[val.resultado.isin(["chi_eventos_se_ano_depois", "disjuntor_2026_chi"]) & val.preditor.isin(rot)]
pv = v.pivot(index="preditor", columns="resultado", values="spearman").loc[list(rot)]
x = np.arange(len(pv))
axs[1].bar(x - 0.18, pv["chi_eventos_se_ano_depois"], 0.36, color=S1, label="CHI de eventos de SE 2024-25")
axs[1].bar(x + 0.18, pv["disjuntor_2026_chi"], 0.36, color=S3, label="CHI aberto por disjuntor 2026")
axs[1].set_xticks(x, [rot[i] for i in pv.index], fontsize=8)
axs[1].axhline(0, color=AXIS)
axs[1].set_ylabel("Correlação de Spearman")
axs[1].set_title("Índice de 2023 contra o que aconteceu depois")
axs[1].set_ylim(-0.1, 0.65)
axs[1].legend(fontsize=8, loc="upper right")
salvar(fig, "05_validacao.png")
print(sorted(p.name for p in FIG.glob("*.png")))
