import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import alertas


T1 = '2026-09-14T10:00:00-03:00'
T2 = '2026-09-14T11:00:00-03:00'


def receipt(value=100, **fields):
    return dict({'doc': 'PIX-1', 'data': '10/09/2026', 'cpfCnpj': '123',
                 'doador': 'DOADOR', 'fonte': 'Outros Recursos', 'valor': value}, **fields)


def candidate():
    return {'nome': 'CANDIDATO', 'cargo': 6,
            'valores': {k: 10000 if k in ('liquido', 'total', 'financeiro') else 0 for k in alertas.VALORES},
            'temContas': True, 'despesasDisponiveis': True,
            'receitas': alertas.lancamentos([receipt()]), 'despesas': {}}


def snapshot(c=None, when=T1):
    return {'quando': when, 'candidatos': {'1': c or candidate()}}


def baseline():
    state = alertas.preparar(None, snapshot())
    state['pendentes'] = []
    return state


class Client:
    def __init__(self, fail_at=None, published=()):
        self.sent = []
        self.fail_at = fail_at
        self.published = set(published)

    def publicados(self):
        return self.published

    def enviar(self, event):
        if len(self.sent) == self.fail_at:
            raise RuntimeError('Indisponibilidade simulada')
        self.sent.append(event)
        return 'recibo'


