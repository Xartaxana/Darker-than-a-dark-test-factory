"""mitmproxy addon: перехват тела ИСХОДЯЩЕГО запроса (AT-BUG-073, критерий
готовности п.4 «примитив перехвата исходящего тела запроса публикации»).

Загружается `mitm.start_replay(..., capture_out=..., capture_url_substr=...)`
через `-s <этот файл>` РЯДОМ с существующим `--server-replay` — оба addon'а
реагируют на ОДНО И ТО ЖЕ событие `request()` для каждого flow (порядок
регистрации между ними не важен для перехвата: встроенный `ServerPlayback`
addon читает `flow.request` только чтобы посчитать хэш матчинга и, при
совпадении, САМ выставляет `flow.response` — он НЕ модифицирует и не убивает
`flow.request`, поэтому этот addon видит ИСХОДНОЕ тело запроса независимо от
того, успел ли реплей уже на него "ответить"). Симметрично МОК-слою (мок
отвечает на запрос заранее записанным содержимым, см.
`gitlab_snippet_mock.py`) — этот addon НЕ отвечает и не блокирует поток,
только СНИМАЕТ копию.

Опции пусты по умолчанию — addon безопасно грузить даже без активного
перехвата (не используется ни один существующий вызывающий `start_replay`
без явного `capture_out`, поэтому этот файл сейчас подключается ТОЛЬКО когда
`capture_out` передан)."""
from __future__ import annotations

import json
import time

from mitmproxy import ctx, http


class RequestBodyCapture:
    def load(self, loader) -> None:
        loader.add_option(
            "capture_out", str, "",
            "Путь JSONL-файла, в который дописываются перехваченные тела запросов",
        )
        loader.add_option(
            "capture_url_substr", str, "",
            "Подстрока URL — перехватываются только запросы, чей pretty_url её содержит",
        )

    def request(self, flow: http.HTTPFlow) -> None:
        out = ctx.options.capture_out
        substr = ctx.options.capture_url_substr
        if not out:
            return
        # Критик-вход (attempt 4, блокер 1): ПУСТАЯ `substr` — валидное
        # «перехватывать ВСЕ POST/PUT/PATCH», как задокументировано выше и в
        # `mitm.py:start_replay` — раньше `or not substr` возвращалась ДО
        # проверки метода, молча отключая перехват целиком (файл `out` даже
        # не создавался бы), что делало негативные оракулы («ни одного
        # PUT/POST перехвачено») ложно-зелёными при пустой подстроке.
        # `substr not in url` с `substr == ""` уже НИКОГДА не истинно (пустая
        # строка — подстрока любой строки) — фильтр ниже сам по себе корректно
        # трактует пустую `substr` как «без фильтра по URL».
        if substr not in flow.request.pretty_url:
            return
        # Перехватываем ТОЛЬКО запросы, несущие тело публикации (createSnippet/
        # updateSnippet) — GET (fetchRemote) не несёт тела, перехватывать нечего.
        if flow.request.method not in ("POST", "PUT", "PATCH"):
            return
        record = {
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "body": flow.request.get_text(strict=False),
            "captured_at": time.time(),
        }
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


addons = [RequestBodyCapture()]
