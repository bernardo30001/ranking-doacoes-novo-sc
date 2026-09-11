#!/usr/bin/env python3
"""
Auditoria dos valores coletados do TSE.

Confere se os numeros de receita, origem do dinheiro (Fundo Eleitoral / FEFC,
Fundo Partidario) e despesa de campanha fecham entre si, candidato a candidato.
Roda depois de coletar.py:

    python3 verificar.py
"""

import json
import math
import os
import sys

AQUI = os.environ.get("RANKING_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
TOL = 0.05  # tolerancia em reais para arredondamento


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def main():
    with open(os.path.join(AQUI, "dados.json"), encoding="utf-8") as f:
        d = json.load(f)
    cands = d["candidatos"]
    if not cands or len({c['id'] for c in cands}) != len(cands):
        raise ValueError("Lista vazia ou com candidatos duplicados")
    for c in cands:
        if c['cargo'] not in (6, 7) or d['eleicao']['uf'] != 'SC':
            raise ValueError("Candidato fora do recorte de SC")
        values = [c['total'], c['liquido'], c['devolvido'], c['financeiro'], c['estimado'],
                  *c['origem'].values(), *c['receitas'].values(), *c['despesas'].values()]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError("Valor monetário inválido")
    try:
        with open(os.path.join(AQUI, "agregados.json"), encoding="utf-8") as f:
            agr = json.load(f)
    except (OSError, ValueError):
        agr = {}
    for c in cands:
        a = agr.get(c["id"]) or {}
        c["_doadores"] = a.get("doadores") or []
        c["_categorias"] = a.get("categorias") or {}
        c["_fornecedores"] = a.get("fornecedores") or []
        path = os.path.join(AQUI, "detalhe", c["id"] + ".json")
        with open(path, encoding="utf-8") as f:
            detalhe = json.load(f)
        if detalhe.get("id") != c["id"] or detalhe.get("atualizadoEm") != d["atualizadoEm"]:
            raise ValueError(f"Detalhe de outra coleta: {c['nome']}")
        c["_receitasItens"] = detalhe.get("receitas") or []
        c["_despesasItens"] = detalhe.get("despesas") or []

    checagens = [
        ("fornecedores completos == despesas contratadas",
         lambda c: (sum(x["valor"] for x in c["_fornecedores"]), c["despesas"]["contratadas"])),
        ("arquivo de receitas == total líquido",
         lambda c: (sum(x["valor"] for x in c["_receitasItens"]), c["liquido"])),
        ("arquivo de despesas == despesas contratadas",
         lambda c: (sum(x["valor"] for x in c["_despesasItens"]), c["despesas"]["contratadas"])),
        ("receitas por natureza + devolvidas == total bruto",
         lambda c: (sum(c["receitas"][k] for k in c["receitas"] if k != "devolvidas")
                    + c["receitas"]["devolvidas"], c["total"])),
        ("fundos + outros == recursos financeiros",
         lambda c: (c["origem"]["fundoEspecial"] + c["origem"]["fundoPartidario"]
                    + c["origem"]["outros"], c["financeiro"])),
        ("origem completa == total líquido",
         lambda c: (sum(c["origem"].values()), c["total"] - c["receitas"]["devolvidas"])),
        ("financeiro + RONI + estimavel == total líquido",
         lambda c: (c["financeiro"] + c["receitas"]["roni"] + c["estimado"],
                    c["total"] - c["receitas"]["devolvidas"])),
        ("doacoes itemizadas == total líquido",
         lambda c: (sum(x["valor"] for x in c["_doadores"]),
                    c["total"] - c["receitas"]["devolvidas"])),
        ("despesas por categoria == despesas contratadas",
         lambda c: (sum(c["_categorias"].values()), c["despesas"]["contratadas"])),
    ]

    print(f"Auditoria de {len(cands)} candidatos — {d['eleicao']['uf']} {d['eleicao']['ano']}\n")
    problemas = 0

    for rotulo, calc in checagens:
        divergentes = []
        for c in cands:
            a, b = calc(c)
            if not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > TOL:
                divergentes.append((c, a, b))
        problemas += len(divergentes)
        marca = "ok " if not divergentes else "!! "
        print(f"{marca}{rotulo}: {len(cands) - len(divergentes)}/{len(cands)} batem")
        for c, a, b in sorted(divergentes, key=lambda x: -abs(x[1] - x[2]))[:8]:
            print(f"     {c['nome']} ({c['partido']}): {brl(a)} vs {brl(b)}  dif {brl(a - b)}")
        if len(divergentes) > 8:
            print(f"     ... e mais {len(divergentes) - 8}")

    print()
    regras = [
        ("despesas pagas <= despesas contratadas",
         lambda c: c["despesas"]["pagas"] <= c["despesas"]["contratadas"] + TOL),
        ("fundos publicos <= total arrecadado",
         lambda c: c["origem"]["fundoPartidario"] + c["origem"]["fundoEspecial"] <= c["total"] + TOL),
        ("nenhum valor negativo",
         lambda c: min([c["total"], c["financeiro"], c["estimado"],
                        *c["origem"].values(), *c["receitas"].values(),
                        c["despesas"]["contratadas"], c["despesas"]["pagas"]]) >= 0),
    ]

    for rotulo, ok in regras:
        maus = [c for c in cands if not ok(c)]
        problemas += len(maus)
        marca = "ok " if not maus else "!! "
        print(f"{marca}{rotulo}: {len(cands) - len(maus)}/{len(cands)} passam")
        for c in maus[:8]:
            print(f"     {c['nome']} ({c['partido']}, {c['cargoNome']}): "
                  f"arrecadou {brl(c['total'])}, contratou {brl(c['despesas']['contratadas'])}, "
                  f"pagou {brl(c['despesas']['pagas'])}, limite {brl(c['limiteGasto'])}")
        if len(maus) > 8:
            print(f"     ... e mais {len(maus) - 8}")

    # --- nao e erro, mas merece olhar: contratou mais do que arrecadou ---
    estourados = sorted(
        (c for c in cands if c["despesas"]["contratadas"] > c["total"] + TOL),
        key=lambda c: -(c["despesas"]["contratadas"] - c["total"]))
    print(f"\n.. contrataram mais do que declararam ter arrecadado: {len(estourados)}")
    print("   (diferenças isoladas não demonstram regularidade ou irregularidade)")
    for c in estourados[:10]:
        print(f"     {c['nome']} ({c['partido']}, {c['cargoNome']}): "
              f"arrecadou {brl(c['total'])}, contratou {brl(c['despesas']['contratadas'])}, "
              f"pagou {brl(c['despesas']['pagas'])}")

    # --- panorama do dinheiro publico ---
    roni = sum(c["origem"]["roni"] for c in cands)
    fefc = sum(c["origem"]["fundoEspecial"] for c in cands)
    fp = sum(c["origem"]["fundoPartidario"] for c in cands)
    outros = sum(c["origem"]["outros"] for c in cands)
    estim = sum(c["origem"]["estimavel"] for c in cands)
    total = sum(c["liquido"] for c in cands)
    desp = sum(c["despesas"]["contratadas"] for c in cands)

    print(f"\nTotais de {d['eleicao']['uf']}")
    print(f"  arrecadado líquido   {brl(total)}")
    print(f"    Fundo Eleitoral    {brl(fefc)}  ({fefc / (total or 1) * 100:.1f}%)")
    print(f"    Fundo Partidário   {brl(fp)}  ({fp / (total or 1) * 100:.1f}%)")
    print(f"    outros recursos    {brl(outros)}  ({outros / (total or 1) * 100:.1f}%)")
    print(f"    origem não ident.  {brl(roni)}  ({roni / (total or 1) * 100:.2f}%)")
    print(f"    estimáveis         {brl(estim)}  ({estim / (total or 1) * 100:.2f}%)")
    print(f"  despesas contratadas {brl(desp)}  ({desp / (total or 1) * 100:.1f}% do arrecadado)")
    print(f"  sem prestação de contas: {sum(1 for c in cands if not c['temContas'])}")

    if problemas:
        print(f"\n{problemas} inconsistência(s) — os números do TSE não fecham entre si.")
    else:
        print("\nTodas as checagens de consistência passaram.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
