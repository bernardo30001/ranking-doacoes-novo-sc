"""Recupera a última publicação completa, inclusive se o cache expirar."""
import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from coletar import agrupar

ROOT = Path(__file__).resolve().parent


def ler(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def restaurar(snapshot, destino):
    data = ler(snapshot / 'dados.json', {})
    if not data.get('candidatos'):
        raise ValueError('Publicação anterior sem candidatos')
    prefix = data.get('arquivosBase', '')
    # Os arquivos de compatibilidade na raiz também existem nas versões antigas.
    base = snapshot / prefix if prefix else snapshot
    if not base.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError('Caminho de publicação inválido')
    aggregates = {}
    details = {}
    for c in data['candidatos']:
        detail = ler(base / 'detalhe' / (c['id'] + '.json'), None)
        if detail is None:
            if c['liquido'] or c['despesas']['contratadas']:
                raise ValueError('Lançamentos ausentes: ' + c['nome'])
            detail = {'id': c['id'], 'nome': c['nome'], 'atualizadoEm': data['atualizadoEm'], 'receitas': [], 'despesas': []}
        if detail['id'] != c['id'] or detail['atualizadoEm'] != data['atualizadoEm']:
            raise ValueError('Detalhe de outra coleta')
        categories = {}
        for row in detail['despesas']:
            key = row['categoria'] or 'Não informado'
            categories[key] = round(categories.get(key, 0) + row['valor'], 2)
        aggregates[c['id']] = {'doadores': agrupar(detail['receitas'], 'doador', 'cpfCnpj'),
                               'fornecedores': agrupar(detail['despesas'], 'fornecedor', 'cpfCnpj'),
                               'categorias': categories}
        details[c['id']] = detail
    # Conserva dias recuperados de ambos os lugares. A publicação é a referência
    # quando há duas versões do mesmo dia: ela passou por coleta e publicação.
    history = {p['data']: p for p in ler(destino / 'historico.json', [])}
    history.update({p['data']: p for p in ler(base / 'historico.json', [])})
    data.pop('arquivosBase', None)
    data['versaoSchema'] = 2
    data['resumo']['totalArrecadado'] = round(sum(c['liquido'] for c in data['candidatos']), 2)
    data['resumo']['totalBruto'] = round(sum(c['total'] for c in data['candidatos']), 2)
    data['resumo']['totalDevolvido'] = round(sum(c['devolvido'] for c in data['candidatos']), 2)
    data['resumo']['porCargo'] = {name: round(sum(c['liquido'] for c in data['candidatos'] if c['cargoNome'] == name), 2)
                               for name in {c['cargoNome'] for c in data['candidatos']}}
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'detalhe').mkdir(exist_ok=True)
    output = {'dados.json': data, 'agregados.json': aggregates,
              'historico.json': sorted(history.values(), key=lambda p: p['data'])[-45:],
              'correcoes.json': ler(base / 'correcoes.json', [])}
    for name, value in output.items():
        (destino / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    for cid, value in details.items():
        (destino / 'detalhe' / (cid + '.json')).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
    print('Última publicação recuperada:', data['atualizadoEm'], len(details), 'candidatos;', len(history), 'dias')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    if args.snapshot:
        restaurar(args.snapshot, ROOT)
        return
    repo = os.environ['GITHUB_REPOSITORY']
    runs = json.loads(subprocess.check_output(['gh', 'run', 'list', '--repo', repo, '--workflow', 'atualizar.yml',
                                               '--status', 'success', '--limit', '1', '--json', 'databaseId'], text=True))
    if not runs:
        raise RuntimeError('Não foi encontrada uma publicação anterior concluída')
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp)
        subprocess.run(['gh', 'run', 'download', str(runs[0]['databaseId']), '--repo', repo,
                        '--name', 'github-pages', '--dir', temp], check=True)
        with tarfile.open(snapshot / 'artifact.tar') as archive:
            archive.extractall(snapshot, filter='data')
        restaurar(snapshot, ROOT)


if __name__ == '__main__':
    main()
