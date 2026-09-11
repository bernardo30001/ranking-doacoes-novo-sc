"""Só substitui a coleta publicada depois de baixar e conferir todos os dados."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from coletar import FUSO

ROOT = Path(__file__).resolve().parent
FILES = ['dados.json', 'agregados.json', 'historico.json', 'correcoes.json', 'estado.json']


def executar(destino=ROOT):
    with tempfile.TemporaryDirectory(prefix='ranking-coleta-') as temp:
        stage = Path(temp)
        for name in FILES:
            if (destino / name).exists():
                shutil.copy2(destino / name, stage / name)
        env = dict(os.environ, RANKING_DATA_DIR=str(stage), PYTHONUNBUFFERED='1')
        try:
            subprocess.run([sys.executable, str(ROOT / 'coletar.py')], env=env, check=True, timeout=720)
            subprocess.run([sys.executable, str(ROOT / 'verificar.py')], env=env, check=True, timeout=90)
        except (subprocess.SubprocessError, OSError):
            # Nenhum dado financeiro, dia histórico ou estado de comparação muda.
            if (destino / 'dados.json').exists():
                data = json.loads((destino / 'dados.json').read_text())
                data['ultimaTentativa'] = {'quando': datetime.now(FUSO).isoformat(), 'status': 'falhou'}
                (destino / 'dados.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
            raise
        # O servidor e o Pages publicam o manifesto por último.
        shutil.copytree(stage / 'detalhe', destino / 'detalhe', dirs_exist_ok=True)
        for name in FILES[1:]:
            shutil.copy2(stage / name, destino / name)
        shutil.copy2(stage / 'dados.json', destino / 'dados.json')


if __name__ == '__main__':
    executar()
