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
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from curl_cffi import requests

BASE = "https://divulgacandcontas.tse.jus.br/divulga/rest/v1"
ID_ELEICAO = "20322002026"   # Eleicao Geral Federal 2026
ANO = "2026"
UF = "SC"
CARGOS = {6: "Deputado Federal", 7: "Deputado Estadual"}
DESTAQUE = "NOVO"            # partido em destaque no painel
TRABALHADORES = 8            # requisicoes simultaneas ao TSE

AQUI = os.environ.get("RANKING_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(AQUI, "dados.json")
HISTORICO = os.path.join(AQUI, "historico.json")
AGREGADOS = os.path.join(AQUI, "agregados.json")
CORRECOES = os.path.join(AQUI, "correcoes.json")
ESTADO = os.path.join(AQUI, "estado.json")
DETALHE = os.path.join(AQUI, "detalhe")
FUSO = timezone(timedelta(hours=-3))  # horario de Brasilia

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://divulgacandcontas.tse.jus.br/divulga/",
}


class ErroColeta(RuntimeError):
    """Uma falha de transporte nunca deve virar receita zero."""


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
    raise ErroColeta(f"TSE indisponível após {tentativas} tentativas: {url}")


def listar_candidatos(cargo):
    """Lista todos os candidatos de um cargo, de todos os partidos."""
    url = f"{BASE}/candidatura/listar/{ANO}/{UF}/{ID_ELEICAO}/{cargo}/candidatos"
    j = get(url)
    if not j:
        raise RuntimeError(f"nao consegui listar candidatos do cargo {cargo}")
    lista = j.get("candidatos")
    if not isinstance(lista, list) or not lista:
        raise ErroColeta(f"Listagem incompleta para cargo {cargo}")
    return lista


def numeros_de_partido(cargo):
    """Mapa sigla -> numero do partido. A listagem de candidatos traz
    numero=0, entao pegamos os numeros de verdade neste endpoint."""
    lista = get(f"{BASE}/eleicao/{ID_ELEICAO}/ues/{UF}/cargos/{cargo}/partidos") or []
    return {p["sigla"]: p["numero"] for p in lista if p.get("sigla")}


def num(v):
    """Normaliza valores monetarios (None -> 0.0)."""
    try:
        value = round(float(v or 0), 2)
        if not math.isfinite(value):
            raise ValueError("Valor não finito")
        return value
    except (TypeError, ValueError) as exc:
        raise ErroColeta("O TSE retornou um valor monetário inválido") from exc


def receitas_itemizadas(id_prestador, id_entrega):
    """Lancamentos de receita, um a um. Substitui o ranking do TSE, que so
    publica os 5 maiores doadores de cada candidato."""
    l = get(f"{BASE}/prestador/consulta/receitas/{ID_ELEICAO}/{id_prestador}/{id_entrega}/lista?pagina=1")
    if not isinstance(l, list):
        raise ErroColeta(f"Lista de receitas indisponível: {id_prestador}/{id_entrega}")
    return [{
        "data": r.get("dtReceita"),
        "doador": r.get("nomeDoador"),
        "cpfCnpj": r.get("cpfCnpjDoador"),
        "origBem": r.get("nomeDoadorOriginario") if r.get("cpfCnpjDoadorOriginario") != r.get("cpfCnpjDoador") else None,
        "valor": num(r.get("valorReceita")),
        "fonte": r.get("fonteOrigem"),
        "especie": r.get("especieRecurso"),
        "doc": r.get("nrDocumento"),
        "fcc": bool(r.get("stFinanciamentoColetivo")),
    } for r in (l or [])]


def despesas_itemizadas(id_prestador, id_entrega):
    """Lancamentos de despesa: para quem foi o dinheiro e em que categoria."""
    l = get(f"{BASE}/prestador/consulta/despesas/{ID_ELEICAO}/{id_prestador}/{id_entrega}")
    if not isinstance(l, list):
        raise ErroColeta(f"Lista de despesas indisponível: {id_prestador}/{id_entrega}")
    return [{
        "data": x.get("data"),
        "fornecedor": x.get("nomeFornecedor"),
        "cpfCnpj": x.get("cpfCnpjFornecedor"),
        "valor": num(x.get("valor")),
        "categoria": x.get("tipoDespesa"),
        "descricao": x.get("descricaoDespesa"),
        "especie": x.get("especieRecurso"),
        "doc": x.get("numeroDocumento"),
    } for x in (l or [])]


