"""Alertas pessoais do NOVO/SC, enviados só depois da publicação conferida.

O tópico fica em um GitHub Secret. O checkpoint contém apenas dados públicos
e recibos de entrega, nunca o endereço do canal. Não depende do cache do site.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode
import zipfile

from curl_cffi import requests

ROOT = Path(__file__).resolve().parent
CHECKPOINT = 'alertas-estado.json'
ARTIFACT = 'alertas-estado'
SITE = 'https://bernardo30001.github.io/ranking-doacoes-novo-sc/'
ELEICAO = '20322002026'
FUSO = timezone(timedelta(hours=-3))
LIMITE_DIA = 200  # Reserva margem no plano gratuito; o excedente fica na fila.
LIMITE_RODADA = 50
VALORES = {
    'liquido': 'Arrecadação líquida', 'total': 'Receita bruta',
    'devolvido': 'Receitas devolvidas', 'financeiro': 'Recursos financeiros',
    'estimado': 'Recursos estimáveis', 'limiteGasto': 'Limite de gastos',
    'despesas.contratadas': 'Despesas contratadas', 'despesas.pagas': 'Despesas pagas',
    'origem.fundoEspecial': 'Fundo Eleitoral (FEFC)',
    'origem.fundoPartidario': 'Fundo Partidário', 'origem.outros': 'Outros recursos',
    'origem.roni': 'Origem não identificada', 'origem.estimavel': 'Origem estimável',
    'receitas.pessoaFisica': 'Pessoas físicas', 'receitas.pessoaJuridica': 'Pessoas jurídicas',
    'receitas.internet': 'Receitas pela internet', 'receitas.outrosCandidatos': 'Repasses de candidatos',
    'receitas.partidos': 'Repasses de partidos', 'receitas.roni': 'Receita de origem não identificada',
    'receitas.proprios': 'Recursos próprios', 'receitas.financiamentoColetivo': 'Financiamento coletivo',
    'receitas.comercializacao': 'Comercialização', 'receitas.aplicacoes': 'Aplicações financeiras',
    'receitas.bens': 'Bens móveis e imóveis', 'receitas.devolvidas': 'Devoluções declaradas',
}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def centavos(value):
    n = Decimal(str(value or 0))
    if not n.is_finite():
        raise ValueError('Valor inválido nos alertas')
    return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def dinheiro(cents):
    text = f'{abs(cents) // 100:,}'.replace(',', '.') + f',{abs(cents) % 100:02d}'
    return ('−' if cents < 0 else '') + 'R$ ' + text


def curto(text, limit=110):
    return ' '.join(str(text or '').split())[:limit]


def salvar(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json_text(value), encoding='utf-8')
    temp.replace(path)


def ler(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lancamentos(rows):
    # Multiconjunto: duas doações iguais continuam sendo dois lançamentos.
    normalized = []
    for row in rows:
        item = {k: (' '.join(v.split()) if isinstance(v, str) else v)
                for k, v in row.items()}
        item['valor'] = centavos(row['valor'])
        normalized.append(json_text(item))
    return dict(sorted(Counter(normalized).items()))


def retrato(root):
    data = ler(root / 'dados.json')
    if str(data['eleicao']['id']) != ELEICAO or data['eleicao']['uf'] != 'SC':
        raise ValueError('Eleição ou estado incompatível com os alertas')
    if data.get('ultimaTentativa', {}).get('status') == 'falhou':
        return None
    if data.get('auditoria', {}).get('status') != 'ok':
        raise ValueError('Coleta sem conferência')
    base = (root / data.get('arquivosBase', '')).resolve()
    if not base.is_relative_to(root.resolve()):
        raise ValueError('Caminho de coleta inválido')
    result = {}
    for c in data['candidatos']:
        if c['partido'] != 'NOVO' or c['cargo'] not in (6, 7):
            continue
        cid = str(c['id'])
        if not cid.isdigit():
            raise ValueError('Identificador de candidato inválido')
        detail = ler(base / 'detalhe' / (cid + '.json'))
        if str(detail['id']) != cid or detail['atualizadoEm'] != data['atualizadoEm']:
            raise ValueError('Detalhe incompatível com a coleta')
        values = {}
        for key in VALORES:
            v = c
            for part in key.split('.'):
                v = v.get(part) if isinstance(v, dict) else None
            values[key] = centavos(v)
        result[cid] = {
            'nome': c['nome'], 'cargo': c['cargo'],
            'valores': values, 'temContas': c['temContas'],
            'despesasDisponiveis': c.get('despesasDisponiveis', False),
            'receitas': lancamentos(detail['receitas']),
            'despesas': lancamentos(detail['despesas']),
        }
    if not result:
        raise ValueError('Nenhum candidato do NOVO na coleta')
    return {'quando': data['atualizadoEm'], 'candidatos': result}


def financeiro(c):
    return {k: c[k] for k in ('valores', 'temContas', 'despesasDisponiveis', 'receitas', 'despesas')}


def diferencas_itens(old, new, kind):
    before, after = Counter(old), Counter(new)
    removed, added = before - after, after - before
    label, person = ('Receita', 'doador') if kind == 'receitas' else ('Despesa', 'fornecedor')

    def identidade(row):
        # Só chama de alteração quando documento, data e CPF/CNPJ identificam
        # um único lançamento em ambos os retratos. Sem isso, descreve entradas/saídas.
        fields = [row.get(k) for k in ('doc', 'data', 'cpfCnpj')]
        return json_text(fields) if all(fields) else None

    def grupos(counter):
        groups = defaultdict(list)
        for key, qty in counter.items():
            identity = identidade(json.loads(key))
            if identity:
                groups[identity] += [key] * qty
        return groups

    old_groups, new_groups = grupos(before), grupos(after)
    changes = []
    for key in list(removed):
        a = json.loads(key)
        identity = identidade(a)
        if not identity or len(old_groups[identity]) != 1 or len(new_groups[identity]) != 1:
            continue
        new_key = new_groups[identity][0]
        if not added[new_key]:
            continue
        b = json.loads(new_key)
        changed = [f'{label} alterada: {curto(b.get(person) or a.get(person) or "Não informado")}',
                   f'{dinheiro(a["valor"])} → {dinheiro(b["valor"])}']
        for field, title in [('fonte', 'origem'), ('categoria', 'categoria'), ('especie', 'espécie'),
                             ('descricao', 'descrição'), ('origBem', 'doador originário'), (person, 'nome')]:
            if a.get(field) != b.get(field):
                changed.append(f'{title}: {curto(a.get(field) or "não informado")} → {curto(b.get(field) or "não informado")}')
        if a.get('fcc') != b.get('fcc'):
            changed.append('classificação de financiamento coletivo mudou')
        changes.append(' · '.join(changed))
        removed[key] -= 1
        added[new_key] -= 1
    for counter, verb in [(added, 'incluída na declaração'), (removed, 'deixou de constar')]:
        for key, qty in sorted(counter.items(), key=lambda x: -json.loads(x[0])['valor']):
            if not qty:
                continue
            row = json.loads(key)
            who = curto(row.get(person) or 'Não informado')
            source = curto(row.get('fonte') or row.get('categoria') or 'Origem/categoria não informada')
            multiplier = f'{qty} × ' if qty > 1 else ''
            changes.append(f'{label} {verb}: {who} · {multiplier}{dinheiro(row["valor"])} · {source}')
    return changes


def mensagem(cid, before, after, when, previous):
    lines = []
    if before is None:
        lines.append('Candidato passou a integrar o monitor do NOVO/SC. Valores atuais, sem base anterior.')
        lines.append('Arrecadação líquida: ' + dinheiro(after['valores']['liquido']))
    else:
        for key, label in VALORES.items():
            a, b = before['valores'][key], after['valores'][key]
            if a != b:
                lines.append(f'{label}: {dinheiro(a)} → {dinheiro(b)}')
        if before['temContas'] != after['temContas']:
            lines.append('Disponibilidade da prestação de contas mudou.')
        if before['despesasDisponiveis'] != after['despesasDisponiveis']:
            lines.append('Disponibilidade dos dados de despesas mudou.')
        for kind in ('receitas', 'despesas'):
            lines.extend(diferencas_itens(before[kind], after[kind], kind))
    event_id = hashlib.sha256(json_text([ELEICAO, cid, previous, when, before, after]).encode()).hexdigest()
    stamp = datetime.fromisoformat(when).astimezone(FUSO).strftime('%d/%m %H:%M')
    header = f'NOVO/SC · {"Federal" if after["cargo"] == 6 else "Estadual"} · Coleta {stamp} (Brasília)'
    footer = '\nMudanças na declaração do TSE; a data da doação pode ser anterior.\nRef. ' + event_id[:12]
    chosen = []
    for line in lines:
        if len((header + '\n' + '\n'.join(chosen + [line]) + footer).encode()) > 3400:
            break
        chosen.append(line)
    if len(chosen) < len(lines):
        chosen.append(f'Mais {len(lines) - len(chosen)} mudanças. Abra as contas para consultar os lançamentos.')
    url = SITE + '?' + urlencode({'partido': 'NOVO', 'cargo': after['cargo'], 'candidato': cid})
    return {'id': event_id, 'title': curto(after['nome'], 70) + ' · Finanças alteradas',
            'message': header + '\n\n' + '\n'.join(chosen) + footer,
            'click': url, 'tags': ['moneybag']}


def preparar(state, current):
    if current is None:
        return state
    if state is None:
        count = len(current['candidatos'])
        welcome = {
            'id': 'novo-sc-ativacao-v1', 'title': 'Alertas NOVO SC ativados',
            'message': f'Monitor conectado ao ntfy. Acompanhando {count} candidatos a deputado federal e estadual do NOVO em SC.\n\nVocê receberá as próximas mudanças de receitas, despesas, pagamentos e origem do dinheiro detectadas nas coletas completas. Coleta programada de hora em hora.\n\nEsta mensagem confirma a conexão; não é uma nova doação.',
            'click': SITE + '?partido=NOVO', 'tags': ['white_check_mark'],
        }
        return {'schema': 1, 'eleicao': ELEICAO, 'snapshot': current,
                'pendentes': [welcome], 'enviados': [], 'entregues': []}
    previous = state['snapshot']
    if datetime.fromisoformat(current['quando']) < datetime.fromisoformat(previous['quando']):
        return state  # Reexecução de uma publicação antiga não gera uma queda falsa.
    if previous['quando'] == current['quando']:
        if previous != current:
            raise ValueError('Dois retratos diferentes com a mesma data de coleta')
        return state
    pending_ids = {e['id'] for e in state['pendentes']}
    for cid, after in current['candidatos'].items():
        before = previous['candidatos'].get(cid)
        if before is not None and financeiro(before) == financeiro(after):
            continue
        event = mensagem(cid, before, after, current['quando'], previous['quando'])
        if event['id'] not in pending_ids:
            state['pendentes'].append(event)
    # Candidato que sai da lista não vira receita zero nem despesa removida.
    state['snapshot'] = current
    return state


def restaurar(repo):
    # A API inclui checkpoints de execuções com erro no envio. O último arquivo
    # contém a fila ainda pendente e os recibos salvos antes de cada interrupção.
    endpoint = f'repos/{repo}/actions/artifacts?name={ARTIFACT}&per_page=100'
    result = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
    artifacts = [a for a in result['artifacts'] if not a['expired'] and a['name'] == ARTIFACT]
    if not artifacts:
        if result.get('total_count', 0):
            raise RuntimeError('Os checkpoints de alertas expiraram; recuperação necessária')
        return None
    latest = max(artifacts, key=lambda a: a['id'])
    raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{latest["id"]}/zip'])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        state = json.loads(archive.read(CHECKPOINT))
    if state.get('schema') != 1 or state.get('eleicao') != ELEICAO:
        raise ValueError('Checkpoint de alertas incompatível')
    for key in ('snapshot', 'pendentes', 'enviados', 'entregues'):
        if key not in state:
            raise ValueError('Checkpoint incompleto')
    print('Checkpoint recuperado; pendentes:', len(state['pendentes']))
    return state


class Ntfy:
    def __init__(self, topic):
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', topic):
            raise ValueError('Tópico ntfy inválido ou curto demais')
        self.topic = topic

    def publicados(self):
        try:
            response = requests.get('https://ntfy.sh/' + self.topic + '/json',
                                    params={'poll': '1', 'since': 'all'}, timeout=30)
            if response.status_code != 200:
                raise RuntimeError('Falha ao consultar recibos ntfy')
            return {x['sequence_id'] for line in response.text.splitlines()
                    if (x := json.loads(line)).get('sequence_id')}
        except Exception:
            # Não revela o tópico em logs públicos, nem envia de novo às cegas.
            raise RuntimeError('Não foi possível conferir os recibos ntfy. Fila preservada.') from None

    def enviar(self, event):
        payload = {k: event[k] for k in ('title', 'message', 'click', 'tags')}
        payload.update(topic=self.topic, sequence_id=event['id'], priority=3)
        payload['actions'] = [{'action': 'view', 'label': 'Ver contas', 'url': event['click']}]
        try:
            response = requests.post('https://ntfy.sh/',
                                     data=json_text(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, timeout=30)
            if response.status_code != 200:
                raise RuntimeError('Envio rejeitado')
            result = response.json()
            if result.get('event') != 'message' or result.get('sequence_id') != event['id']:
                raise RuntimeError('Recibo incompatível')
            return result['id']
        except Exception:
            raise RuntimeError('Envio ntfy não confirmado. Fila preservada para a próxima execução.') from None


def entregar(state, client, path, now=None):
    now = now or datetime.now(timezone.utc)
    state['enviados'] = [t for t in state['enviados'] if datetime.fromisoformat(t) > now - timedelta(days=1)]
    salvar(path, state)  # Fila persistida antes de qualquer envio.
    if not state['pendentes']:
        print('Nenhuma alteração nova do NOVO/SC.')
        return
    confirmed = client.publicados()
    count = 0
    while state['pendentes'] and count < LIMITE_RODADA:
        event = state['pendentes'][0]
        if event['id'] in confirmed:
            receipt = 'recuperado-do-ntfy'
        elif len(state['enviados']) < LIMITE_DIA:
            receipt = client.enviar(event)
        else:
            break
        state['enviados'].append(now.isoformat())
        state['entregues'].append({'id': event['id'], 'recibo': receipt, 'quando': now.isoformat()})
        state['entregues'] = state['entregues'][-500:]
        state['pendentes'].pop(0)
        salvar(path, state)
        count += 1
    print(f'Alertas confirmados: {count}; aguardando envio: {len(state["pendentes"])}')
    if state['pendentes']:
        print('::warning::Há alertas na fila. Nova tentativa na próxima execução, respeitando os limites do ntfy.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=ROOT)
    parser.add_argument('--local-state', action='store_true', help='Usa apenas o checkpoint local; para ensaios')
    parser.add_argument('--dry-run', action='store_true', help='Compara e salva sem enviar notificações')
    args = parser.parse_args()
    topic = os.environ.get('NTFY_TOPIC', '')
    if not topic and not args.dry_run:
        print('Alertas não configurados: defina o secret NTFY_TOPIC.')
        return
    path = args.data_dir / CHECKPOINT
    state = (ler(path) if path.exists() else None) if args.local_state else restaurar(os.environ['GITHUB_REPOSITORY'])
    state = preparar(state, retrato(args.data_dir))
    if state is None:
        print('Aguardando a primeira coleta completa para iniciar os alertas.')
        return
    if args.dry_run:
        salvar(path, state)
        print('Ensaio sem envio; pendentes:', len(state['pendentes']))
    else:
        entregar(state, Ntfy(topic), path)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Mensagens das bibliotecas HTTP podem conter URLs/credenciais.
        print('::error::Falha nos alertas (' + type(error).__name__ + '). Verifique o checkpoint; o site continua publicado.')
        sys.exit(1)
