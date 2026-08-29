#!/usr/bin/env python3
"""
Coletor de dados de financiamento de campanha - DivulgaCandContas / TSE.

Baixa TODOS os candidatos a Deputado Federal (cargo 6) e Deputado Estadual
(cargo 7) em Santa Catarina, de todos os partidos, junto com a prestacao de
contas de cada um, e grava tudo em dados.json.

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
CARGOS = {6: "Deputado Federal", 7: "Deputado Estadual"}
DESTAQUE = "NOVO"            # partido em destaque no painel
TRABALHADORES = 8            # requisicoes simultaneas ao TSE

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
                # Corpo vazio com 200 e como o TSE diz "nao ha registro aqui"
                # (candidato sem prestacao de contas). Nao adianta insistir.
                if not r.text.strip():
                    return None
                return r.json()
            print(f"  ! HTTP {r.status_code} em {url}", file=sys.stderr)
        except Exception as e:
            print(f"  ! {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(1.5 * (i + 1))
    return None


def listar_candidatos(cargo):
    """Lista todos os candidatos de um cargo, de todos os partidos."""
    url = f"{BASE}/candidatura/listar/{ANO}/{UF}/{ID_ELEICAO}/{cargo}/candidatos"
    j = get(url)
    if not j:
        raise RuntimeError(f"nao consegui listar candidatos do cargo {cargo}")
    return j.get("candidatos") or []


def numeros_de_partido(cargo):
    """Mapa sigla -> numero do partido. A listagem de candidatos traz
    numero=0, entao pegamos os numeros de verdade neste endpoint."""
    lista = get(f"{BASE}/eleicao/{ID_ELEICAO}/ues/{UF}/cargos/{cargo}/partidos") or []
    return {p["sigla"]: p["numero"] for p in lista if p.get("sigla")}


def num(v):
    """Normaliza valores monetarios (None -> 0.0)."""
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def coletar_um(item):
    cargo, base, nr_partido = item
    id_cand = base["id"]
    numero = base["numero"]

    detalhe = get(f"{BASE}/candidatura/buscar/{ANO}/{UF}/{ID_ELEICAO}/candidato/{id_cand}") or {}
    contas = get(f"{BASE}/prestador/consulta/{ID_ELEICAO}/{ANO}/{UF}/{cargo}/{nr_partido}/{numero}/{id_cand}")

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
    fornecedores = fornecedores[:10]

    entregas = [{
        "data": e.get("dataEntrega"),
        "tipo": e.get("tipo"),
        "retificadora": e.get("retificadora") == "SIM",
    } for e in ((contas or {}).get("historicoEntregas") or [])[:6]]

    partido = (base.get("partido") or {})

    return {
        "id": str(id_cand),
        "nome": base.get("nomeUrna"),
        "nomeCompleto": detalhe.get("nomeCompleto") or base.get("nomeCompleto"),
        "numero": numero,
        "cargo": cargo,
        "cargoNome": CARGOS[cargo],
        "partido": partido.get("sigla"),
        "partidoNome": partido.get("nome"),
        "partidoNumero": nr_partido,
        "coligacao": base.get("nomeColigacao"),
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
        # Origem do dinheiro. Os tres primeiros somam o total financeiro; RONI e
        # estimaveis ficam de fora dele, e os cinco juntos fecham o total recebido.
        "origem": {
            "fundoEspecial": num(d.get("graphVrReceitaFinFefc")),
            "fundoPartidario": num(d.get("graphVrReceitaFinFundo")),
            "outros": num(d.get("graphVrReceitaFinOutros")),
            "roni": num(d.get("totalRoni")),
            "estimavel": num(d.get("totalEstimados")),
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
    print(f"[{agora:%d/%m/%Y %H:%M:%S}] coletando candidatos de {UF}...")

    alvos = []
    for cargo in CARGOS:
        lista = listar_candidatos(cargo)
        numeros = numeros_de_partido(cargo)
        faltando = set()
        for c in lista:
            sigla = (c.get("partido") or {}).get("sigla")
            nr = numeros.get(sigla)
            if nr is None:
                # fallback: os dois primeiros digitos do numero do candidato
                nr = int(str(c["numero"])[:2])
                faltando.add(sigla)
            alvos.append((cargo, c, nr))
        print(f"  {CARGOS[cargo]}: {len(lista)} candidatos, {len(numeros)} partidos")
        if faltando:
            print(f"    (numero do partido deduzido para: {', '.join(sorted(map(str, faltando)))})")

    inicio = time.time()
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as pool:
        candidatos = list(pool.map(coletar_um, alvos))
    print(f"  {len(candidatos)} prestacoes de contas em {time.time() - inicio:.0f}s")

    candidatos.sort(key=lambda c: -c["total"])
    for i, c in enumerate(candidatos, 1):
        c["posicao"] = i

    total_geral = sum(c["total"] for c in candidatos)
    partidos = sorted({c["partido"] for c in candidatos if c["partido"]})

    saida = {
        "atualizadoEm": agora.isoformat(),
        "eleicao": {"id": ID_ELEICAO, "ano": int(ANO), "uf": UF, "destaque": DESTAQUE},
        "partidos": partidos,
        "resumo": {
            "candidatos": len(candidatos),
            "comArrecadacao": sum(1 for c in candidatos if c["total"] > 0),
            "totalArrecadado": round(total_geral, 2),
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
    # Sao 640 candidatos: guardar muitos dias deixaria o arquivo pesado
    # para quem abre o painel. O painel so usa o ponto do dia anterior.
    hist = hist[-45:]

    with open(HISTORICO, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