def agrupar(itens, chave_nome, chave_doc):
    """Soma os lancamentos por pessoa/empresa, preservando a contagem."""
    por = {}
    for i in itens:
        k = i[chave_doc] or i[chave_nome]
        e = por.setdefault(k, {"cpfCnpj": i[chave_doc], "nome": i[chave_nome],
                               "qtd": 0, "valor": 0.0, "fcc": False})
        e["qtd"] += 1
        e["valor"] += i["valor"]
        e["fcc"] = e["fcc"] or bool(i.get("fcc"))
    l = sorted(por.values(), key=lambda x: -x["valor"])
    for e in l:
        e["valor"] = round(e["valor"], 2)
    return l


def coletar_um(item):
    cargo, base, nr_partido = item
    id_cand = base["id"]
    numero = base["numero"]

    detalhe = get(f"{BASE}/candidatura/buscar/{ANO}/{UF}/{ID_ELEICAO}/candidato/{id_cand}")
    if not isinstance(detalhe, dict) or str(detalhe.get("id")) != str(id_cand):
        raise ErroColeta(f"Cadastro indisponível: {id_cand}")
    contas = get(f"{BASE}/prestador/consulta/{ID_ELEICAO}/{ANO}/{UF}/{cargo}/{nr_partido}/{numero}/{id_cand}")

    if contas is not None and (not isinstance(contas, dict) or str(contas.get("idCandidato")) != str(id_cand)):
        raise ErroColeta(f"Prestação incompatível: {id_cand}")
    d = (contas or {}).get("dadosConsolidados") or {}
    desp = (contas or {}).get("despesas") or {}

    id_prestador = (contas or {}).get("idPrestador")
    id_entrega = (contas or {}).get("idUltimaEntrega")

    receitas, despesas = [], []
    if id_prestador and id_entrega:
        receitas = receitas_itemizadas(id_prestador, id_entrega)
        despesas = despesas_itemizadas(id_prestador, id_entrega)

    doadores = agrupar(receitas, "doador", "cpfCnpj")
    fornecedores = agrupar(despesas, "fornecedor", "cpfCnpj")

    categorias = {}
    for x in despesas:
        c = x["categoria"] or "Nao especificada"
        categorias[c] = round(categorias.get(c, 0) + x["valor"], 2)

    entregas = [{
        "data": e.get("dataEntrega"),
        "tipo": e.get("tipo"),
        "retificadora": e.get("retificadora") == "SIM",
    } for e in ((contas or {}).get("historicoEntregas") or [])]

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
        "idPrestador": id_prestador,
        "idEntrega": id_entrega,
        "despesasDisponiveis": desp.get("totalDespesasContratadas") is not None,
        "contasAtualizadas": (contas or {}).get("dataUltimaAtualizacaoContas"),

        # Total e composicao por natureza da receita
        "total": num(d.get("totalRecebido")),
        "devolvido": num(d.get("totalDoacaoDevolvida")),
        "liquido": round(num(d.get("totalRecebido")) - num(d.get("totalDoacaoDevolvida")), 2),
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
        "entregas": entregas,
        "qtdDoadores": len(doadores),
        "qtdFornecedores": len(fornecedores),
        "qtdLancamentos": len(receitas),
        # Fica fora do dados.json: vira agregados.json e detalhe/<id>.json.
        "_agregado": {
            "doadores": doadores,
            "fornecedores": fornecedores,
            "categorias": categorias,
        },
        "_itens": {"receitas": receitas, "despesas": despesas},
    }


