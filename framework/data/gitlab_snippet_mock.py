"""Мок GitLab Snippet API (`/api/v4/snippets`) для области `sync` (AT-BUG-073).

`SyncRepository.kt` (app-under-test) бьёт по ТРЁМ эндпойнтам через голый
`OkHttpClient` — тот же device-wide прокси (`framework/core/mitm.py`), что уже
перехватывает WebView-навигацию и `DownloadRepository`'s
`OkHttpClient`-транзакции (`work_with_download.mitm`, см. `recording_builder.py`
модульный докстринг):

  GET  {instance}/api/v4/snippets/{id}/raw  -- fetchRemote: сырое содержимое
                                                снимка библиотеки (НЕ обёрнуто в
                                                GitLab JSON-конверт "snippet" —
                                                `/raw` отдаёт файл как есть)
  POST {instance}/api/v4/snippets            -- createSnippet: тело ответа несёт
                                                {"id": ...}, парсится
                                                `JSONObject(text).opt("id")`
  PUT  {instance}/api/v4/snippets/{id}       -- updateSnippet: код ответа
                                                проверяется только через
                                                `response.isSuccessful`, тело
                                                не читается вовсе

ВАЖНО (сверено с исходником, `SyncRepository.kt:286-294`): обновление снимка —
`PUT`, НЕ `PATCH` (bugs/AT-BUG-073.md критерий готовности говорит «PATCH» —
устаревшая формулировка находки; код приложения — источник истины, см. память
проекта «PROJECT.md unreliable»). Мок реализует РЕАЛЬНЫЙ метод (`PUT`), не
текст тикета.

server-replay матчит ПО УМОЛЧАНИЮ ТАКЖЕ по телу запроса (`mitmproxy.addons.
serverplayback._hash`, `server_replay_ignore_content` option, дефолт `False`)
— живая находка AT-BUG-073 attempt 1 (см. докстринг `framework.core.mitm.
start_replay`): для GET (`fetchRemote`, пустое тело) это безобидно, но
POST/PUT (`createSnippet`/`updateSnippet`) несут НЕПРЕДСКАЗУЕМОЕ тело
(мерженный JSON библиотеки, зависит от состояния устройства) — записанный
здесь плейсхолдер `b""` НЕ совпадёт с реальным телом БЕЗ `ignore_content=True`
на стороне мока. Использующий этот модуль тест ОБЯЗАН поднимать replay через
`conftest.py::sync_replay` (зовёт `mitm.start_replay(..., ignore_content=True)`),
не голый `replay`/`mitm.start_replay(...)` без опции — иначе PUT/POST уйдёт
в live-forward на реальный gitlab.com."""
from __future__ import annotations

import json
from pathlib import Path

from framework.data.recording_builder import make_json_flow, write_flows

DEFAULT_INSTANCE = "https://gitlab.com"  # == SyncRepository.DEFAULT_INSTANCE


def snippet_raw_url(snippet_id: str, instance: str = DEFAULT_INSTANCE) -> str:
    return f"{instance}/api/v4/snippets/{snippet_id}/raw"


def snippets_create_url(instance: str = DEFAULT_INSTANCE) -> str:
    return f"{instance}/api/v4/snippets"


def snippet_update_url(snippet_id: str, instance: str = DEFAULT_INSTANCE) -> str:
    return f"{instance}/api/v4/snippets/{snippet_id}"


def make_snippet_get_flow(snippet_id: str, content: str, instance: str = DEFAULT_INSTANCE,
                           status: int = 200):
    """GET `.../raw` -> тело ответа = `content` СЫРЫМ текстом (не JSON-конверт) —
    ровно то, что `fetchRemote` кладёт в `response.body?.string()`."""
    return make_json_flow(
        "GET", snippet_raw_url(snippet_id, instance), content.encode("utf-8"), status=status,
    )


def make_snippet_create_flow(response_id: str, instance: str = DEFAULT_INSTANCE, status: int = 201):
    """POST `/api/v4/snippets` -> `{"id": response_id}` — `createSnippet` читает
    ТОЛЬКО поле `id` (`JSONObject(text).opt("id")?.toString()`), остальные поля
    GitLab-ответа приложением не используются, мок их не несёт."""
    body = json.dumps({"id": response_id}).encode("utf-8")
    return make_json_flow("POST", snippets_create_url(instance), body, status=status)


