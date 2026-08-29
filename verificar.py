#!/usr/bin/env python3
"""
Auditoria dos valores coletados do TSE.

Confere se os numeros de receita, origem do dinheiro (Fundo Eleitoral / FEFC,
Fundo Partidario) e despesa de campanha fecham entre si, candidato a candidato.
Roda depois de coletar.py:

    python3 verificar.py
"""

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
TOL = 0.05  # tolerancia em reais para arredondamento


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def main():
    with open(os.path.join(AQUI, "dados.json"), encoding="utf-8") as f:
        d = json.load(f)
    cands = d["candidatos"]

    checagens = [
        ("receitas por natureza == total recebido",
         lambda c: (sum(c["receitas"][k] for k in c["receitas"] if k != "devolvidas"), c["total"])),
        ("fundos + outros == recursos financeiros",
         lambda c: (c["origem"]["fundoEspecial"] + c["origem"]["fundoPartidario"]
                    + c["origem"]["outros"], c["financeiro"])),
        ("origem completa == total recebido",
         lambda c: (sum(c["origem"].values()), c["total"])),
        ("financeiro + RONI + estimavel == total recebido",
         lambda c: (c["financeiro"] + c["receitas"]["roni"] + c["estimado"], c["total"])),
    ]

    print(f"Auditoria de {len(cands)} candidatos — {d['eleicao']['uf']} {d['eleicao']['ano']}\n")
    problemas = 0

    for rotulo, calc in checagens:
        divergentes = []
        for c in cands:
            a, b = calc(c)
            if abs(a - b) > TOL:
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
        ("despesas contratadas <= limite legal de gastos",
         lambda c: not c["limiteGasto"] or c["despesas"]["contratadas"] <= c["limiteGasto"] + TOL),
        ("fundos publicos <= total arrecadado",
         lambda c: c["origem"]["fundoPartidario"] + c["origem"]["fundoEspecial"] <= c["total"] + TOL),
        ("ranking de doadores <= total (o TSE publica so os 5 maiores)",
         lambda c: sum(x["valor"] for x in c["doadores"]) <= c["total"] + TOL),
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
    print("   (legal — a despesa pode ser contratada a prazo — mas vale acompanhar)")
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
    total = sum(c["total"] for c in cands)
    desp = sum(c["despesas"]["contratadas"] for c in cands)

    print(f"\nTotais de {d['eleicao']['uf']}")
    print(f"  arrecadado           {brl(total)}")
    print(f"    Fundo Eleitoral    {brl(fefc)}  ({fefc / total * 100:.1f}%)")
    print(f"    Fundo Partidário   {brl(fp)}  ({fp / total * 100:.1f}%)")
    print(f"    outros recursos    {brl(outros)}  ({outros / total * 100:.1f}%)")
    print(f"    origem não ident.  {brl(roni)}  ({roni / total * 100:.2f}%)")
    print(f"    estimáveis         {brl(estim)}  ({estim / total * 100:.2f}%)")
    print(f"  despesas contratadas {brl(desp)}  ({desp / total * 100:.1f}% do arrecadado)")
    print(f"  sem prestação de contas: {sum(1 for c in cands if not c['temContas'])}")

    if problemas:
        print(f"\n{problemas} inconsistência(s) — os números do TSE não fecham entre si.")
    else:
        print("\nTodas as checagens de consistência passaram.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
