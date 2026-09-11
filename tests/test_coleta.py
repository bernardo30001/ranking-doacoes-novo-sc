import copy, json, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import coletar
import atualizar
import recuperar
import subprocess

def candidate(value=100):
    receipt={'doc':'PIX-1','data':'04/09/2026','cpfCnpj':'123','fonte':'Fundo Partidário','valor':value,'doador':'DOADOR'}
    return {'id':'1','nome':'CANDIDATO','partido':'NOVO','cargo':6,'cargoNome':'Deputado Federal','total':value,'liquido':value,'devolvido':0,'idPrestador':'2','idEntrega':'3','origem':{'fundos':value},'receitas':{'partidos':value,'devolvidas':0},'despesas':{'contratadas':0},'_agregado':{'fornecedores':[]},'_itens':{'receitas':[receipt],'despesas':[]}}

class Tests(unittest.TestCase):
    def test_invalid_amount_is_not_zero(self):
        for value in ['inválido', float('nan'), float('inf')]:
            with self.assertRaises(coletar.ErroColeta):coletar.num(value)
        self.assertEqual(coletar.num(None),0)
    def test_transport_failure_is_not_zero(self):
        with patch.object(coletar.requests,'get',side_effect=TimeoutError('simulado')),patch.object(coletar.time,'sleep'):
            with self.assertRaises(coletar.ErroColeta):coletar.get('https://tse.invalid',2)
    def test_truncated_items_rejected(self):
        c=candidate();coletar.validar_candidato(c)
        c['_itens']['receitas']=[]
        with self.assertRaises(coletar.ErroColeta):coletar.validar_candidato(c)
    def test_all_suppliers_included(self):
        items=[{'nome':str(i),'doc':str(i),'valor':1} for i in range(35)]
        out=coletar.agrupar(items,'nome','doc');self.assertEqual(len(out),35);self.assertEqual(sum(x['valor'] for x in out),35)
    def test_correction_duplicate_removal_and_replay(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(coletar,'ESTADO',str(Path(temp)/'estado.json')),patch.object(coletar,'CORRECOES',str(Path(temp)/'correcoes.json')):
            now=datetime.now(timezone.utc);c=candidate();items={'1':c['_itens']}
            self.assertEqual(coletar.detectar_correcoes(now,[c],items),[])
            self.assertEqual(coletar.detectar_correcoes(now,[c],items),[])
            c=candidate(80);items={'1':c['_itens']};result=coletar.detectar_correcoes(now,[c],items)
            self.assertEqual(result[0]['alteracoes'][0]['de'],100);self.assertEqual(result[0]['alteracoes'][0]['para'],80)
            self.assertEqual(coletar.detectar_correcoes(now,[c],items),[])
            c=candidate(0);c['_itens']['receitas']=[];items={'1':c['_itens']};result=coletar.detectar_correcoes(now,[c],items)
            self.assertEqual(result[0]['removidos'][0]['doador'],'DOADOR')
    def test_multiset_keeps_duplicates(self):
        r=candidate()['_itens']['receitas'][0];self.assertEqual(sum(coletar._chaves([r,r]).values()),2)
    def test_history_keeps_existing_days_and_explicit_zero(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(coletar,'HISTORICO',str(Path(temp)/'historico.json')):
            path=Path(coletar.HISTORICO);path.write_text(json.dumps([{'data':'2026-08-30','total':100,'porCandidato':{'1':100}}]));c=candidate(0)
            coletar.registrar_historico(datetime(2026,9,11,tzinfo=timezone.utc),[c],0)
            h=json.loads(path.read_text());self.assertEqual(len(h),2);self.assertEqual(h[-1]['porCandidatoLiquido']['1'],0);self.assertIn('1',h[-1]['porCandidato'])
    def test_failed_refresh_preserves_published_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            data={'atualizadoEm':'2026-09-11T00:00:00-03:00','candidatos':[{'total':123}]}
            (root/'dados.json').write_text(json.dumps(data))
            (root/'historico.json').write_text('[{"data":"2026-09-10"}]')
            (root/'estado.json').write_text('{"original":true}')
            with patch.object(atualizar.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'coletar')):
                with self.assertRaises(subprocess.CalledProcessError):atualizar.executar(root)
            after=json.loads((root/'dados.json').read_text())
            self.assertEqual(after['atualizadoEm'],data['atualizadoEm'])
            self.assertEqual(after['candidatos'],data['candidatos'])
            self.assertEqual(after['ultimaTentativa']['status'],'falhou')
            self.assertEqual((root/'historico.json').read_text(),'[{"data":"2026-09-10"}]')
            self.assertEqual((root/'estado.json').read_text(),'{"original":true}')
    def test_restore_rebuilds_complete_supplier_list(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);src=root/'source';dst=root/'destination';src.mkdir();dst.mkdir();(src/'detalhe').mkdir()
            c=candidate();c['despesas']['contratadas']=35
            data={'atualizadoEm':'2026-09-11T00:00:00-03:00','candidatos':[c],'resumo':{}}
            (src/'dados.json').write_text(json.dumps(data))
            detail={'id':'1','atualizadoEm':data['atualizadoEm'],'receitas':c['_itens']['receitas'],
                    'despesas':[{'fornecedor':str(i),'cpfCnpj':str(i),'valor':1,'categoria':'Serviços'} for i in range(35)]}
            (src/'detalhe'/'1.json').write_text(json.dumps(detail))
            (src/'historico.json').write_text('[{"data":"2026-09-11"}]')
            (dst/'historico.json').write_text('[{"data":"2026-09-10"}]')
            recuperar.restaurar(src,dst)
            self.assertEqual(len(json.loads((dst/'agregados.json').read_text())['1']['fornecedores']),35)
            self.assertEqual(len(json.loads((dst/'historico.json').read_text())),2)
            self.assertEqual(json.loads((dst/'dados.json').read_text())['atualizadoEm'],data['atualizadoEm'])
if __name__=='__main__':unittest.main()
