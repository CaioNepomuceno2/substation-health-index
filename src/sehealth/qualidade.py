"""Portas de qualidade pré-registradas (``docs/decisoes_ems.md``, seção 2).

Escritas e commitadas antes de qualquer resultado de MS. Duas portas decidem o que pode ser publicado:

* **(a) Idade:** a nota de saúde só entra no índice se não depender de idade de equipamento inferida do cadastro.
  Em MS, a data de conexão do mesmo trafo muda de um cadastro para o outro, então ``idade_anos`` não pode ter peso.
* **(b) Validação com eventos:** a afirmação "o índice antecipa os eventos de SE" só é publicada para um resultado
  (eventos de SE, aberturas por disjuntor) se pelo menos ``min_ses_com_evento`` SEs do índice tiveram pelo menos um
  evento na janela de validação e houve pelo menos ``min_eventos`` eventos no total. Senão o índice sai sem a afirmação.

Mais um critério de estabilidade entre cadastros, usado para escolher quais campos do cadastro entram nos
indicadores (:func:`estabilidade`).
"""
from __future__ import annotations

import pandas as pd

# critérios pré-registrados (iguais para todo campo do cadastro)
MAX_FRAC_MUDOU = 0.10      # no máximo 10% dos equipamentos com o valor trocado entre dois cadastros seguidos
MIN_COBERTURA = 0.90       # pelo menos 90% dos trafos com valor válido


def estabilidade(antes: pd.DataFrame, depois: pd.DataFrame, chave: str, campo: str, casas: int | None = None) -> dict:
    """Fração dos equipamentos presentes nos dois cadastros (mesma ``chave``) cujo ``campo`` mudou de valor.

    Um equipamento não troca de data de conexão nem de perda no ferro de um ano para o outro: valor trocado é
    mudança de cadastro, não de equipamento. ``casas`` arredonda antes de comparar (campos numéricos).
    """
    a = antes.drop_duplicates(chave).set_index(chave)[campo]
    b = depois.drop_duplicates(chave).set_index(chave)[campo]
    comuns = a.index.intersection(b.index)
    va, vb = a.loc[comuns], b.loc[comuns]
    if casas is not None:
        va, vb = pd.to_numeric(va, errors="coerce").round(casas), pd.to_numeric(vb, errors="coerce").round(casas)
    mudou = ~((va == vb) | (va.isna() & vb.isna()))
    n = int(len(comuns))
    return {"n_antes": int(len(a)), "n_comuns": n, "n_mudou": int(mudou.sum()),
            "frac_mudou": float(mudou.mean()) if n else float("nan")}


def passa_estabilidade(frac_mudou: float) -> bool:
    return bool(frac_mudou <= MAX_FRAC_MUDOU)


def verificar_pesos(cfg: dict) -> None:
    """Porta (a): recusa a configuração em que a nota de saúde depende de idade de equipamento não confiável."""
    q = cfg.get("qualidade", {})
    if q.get("idade_trafo_confiavel", True):
        return
    peso = float(cfg.get("pesos", {}).get("saude", {}).get("idade_anos", 0) or 0)
    if peso > 0:
        raise ValueError("a idade do trafo está marcada como não confiável (qualidade.idade_trafo_confiavel: false); "
                         "retire idade_anos de pesos.saude")


def porta_validacao(n_ses_com_evento: int, n_eventos: int, min_ses: int, min_eventos: int) -> dict:
    """Porta (b): a validação contra um resultado só é publicada com SEs e eventos suficientes."""
    ok_ses, ok_ev = n_ses_com_evento >= min_ses, n_eventos >= min_eventos
    motivos = []
    if not ok_ses:
        motivos.append(f"só {n_ses_com_evento} SEs do índice com pelo menos 1 evento (mínimo {min_ses})")
    if not ok_ev:
        motivos.append(f"só {n_eventos} eventos no total (mínimo {min_eventos})")
    return {"passou": bool(ok_ses and ok_ev), "ses_com_evento": int(n_ses_com_evento), "eventos": int(n_eventos),
            "min_ses_com_evento": int(min_ses), "min_eventos": int(min_eventos), "motivo": "; ".join(motivos)}


def minimos_validacao(cfg: dict) -> tuple[int, int] | None:
    """(SEs, eventos) mínimos da porta (b) na configuração, ou None se a configuração não tem a porta (MT)."""
    v = cfg.get("qualidade", {}).get("validacao")
    if not v:
        return None
    return int(v["min_ses_com_evento"]), int(v["min_eventos"])
