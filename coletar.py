#!/usr/bin/env python3
"""
Coletor de dados de financiamento de campanha - DivulgaCandContas / TSE.

Baixa todos os candidatos do PARTIDO NOVO em Santa Catarina para
Deputado Federal (cargo 6) e Deputado Estadual (cargo 7), junto com a
prestacao de contas de cada um, e grava tudo em dados.json.

O TSE fica atras de um WAF (Akamai) que bloqueia clientes HTTP comuns,
entao usamos curl_cffi para imitar o handshake TLS do Chrome.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from curl_cffi import requests

BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"
ID_ELEICAO = "20322002026"   # Eleicao Geral Federal 2026
ANO = "2026"
UF = "SC"
PARTIDO = 30                 # NOVO
CARGOS = {6: "Deputado Federal", 7: "Deputado Estadual"}

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "dados.json")
HISTORICO = os.path.join(AQUI, "historico.json")
FUSO = timezone(timedelta(hours=-3))  # horario de Brasilia

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://divulgacandcontas.tse.jus.br/divulga/",
}


def get(url, tentativas=4):
    """GET com retry e backoff. Devolve o JSON ou None."""
    for i in range(tentativas):
        try:
            r = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.json()
            print(f"  ! HTTP {r.status_code} em {url}", file=sys.stderr)
        except Exception as e:
            print(f"  ! {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(1.5 * (i + 1))
    return None


def listar_candidatos(cargo):
    """Lista os candidatos do NOVO para um cargo."""
    url = f"{BASE}/candidatura/listar/{ANO}/{UF}/{ID_ELEICAO}/{cargo}/candidatos"
    j = get(url)
    if not j:
        raise RuntimeError(f"nao consegui listar candidatos do cargo {cargo}")
    todos = j.get("candidatos") or []
    return [c for c in todos if (c.get("partido") or {}).get("sigla") == "NOVO"]


def num(v):
    """Normaliza valores monetarios (None -> 0.0)."""
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def coletar_um(item):
    cargo, base = item
    id_cand = base["id"]
    numero = base["numero"]

    detalhe = get(f"{BASE}/candidatura/buscar/{ANO}/{UF}/{ID_ELEICAO}/candidato/{id_cand}") or {}
    contas = get(f"{BASE}/prestador/consulta/{ID_ELEICAO}/{ANO}/{UF}/{cargo}/{PARTIDO}/{numero}/{id_cand}")

    d = (contas or {}).get("dadosConsolidados") or {}
    desp = (contas or {}).get("despesas") or {}

    doadores = []
    for x in (contas or {}).get("rankingDoadores") or []:
        doadores.append({
            "cpfCnpj": x.get("cpfCnpj"),
            "nome": x.get("nome"),
            "qtd": int(x.get("qntd") or 0),
            "valor": num(x.get("valor")),
            "fcc": bool(x.get("stFinanciamentoColetivo")),
        })
    doadores.sort(key=lambda x: -x["valor"])

    fornecedores = []
    for x in (contas or {}).get("rankingFornecedores") or []:
        fornecedores.append({
            "cpfCnpj": x.get("cpfCnpj"),
            "nome": x.get("nome"),
            "qtd": int(x.get("qntd") or 0),
            "valor": num(x.get("valor")),
        })
    fornecedores.sort(key=lambda x: -x["valor"])

    entregas = [{
        "data": e.get("dataEntrega"),
        "tipo": e.get("tipo"),
        "retificadora": e.get("retificadora") == "SIM",
    } for e in (contas or {}).get("historicoEntregas") or []]

    return {
        "id": str(id_cand),
        "nome": base.get("nomeUrna"),
        "nomeCompleto": detalhe.get("nomeCompleto") or base.get("nomeCompleto"),
        "numero": numero,
        "cargo": cargo,
        "cargoNome": CARGOS[cargo],
        "cpf": detalhe.get("cpf"),
        "ocupacao": detalhe.get("ocupacao"),
        "municipio": detalhe.get("nomeMunicipioNascimento"),
        "situacao": base.get("descricaoSituacao"),
        "totalizacao": base.get("descricaoTotalizacao"),
        "foto": detalhe.get("fotoUrl") if detalhe.get("fotoUrlPublicavel") else None,
        "sites": detalhe.get("sites") or [],
        "cnpjCampanha": detalhe.get("cnpjcampanha"),
        "limiteGasto": num(detalhe.get("gastoCampanha1T")),
        "totalBens": num(detalhe.get("totalDeBens")),
        "urlTse": (
            "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/"
            f"SUL/{UF}/{ID_ELEICAO}/{id_cand}/{ANO}/{UF}"
        ),
        "temContas": contas is not None,
        "contasAtualizadas": (contas or {}).get("dataUltimaAtualizacaoContas"),

        # Total e composicao por natureza da receita
        "total": num(d.get("totalRecebido")),
        "qtdDoacoes": int(d.get("qtdRecebido") or 0),
        "financeiro": num(d.get("totalFinanceiro")),
        "estimado": num(d.get("totalEstimados")),
        "receitas": {
            "pessoaFisica": num(d.get("totalReceitaPF")),
            "pessoaJuridica": num(d.get("totalReceitaPJ")),
            "internet": num(d.get("totalInternet")),
            "outrosCandidatos": num(d.get("totalReceitaOutCand")),
            "partidos": num(d.get("totalPartidos")),
            "roni": num(d.get("totalRoni")),
            "proprios": num(d.get("totalProprios")),
            "financiamentoColetivo": num(d.get("totalDoacaoFcc")),
            "comercializacao": num(d.get("totalReceitaComercializacao")),
            "aplicacoes": num(d.get("totalDoacaoAplicacaoFinanceira")),
            "bens": num(d.get("totalDoacaoBensMoveisImoveis")),
            "devolvidas": num(d.get("totalDoacaoDevolvida")),
        },
        # Origem do dinheiro: publico (fundos) x privado (outros)
        "origem": {
            "fundoPartidario": num(d.get("graphVrReceitaFinFundo")),
            "fundoEspecial": num(d.get("graphVrReceitaFinFefc")),
            "outros": num(d.get("graphVrReceitaFinOutros")),
        },
        "despesas": {
            "contratadas": num(desp.get("totalDespesasContratadas")),
            "pagas": num(desp.get("totalDespesasPagas")),
        },
        "doadores": doadores,
        "fornecedores": fornecedores,
        "entregas": entregas,
    }


def main():
    agora = datetime.now(FUSO)
    print(f"[{agora:%d/%m/%Y %H:%M:%S}] coletando NOVO/SC...")

    alvos = []
    for cargo in CARGOS:
        lista = listar_candidatos(cargo)
        print(f"  {CARGOS[cargo]}: {len(lista)} candidatos do NOVO")
        alvos += [(cargo, c) for c in lista]

    with ThreadPoolExecutor(max_workers=6) as pool:
        candidatos = list(pool.map(coletar_um, alvos))

    candidatos.sort(key=lambda c: -c["total"])
    for i, c in enumerate(candidatos, 1):
        c["posicao"] = i

    fundo_total = sum(c["origem"]["fundoPartidario"] + c["origem"]["fundoEspecial"] for c in candidatos)
    total_geral = sum(c["total"] for c in candidatos)

    saida = {
        "atualizadoEm": agora.isoformat(),
        "eleicao": {"id": ID_ELEICAO, "ano": int(ANO), "uf": UF, "partido": "NOVO"},
        "resumo": {
            "candidatos": len(candidatos),
            "comArrecadacao": sum(1 for c in candidatos if c["total"] > 0),
            "totalArrecadado": round(total_geral, 2),
            "totalFundos": round(fundo_total, 2),
            "totalPrivado": round(sum(c["origem"]["outros"] for c in candidatos), 2),
            "totalDespesas": round(sum(c["despesas"]["contratadas"] for c in candidatos), 2),
            "porCargo": {
                CARGOS[k]: round(sum(c["total"] for c in candidatos if c["cargo"] == k), 2)
                for k in CARGOS
            },
        },
        "candidatos": candidatos,
    }

    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SAIDA)

    registrar_historico(agora, candidatos, total_geral)

    print(f"  total arrecadado: R$ {total_geral:,.2f}".replace(",", "."))
    print(f"  gravado em {SAIDA}")


def registrar_historico(agora, candidatos, total_geral):
    """Guarda um ponto por dia para o grafico de evolucao."""
    try:
        with open(HISTORICO, encoding="utf-8") as f:
            hist = json.load(f)
    except (OSError, ValueError):
        hist = []

    ponto = {
        "data": agora.strftime("%Y-%m-%d"),
        "hora": agora.strftime("%H:%M"),
        "total": round(total_geral, 2),
        "porCandidato": {c["id"]: c["total"] for c in candidatos if c["total"] > 0},
    }
    hist = [p for p in hist if p["data"] != ponto["data"]]
    hist.append(ponto)
    hist.sort(key=lambda p: p["data"])

    with open(HISTORICO, "w", encoding="utf-8") as f:
        json.dump(hist[-180:], f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
