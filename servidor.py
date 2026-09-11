#!/usr/bin/env python3
"""
Servidor do painel de doacoes NOVO/SC.

Sobe o site em http://localhost:8000 e reexecuta o coletor de tempos em
tempos, para o painel ficar sempre em dia sem ninguem precisar mexer.

    python3 servidor.py                # atualiza a cada 30 min
    python3 servidor.py --minutos 10   # a cada 10 min
    python3 servidor.py --porta 8080
"""

import argparse
import http.server
import json
import os
import socketserver
import threading
import time
import webbrowser
from datetime import datetime

import atualizar

AQUI = os.path.dirname(os.path.abspath(__file__))
trava = threading.Lock()
ultima_coleta = {"quando": None, "erro": None}


def coletar_agora():
    """Roda o coletor. Uma execucao por vez."""
    with trava:
        try:
            atualizar.executar()
            ultima_coleta.update(quando=datetime.now().isoformat(), erro=None)
            return True, None
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            ultima_coleta.update(erro=msg)
            print(f"  ! falha na coleta: {msg}")
            return False, msg


def laco(minutos):
    while True:
        time.sleep(minutos * 60)
        coletar_agora()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=AQUI, **kw)

    def do_POST(self):
        if self.path.rstrip("/") != "/api/atualizar":
            return self.send_error(404)
        from urllib.parse import urlsplit
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self.send_error(403)
        ok, erro = coletar_agora()
        corpo = json.dumps({"ok": ok, "erro": erro}).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def end_headers(self):
        # nenhum JSON pode ficar em cache, senao o painel congela
        if self.path.split("?")[0].endswith(".json"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # silencia o log de cada arquivo servido


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    p = argparse.ArgumentParser(description="Painel de doacoes NOVO/SC")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--minutos", type=int, default=30, help="intervalo entre coletas")
    p.add_argument("--sem-navegador", action="store_true")
    args = p.parse_args()
    if args.minutos < 1 or not 1 <= args.porta <= 65535:
        p.error("Use intervalo de pelo menos 1 minuto e porta entre 1 e 65535.")

    if not os.path.exists(os.path.join(AQUI, "dados.json")):
        coletar_agora()

    threading.Thread(target=laco, args=(args.minutos,), daemon=True).start()

    url = f"http://localhost:{args.porta}"
    with Servidor(("127.0.0.1", args.porta), Handler) as s:
        print(f"\n  Painel no ar: {url}")
        print(f"  Atualizando os dados a cada {args.minutos} min. Ctrl+C para parar.\n")
        if not args.sem_navegador:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print("\n  encerrado.")


if __name__ == "__main__":
    main()