def validar_candidato(c):
    """Rejeita coleta incompleta antes de gerar quedas ou apagar histórico."""
    a, it = c["_agregado"], c["_itens"]
    pares = [
        (sum(c["origem"].values()), c["liquido"], "origem"),
        (sum(c["receitas"].values()), c["total"], "natureza"),
        (sum(x["valor"] for x in it["receitas"]), c["liquido"], "receitas itemizadas"),
        (sum(x["valor"] for x in it["despesas"]), c["despesas"]["contratadas"], "despesas itemizadas"),
        (sum(x["valor"] for x in a["fornecedores"]), c["despesas"]["contratadas"], "fornecedores"),
    ]
    import math
    for obtido, esperado, rotulo in pares:
        if not math.isfinite(obtido) or not math.isfinite(esperado) or abs(obtido - esperado) > 0.05:
            raise ErroColeta(f"{c['nome']}: {rotulo} incompletas ({obtido:.2f} vs {esperado:.2f})")


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
    pool = ThreadPoolExecutor(max_workers=TRABALHADORES)
    jobs = [pool.submit(coletar_um, alvo) for alvo in alvos]
    try:
        candidatos = [job.result() for job in as_completed(jobs)]
    finally:
        # Não inicia centenas de consultas pendentes depois de uma falha.
        pool.shutdown(wait=True, cancel_futures=True)
    print(f"  {len(candidatos)} prestacoes de contas em {time.time() - inicio:.0f}s")

    # Validar ANTES de atualizar o histórico ou o detector de alterações.
    try:
        anteriores = {c["id"]: c for c in json.load(open(SAIDA, encoding="utf-8"))["candidatos"]}
    except FileNotFoundError:
        anteriores = {}
    ids = {c["id"] for c in candidatos}
    if len(ids) != len(candidatos):
        raise ErroColeta("Candidatos duplicados na listagem")
    desaparecidos = set(anteriores) - ids
    if desaparecidos:
        raise ErroColeta(f"A listagem deixou de incluir {len(desaparecidos)} candidatos; requer conferência")
    for c in candidatos:
        if not c["temContas"] and anteriores.get(c["id"], {}).get("temContas"):
            raise ErroColeta(f"Prestação antes disponível desapareceu: {c['nome']}")
        validar_candidato(c)
    agora = datetime.now(FUSO)
    candidatos.sort(key=lambda c: -c["liquido"])
    for i, c in enumerate(candidatos, 1):
        c["posicao"] = i

    # Separa o que sai do dados.json antes de montar a saida.
    agregados, itens = {}, {}
    for c in candidatos:
        agregados[c["id"]] = c.pop("_agregado")
        itens[c["id"]] = c.pop("_itens")

    correcoes = detectar_correcoes(agora, candidatos, itens)
    gravar_agregados(agregados)
    gravar_detalhes(agora, candidatos, itens)

    total_geral = sum(c["total"] for c in candidatos)
    partidos = sorted({c["partido"] for c in candidatos if c["partido"]})

    saida = {
        "atualizadoEm": agora.isoformat(),
        "versaoSchema": 2,
        "auditoria": {"status": "ok", "candidatos": len(candidatos), "tipo": "Conferência aritmética; não é aprovação de contas"},
        "eleicao": {"id": ID_ELEICAO, "ano": int(ANO), "uf": UF, "destaque": DESTAQUE},
        "partidos": partidos,
        "resumo": {
            "candidatos": len(candidatos),
            "comArrecadacao": sum(1 for c in candidatos if c["total"] > 0),
            "totalArrecadado": round(sum(c["liquido"] for c in candidatos), 2),
            "totalBruto": round(total_geral, 2),
            "totalDevolvido": round(sum(c["devolvido"] for c in candidatos), 2),
            "porCargo": {
                CARGOS[k]: round(sum(c["liquido"] for c in candidatos if c["cargo"] == k), 2)
                for k in CARGOS
            },
        },
        "candidatos": candidatos,
    }

    saida["correcoesRecentes"] = len(correcoes)

    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SAIDA)

    registrar_historico(agora, candidatos, total_geral)

    print(f"  total arrecadado: R$ {total_geral:,.2f}".replace(",", "."))
    print(f"  gravado em {SAIDA}")


def gravar_agregados(agregados):
    """Doadores, fornecedores e categorias por candidato. Sai do dados.json
    para o painel abrir rapido; o front busca este arquivo depois."""
    tmp = AGREGADOS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(agregados, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, AGREGADOS)


def gravar_detalhes(agora, candidatos, itens):
    """Um arquivo por candidato com os lancamentos um a um, carregado so
    quando alguem abre o card daquele candidato."""
    os.makedirs(DETALHE, exist_ok=True)
    vivos = set()
    for c in candidatos:
        it = itens.get(c["id"]) or {}
        vivos.add(f'{c["id"]}.json')
        corpo = {
            "id": c["id"],
            "nome": c["nome"],
            "idPrestador": c["idPrestador"],
            "idEntrega": c["idEntrega"],
            "atualizadoEm": agora.isoformat(),
            "receitas": it["receitas"],
            "despesas": it["despesas"],
        }
        with open(os.path.join(DETALHE, f'{c["id"]}.json'), "w", encoding="utf-8") as f:
            json.dump(corpo, f, ensure_ascii=False, separators=(",", ":"))

    # Candidato que zerou a prestacao nao pode ficar com o detalhe antigo no ar.
    for nome in os.listdir(DETALHE):
        if nome.endswith(".json") and nome not in vivos:
            os.remove(os.path.join(DETALHE, nome))


def _chaves(receitas):
    """Multiconjunto dos lancamentos. E multiconjunto, e nao dicionario, porque
    doc+data+doador+fonte se repete (doacoes iguais no mesmo dia) e 41 de cada
    500 lancamentos vem sem numero de documento."""
    from collections import Counter
    return Counter(
        f'{r["doc"] or ""}|{r["data"] or ""}|{r["cpfCnpj"] or ""}|{r["fonte"] or ""}|{r["valor"]:.2f}'
        for r in receitas
    )