def make_snippet_update_flow(snippet_id: str, instance: str = DEFAULT_INSTANCE, status: int = 200):
    """PUT `/api/v4/snippets/{id}` -> тело ответа приложением НЕ читается
    (`updateSnippet` проверяет только `response.isSuccessful`) — содержимое
    ответа произвольно, лишь бы код был успешным."""
    body = json.dumps({"id": snippet_id}).encode("utf-8")
    return make_json_flow("PUT", snippet_update_url(snippet_id, instance), body, status=status)


def build_snippet_mock(
    path: Path, *, snippet_id: str, remote_content: str, instance: str = DEFAULT_INSTANCE,
    include_create: bool = False,
) -> None:
    """Собирает `.mitm` с GET (raw)/PUT (update) для `snippet_id`, опционально
    POST (create) — используется тестами, где `sync_snippet_id` УЖЕ настроен
    (существующий снимок, самый частый случай области `sync`: TC-207..217/
    221..231/233/234 предполагают уже сконфигурированную синхронизацию, не
    сценарий первого создания снипета). `include_create=True` — для кейсов
    первого создания (`snippet_id` пуст в UI, `createSnippet` вызывается,
    ответ POST задаёт ID, под который затем матчится этот же `.mitm`)."""
    flows = [
        make_snippet_get_flow(snippet_id, remote_content, instance=instance),
        make_snippet_update_flow(snippet_id, instance=instance),
    ]
    if include_create:
        flows.append(make_snippet_create_flow(snippet_id, instance=instance))
    write_flows(path, flows)


# --- Конструкторы содержимого JSON-снимка (LibraryJson.kt v3: works/filterProfiles/
# tombstones) — поля 1:1 с `LibraryJson.workToJson`/`profileToJson`/`tombstoneToJson`.
# Необязательные поля (rating/comment/fandom/wordCount/tags) опущены при `None` —
# `workFromJson` читает отсутствующий ключ и НАЛИЧИЕ ключа со значением JSON null
# ОДИНАКОВО (`obj.isNull(...)`/`obj.optString(...)` дают тот же default) — упрощает
# конструктор, не меняя семантику разбора приложением. ---

def work_json(
    ao3_id: str, timestamp: int, *, rating: str | None = None, comment: str | None = None,
    fandom: str | None = None, word_count: int | None = None, tags: list[str] | None = None,
    title: str = "", author: str = "", url: str | None = None,
) -> dict:
    """Один элемент массива `works` удалённого снимка. `rating` — строка имени
    enum (`SAVE`/`LIKE`/`READ`/`DISLIKE`) или `None` (comment-only строка,
    `LibraryJson.workFromJson` принимает `rating=null`)."""
    return {
        "ao3Id": ao3_id,
        "title": title,
        "author": author,
        "url": url or f"https://archiveofourown.org/works/{ao3_id}",
        "rating": rating,
        "comment": comment,
        "fandom": fandom,
        "wordCount": word_count,
        "tags": tags,
        "timestamp": timestamp,
    }


def profile_json(profile_id: str, name: str, query_string: str, timestamp: int) -> dict:
    """Один элемент массива `filterProfiles` удалённого снимка."""
    return {"id": profile_id, "name": name, "queryString": query_string, "timestamp": timestamp}


def tombstone_json(kind: str, entity_id: str, deleted_at: int) -> dict:
    """Один элемент массива `tombstones` удалённого снимка. `kind` —
    `"work"`/`"profile"` (`SyncTombstone.KIND_WORK`/`KIND_PROFILE`)."""
    return {"kind": kind, "id": entity_id, "deletedAt": deleted_at}


def remote_snapshot_content(
    works: list[dict] = (), profiles: list[dict] = (), tombstones: list[dict] = (),
) -> str:
    """Сериализует полный снимок (v3, `LibraryJson`-конверт) — СЫРОЕ тело, которое
    `make_snippet_get_flow` кладёт в ответ на `.../raw` (fetchRemote читает его
    как есть, `JSONObject(remoteRaw)`)."""
    return json.dumps({
        "version": 3,
        "works": list(works),
        "filterProfiles": list(profiles),
        "tombstones": list(tombstones),
    })
