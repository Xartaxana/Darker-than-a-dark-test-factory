"""board_server — локальный сервер живой борды.

Открывает доску в браузере с кнопкой «↻ Обновить». Каждый запрос страницы
ПЕРЕСОБИРАЕТ доску из артефактов (test-cases/, bugs/, runs/), поэтому кнопка —
это просто перезагрузка страницы, а данные всегда свежие. Без git и без коммитов.

Запуск:  python scripts/board_server.py   (Ctrl+C — остановить)
По умолчанию слушает 127.0.0.1:8777 и открывает браузер.
"""
from __future__ import annotations

import http.server
import socketserver
import sys
import threading
import webbrowser

from board_view import collect, render

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = render(collect(), live=True).encode("utf-8")  # пересборка из артефактов
        except Exception as e:  # noqa: BLE001 — покажем ошибку в странице, не роняем сервер
            body = f"<h1>Ошибка сборки борды</h1><pre>{e}</pre>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # тихо
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        print(f"Не удалось занять {HOST}:{PORT} ({e}). Возможно, сервер уже запущен — "
              f"откройте http://{HOST}:{PORT}/")
        return
    url = f"http://{HOST}:{PORT}/"
    print(f"Живая борда: {url}  (Ctrl+C — остановить)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
        srv.shutdown()


if __name__ == "__main__":
    main()