def detectar_correcoes(agora, candidatos, itens):
    """Compara os lancamentos com os da rodada anterior e registra quando uma
    campanha muda o valor de uma doacao ja declarada, ou apaga uma.

    Doacao nova nao entra: isso e o fluxo normal da campanha. O que interessa
    e a redeclaracao — foi assim que a Bia Borba passou de R$ 814 mil para
    R$ 546 mil, com um PIX de 04/09 reescrito de R$ 280 mil para R$ 12 mil.
    """
    from collections import Counter, defaultdict

    try:
        with open(ESTADO, encoding="utf-8") as f:
            antes = json.load(f)
    except (OSError, ValueError):
        antes = {}

    try:
        with open(CORRECOES, encoding="utf-8") as f:
            feed = json.load(f)
    except (OSError, ValueError):
        feed = []

    eventos, estado = [], {}
    for c in candidatos:
        receitas = (itens.get(c["id"]) or {}).get("receitas") or []
        agora_ct = _chaves(receitas)
        meta = {f'{r["doc"] or ""}|{r["data"] or ""}|{r["cpfCnpj"] or ""}|{r["fonte"] or ""}':
                [r["doador"], r["data"], r["fonte"]] for r in receitas}
        estado[c["id"]] = {"total": c["total"], "liquido": c["liquido"], "itens": dict(agora_ct),
                           "meta": meta, "idPrestador": c["idPrestador"], "idEntrega": c["idEntrega"]}

        ant = antes.get(c["id"])
        if not ant:
            continue  # candidato novo no retrato: nada com que comparar

        ant_ct = Counter(ant.get("itens") or {})
        saiu, entrou = ant_ct - agora_ct, agora_ct - ant_ct
        if not saiu and not entrou:
            continue

        def por_lancamento(ct):
            g = defaultdict(list)
            for k, n in ct.items():
                *ident, valor = k.split("|")
                g["|".join(ident)] += [float(valor)] * n
            return g

        gs, ge = por_lancamento(saiu), por_lancamento(entrou)
        nomes = dict(ant.get("meta") or {})
        nomes.update({f'{r["doc"] or ""}|{r["data"] or ""}|{r["cpfCnpj"] or ""}|{r["fonte"] or ""}':
                 (r["doador"], r["data"], r["fonte"]) for r in receitas})

        alteracoes, removidos = [], []
        for ident, velhos in gs.items():
            novos = ge.get(ident, [])
            doador, data, fonte = nomes.get(ident, (None, ident.split("|")[1], ident.split("|")[3]))
            for i, v in enumerate(sorted(velhos, reverse=True)):
                if i < len(novos):
                    n = sorted(novos, reverse=True)[i]
                    if abs(v - n) <= 0.05:
                        continue
                    alteracoes.append({"doc": ident.split("|")[0], "data": data, "doador": doador, "fonte": fonte,
                                       "de": v, "para": n})
                else:
                    removidos.append({"doc": ident.split("|")[0], "data": data, "doador": doador, "fonte": fonte, "valor": v})
            ge[ident] = novos[len(velhos):]

        novos_lancamentos = sum(len(v) for v in ge.values())
        if not alteracoes and not removidos:
            continue  # so entrou dinheiro novo: fluxo normal, nao e correcao

        eventos.append({
            "quando": agora.isoformat(),
            "id": c["id"], "nome": c["nome"], "partido": c["partido"],
            "cargo": c["cargo"], "cargoNome": c["cargoNome"],
            "totalAntes": ant.get("total"), "totalDepois": c["total"],
            "idPrestador": c["idPrestador"], "entregaAntes": ant.get("idEntrega"), "entregaDepois": c["idEntrega"],
            "alteracoes": alteracoes, "removidos": removidos,
            "novos": novos_lancamentos,
        })

    if eventos:
        eventos.sort(key=lambda e: -abs((e["totalDepois"] or 0) - (e["totalAntes"] or 0)))
        feed = eventos + feed
        print(f"  {len(eventos)} correcao(oes) de prestacao detectada(s)")
        for e in eventos[:5]:
            print(f'     {e["nome"]} ({e["partido"]}): '
                  f'{e["totalAntes"]:,.2f} -> {e["totalDepois"]:,.2f}')

    for arq, dado in ((CORRECOES, feed[:300]), (ESTADO, estado)):
        tmp = arq + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dado, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, arq)

    return eventos


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
        "porCandidato": {c["id"]: c["total"] for c in candidatos},
        "porCandidatoLiquido": {c["id"]: c["liquido"] for c in candidatos},
        "escopoCompleto": True,
    }
    hist = [p for p in hist if p["data"] != ponto["data"]]
    hist.append(ponto)
    hist.sort(key=lambda p: p["data"])
    # Mantém até 45 dias; o gráfico exibe os 14 registros mais recentes.
    hist = hist[-45:]

    with open(HISTORICO + ".tmp", "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    os.replace(HISTORICO + ".tmp", HISTORICO)


if __name__ == "__main__":
    main()