class AlertasTests(unittest.TestCase):
    def test_first_collection_only_activates_no_historical_donations(self):
        state = alertas.preparar(None, snapshot())
        self.assertEqual(len(state['pendentes']), 1)
        self.assertEqual(state['pendentes'][0]['id'], 'novo-sc-ativacao-v1')
        self.assertNotIn('Receita incluída', state['pendentes'][0]['message'])

    def test_no_changes_no_notification(self):
        state = baseline()
        same = snapshot(when=T2)
        same['candidatos']['1']['nome'] = 'Nome atualizado no cadastro'
        self.assertFalse(alertas.preparar(state, same)['pendentes'])

    def test_new_donation_and_replay(self):
        c = candidate()
        c['receitas'] = alertas.lancamentos([receipt(), receipt(20, doc='PIX-2')])
        c['valores']['liquido'] = 12000
        state = alertas.preparar(baseline(), snapshot(c, T2))
        self.assertEqual(len(state['pendentes']), 1)
        self.assertIn('Receita incluída na declaração: DOADOR', state['pendentes'][0]['message'])
        self.assertIn('R$ 100,00 → R$ 120,00', state['pendentes'][0]['message'])
        self.assertEqual(len(alertas.preparar(state, snapshot(c, T2))['pendentes']), 1)

    def test_source_change_with_same_total(self):
        c = candidate()
        c['receitas'] = alertas.lancamentos([receipt(fonte='Fundo Partidário')])
        message = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]['message']
        self.assertIn('Receita alterada', message)
        self.assertIn('origem: Outros Recursos → Fundo Partidário', message)

    def test_correction_and_removal(self):
        c = candidate()
        c['receitas'] = alertas.lancamentos([receipt(12)])
        message = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]['message']
        self.assertIn('R$ 100,00 → R$ 12,00', message)
        c['receitas'] = {}
        message = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]['message']
        self.assertIn('Receita deixou de constar', message)

    def test_expense_and_payment_change(self):
        c = candidate()
        expense = dict(doc='NF-1', data='14/09/2026', cpfCnpj='456', fornecedor='GRÁFICA',
                       valor=30, categoria='Impressos', descricao='Panfletos')
        c['despesas'] = alertas.lancamentos([expense])
        c['valores']['despesas.contratadas'] = 3000
        c['valores']['despesas.pagas'] = 2000
        message = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]['message']
        self.assertIn('Despesa incluída na declaração: GRÁFICA', message)
        self.assertIn('Despesas pagas: R$ 0,00 → R$ 20,00', message)

    def test_refund_without_item_change(self):
        c = candidate()
        c['valores']['devolvido'] = 1000
        message = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]['message']
        self.assertIn('Receitas devolvidas: R$ 0,00 → R$ 10,00', message)

    def test_multisets_ignore_order_keep_duplicates_and_do_not_guess_identity(self):
        rows = [receipt(), receipt(20, doc='PIX-2')]
        self.assertEqual(alertas.lancamentos(rows), alertas.lancamentos(list(reversed(rows))))
        before = alertas.lancamentos([receipt(), receipt()])
        after = alertas.lancamentos([receipt(), receipt(), receipt()])
        diff = alertas.diferencas_itens(before, after, 'receitas')
        self.assertEqual(len(diff), 1)
        self.assertIn('Receita incluída', diff[0])
        before = alertas.lancamentos([receipt(doc='')])
        after = alertas.lancamentos([receipt(20, doc='')])
        diff = '\n'.join(alertas.diferencas_itens(before, after, 'receitas'))
        self.assertNotIn('alterada', diff)
        self.assertIn('deixou de constar', diff)

    def test_no_fake_zero_for_missing_candidate_or_failed_collection(self):
        state = baseline()
        self.assertIs(alertas.preparar(state, None), state)
        self.assertFalse(alertas.preparar(state, {'quando': T2, 'candidatos': {}})['pendentes'])

    def test_old_snapshot_does_not_roll_back_state(self):
        state = baseline()
        state['snapshot']['quando'] = T2
        self.assertEqual(alertas.preparar(state, snapshot())['snapshot']['quando'], T2)

    def test_transport_failure_keeps_unsent_queue_and_successes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / alertas.CHECKPOINT
            state = baseline()
            state['pendentes'] = [{'id': 'one'}, {'id': 'two'}]
            client = Client(fail_at=1)
            with self.assertRaises(RuntimeError):
                alertas.entregar(state, client, path)
            saved = alertas.ler(path)
            self.assertEqual([e['id'] for e in saved['pendentes']], ['two'])
            self.assertEqual(saved['entregues'][0]['id'], 'one')
            retry = Client()
            alertas.entregar(saved, retry, path)
            self.assertEqual([e['id'] for e in retry.sent], ['two'])

    def test_timeout_recovered_from_ntfy_receipt_without_resending(self):
        with tempfile.TemporaryDirectory() as temp:
            state = baseline()
            state['pendentes'] = [{'id': 'one'}]
            client = Client(published=['one'])
            alertas.entregar(state, client, Path(temp) / alertas.CHECKPOINT)
            self.assertEqual(client.sent, [])
            self.assertFalse(state['pendentes'])

    def test_daily_limit_keeps_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            now = alertas.datetime.now(alertas.timezone.utc)
            state = baseline()
            state['pendentes'] = [{'id': 'later'}]
            state['enviados'] = [now.isoformat()] * alertas.LIMITE_DIA
            client = Client()
            alertas.entregar(state, client, Path(temp) / alertas.CHECKPOINT, now)
            self.assertFalse(client.sent)
            self.assertEqual(len(state['pendentes']), 1)

    def test_large_unicode_message_respects_ntfy_limit(self):
        c = candidate()
        c['receitas'] = alertas.lancamentos([receipt(i, doc=str(i), doador='DOAÇÃO ÇÃO' * 30) for i in range(200)])
        event = alertas.preparar(baseline(), snapshot(c, T2))['pendentes'][0]
        self.assertLessEqual(len(event['message'].encode()), 4096)
        self.assertIn('Mais ', event['message'])
        self.assertNotIn('cpfCnpj', event['message'])

    def test_receipts_and_secrets_are_not_logged_on_http_error(self):
        topic = 'segredo-nao-pode-aparecer-no-log'
        with patch.object(alertas.requests, 'get', side_effect=RuntimeError(topic)):
            with self.assertRaises(RuntimeError) as caught:
                alertas.Ntfy(topic).publicados()
            self.assertNotIn(topic, str(caught.exception))

    def test_checkpoint_restored_from_artifact_including_pending_events(self):
        state = baseline()
        state['pendentes'] = [{'id': 'pending'}]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr(alertas.CHECKPOINT, json.dumps(state))
        listing = {'artifacts': [{'id': 42, 'name': alertas.ARTIFACT, 'expired': False}], 'total_count': 1}
        with patch.object(alertas.subprocess, 'check_output', side_effect=[json.dumps(listing), buffer.getvalue()]):
            self.assertEqual(alertas.restaurar('owner/repo'), state)

    def test_corrupt_remote_checkpoint_never_silently_rebaselines(self):
        with patch.object(alertas.subprocess, 'check_output', return_value='broken'):
            with self.assertRaises(ValueError):
                alertas.restaurar('owner/repo')

    def test_retrato_filters_scope_validates_date_and_ignores_refresh_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'detalhe').mkdir()
            c = dict(id='1', nome='NOVO FEDERAL', partido='NOVO', cargo=6, temContas=True,
                     total=100, liquido=100, despesasDisponiveis=True)
            other = dict(c, id='2', partido='PL')
            wrong_office = dict(c, id='3', cargo=5)
            data = {'atualizadoEm': T1, 'eleicao': {'id': alertas.ELEICAO, 'uf': 'SC'},
                    'auditoria': {'status': 'ok'}, 'candidatos': [c, other, wrong_office]}
            detail = {'id': '1', 'atualizadoEm': T1, 'receitas': [receipt()], 'despesas': []}
            alertas.salvar(root / 'dados.json', data)
            alertas.salvar(root / 'detalhe/1.json', detail)
            result = alertas.retrato(root)
            self.assertEqual(list(result['candidatos']), ['1'])
            self.assertEqual(result['candidatos']['1']['valores']['liquido'], 10000)
            detail['atualizadoEm'] = T2
            alertas.salvar(root / 'detalhe/1.json', detail)
            with self.assertRaises(ValueError):
                alertas.retrato(root)
            data['ultimaTentativa'] = {'status': 'falhou'}
            alertas.salvar(root / 'dados.json', data)
            self.assertIsNone(alertas.retrato(root))


if __name__ == '__main__':
    unittest.main()
