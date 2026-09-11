"""Monta uma publicação conferida com recursos identificados por seu conteúdo."""
import hashlib
import json
import shutil
from pathlib import Path
import verificar

ROOT = Path(__file__).resolve().parent
ASSETS = ['index.html', 'estilo.css', 'modelo.js', 'app.js', 'icone.svg']


def build():
    if verificar.main():
        raise RuntimeError('A conferência dos dados falhou; publicação cancelada.')
    out = ROOT / '_site'
    if out.exists():
        shutil.rmtree(out)  # Apenas a pasta gerada por este publicador.
    out.mkdir()
    version = hashlib.sha256(b''.join((ROOT / x).read_bytes() for x in ASSETS)).hexdigest()[:12]
    data = json.loads((ROOT / 'dados.json').read_text())
    resources = ['agregados.json', 'historico.json', 'correcoes.json']
    resources += ['detalhe/' + c['id'] + '.json' for c in data['candidatos']]
    digest = hashlib.sha256((ROOT / 'dados.json').read_bytes())
    for name in sorted(resources):
        digest.update(name.encode())
        digest.update((ROOT / name).read_bytes())
    base = 'coletas/' + digest.hexdigest()[:16] + '/'
    target = out / base
    for asset in ASSETS:
        shutil.copy2(ROOT / asset, out / asset)
    html = (out / 'index.html').read_text()
    for asset in ASSETS[1:]:
        html = html.replace('"' + asset + '"', '"' + asset + '?v=' + version + '"')
    (out / 'index.html').write_text(html)
    for name in resources:
        for dest in [target / name, out / name]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
    data['arquivosBase'] = base
    data['auditoria'] = {'status': 'ok', 'candidatos': len(data['candidatos']), 'checagens': 12,
                        'tipo': 'Conferência aritmética; não é aprovação de contas'}
    (out / 'dados.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    (out / 'versao.json').write_text(json.dumps({'assets': version, 'coleta': data['atualizadoEm'], 'recursos': base}))
    print('Publicação pronta:', out, 'versão', version)


if __name__ == '__main__':
    build()
