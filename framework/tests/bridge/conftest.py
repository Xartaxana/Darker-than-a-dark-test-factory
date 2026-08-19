"""Локальный conftest.py слоя L2 bridge (device-free контракт-тесты `ao3_bridge.js`
против jsdom, `docs/01-test-strategy.md` §«Политика слоёв», `docs/tasks/
p2-pyramid-bridge.md` узел N5). БЕЗ Appium/эмулятора — весь пакет device-free.

`_ensure_app_installed` no-op override — ЕДИНОЕ переопределение на слой (вместо
копии в каждом файле пакета): родительский `framework/tests/conftest.py` несёт
`_ensure_app_installed` как ЕДИНСТВЕННУЮ session-scoped autouse точку входа,
которую уже ~20 существующих device-free юнит-проб (`test_*_unit.py`)
переопределяют тем же приёмом (см. докстринг родительской фикстуры) — этот
локальный conftest распространяет приём на пакет `bridge/` целиком. Гейт
`arch_check.py` (rglob) переопределение НЕ обходит — проверено r1 recon
(`docs/tasks/p2-pyramid-bridge.md`, «Факты»).

Subprocess-протокол (докстринг `framework/bridge_harness/run_bridge.js`,
AT-BUG-079 класс, факт 6 recon): list-argv, `shell=False`, АБСОЛЮТНЫЕ пути,
payload — через ФАЙЛЫ (не argv), `encoding="utf-8"` ОБЯЗАТЕЛЕН на этой стороне
(subprocess python из cp1251-локали, node пишет UTF-8 — без явной кодировки
`text=True` даёт ТИХУЮ порчу кириллицы при УСПЕШНОМ `json.loads`), timeout,
внятный отказ при отсутствии node/jsdom.

Отсутствие node/jsdom при p1-прогоне — ЖЁСТКИЙ отказ (`RuntimeError` с
инструкцией), НЕ молчаливый skip (Р3, DoD N5): `_node_executable`/
`_ensure_harness_ready` бросают исключение ДО спавна подпроцесса."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

from framework.config import settings

@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру родительского conftest.py (см. докстринг
    модуля) — пакет `bridge/` не трогает устройство вовсе."""
    yield


HARNESS_DIR = settings.FRAMEWORK_ROOT / "bridge_harness"
ENTRYPOINT = HARNESS_DIR / "run_bridge.js"
BRIDGE_JS_PATH = (
    settings.REPO_ROOT / "app-under-test" / "app" / "src" / "main" / "assets" / "ao3_bridge.js"
)
# Щедрый запас над наблюдаемыми прогонами харнесса (jsdom init + eval — доли
# секунды, см. критик-вход N5: logs/routing-log.jsonl, task_id
# "p2-n5-bridge-harness", event "accepted" 2026-08-19T11:42:52) — тот же дух, что и остальные таймауты
# framework/config/settings.py (явная TimeoutExpired вместо неопределённого
# клина). Введённая граница — тест НА ней и ЗА ней см.
# test_subprocess_boundary.py (CLAUDE.md builder п. 6а).
DEFAULT_TIMEOUT_SEC = 30.0
DEFAULT_CANARY = "проверка кириллицы N5 (bridge-harness protocol canary)"


def _node_executable() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "node не найден в PATH — bridge-harness (L2, docs/tasks/p2-pyramid-bridge.md, "
            "Р3) требует Node.js. Установи Node.js, затем выполни: "
            "powershell -NoProfile -ExecutionPolicy Bypass -Command "
            "\". D:\\AO3_tests\\scripts\\tasks.ps1; Ensure-BridgeHarness\" "
            "-- ЖЁСТКИЙ отказ (не skip), DoD N5."
        )
    return node


def _ensure_harness_ready() -> None:
    if not ENTRYPOINT.exists():
        raise RuntimeError(
            f"bridge-harness entrypoint не найден: {ENTRYPOINT} -- дерево репозитория "
            "повреждено или framework/bridge_harness/ не склонирован полностью."
        )
    jsdom_marker = HARNESS_DIR / "node_modules" / "jsdom" / "package.json"
    if not jsdom_marker.exists():
        raise RuntimeError(
            "framework/bridge_harness/node_modules/jsdom отсутствует -- jsdom не "
            "установлен. Выполни: powershell -NoProfile -ExecutionPolicy Bypass "
            "-Command \". D:\\AO3_tests\\scripts\\tasks.ps1; Ensure-BridgeHarness\" "
            "-- ЖЁСТКИЙ отказ (не skip), DoD N5."
        )


def _bridge_call_raw(payload: dict, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict:
    """Вызывает харнесс, возвращает СЫРОЙ ответ (без ассертов ok/канарейки) —
    нужен для тестов, которые сами хотят проверить путь отказа (красные пробы,
    граница таймаута)."""
    node = _node_executable()
    _ensure_harness_ready()

    payload = dict(payload)
    payload.setdefault("bridgeJsPath", str(BRIDGE_JS_PATH))
    payload.setdefault("canary", DEFAULT_CANARY)

    # Windows-нативный tempfile.gettempdir() (НЕ POSIX-путь Git Bash) — короткий
    # per-call uuid-суффикс, MAX_PATH-безопасно (CLAUDE.md builder п.10).
    tmp_dir = Path(tempfile.gettempdir())
    request_path = tmp_dir / f"ao3_bridge_req_{uuid.uuid4().hex}.json"
    response_path = tmp_dir / f"ao3_bridge_resp_{uuid.uuid4().hex}.json"
    try:
        request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [node, str(ENTRYPOINT), str(request_path), str(response_path)],
            cwd=str(HARNESS_DIR),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        if not response_path.exists():
            raise RuntimeError(
                "bridge-harness не записал response.json "
                f"(returncode={proc.returncode}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        return json.loads(response_path.read_text(encoding="utf-8"))
    finally:
        request_path.unlink(missing_ok=True)
        response_path.unlink(missing_ok=True)


def _bridge_call(payload: dict, *, timeout: float = DEFAULT_TIMEOUT_SEC) -> dict:
    """Как `_bridge_call_raw`, но с обязательными ассертами happy-path: `ok is
    True` и кириллическая канарейка протокола совпала (round-trip encoding не
    сломан, AT-BUG-079 класс, факт 6 recon) — большинство пилотных тестов
    зовут именно эту обёртку.

    Порядок проверок (Б1, критик-раунд 2, `p2-n5-bridge-harness` accepted
    2026-08-19T11:42:52): СНАЧАЛА `ok` -- ошибка ВНУТРИ харнесса (исключение в
    `runRequest`, `run_bridge.js`) поднимается как `RuntimeError` с РЕАЛЬНЫМ
    `error`/`stack` из ответа, а не тонет за канарейкой (ошибочный ответ мог
    вообще не нести `canaryEcho` -- прежний порядок ловил ЛЮБУЮ ошибку харнесса
    как ложное «round-trip encoding сломан», теряя настоящую причину). Канарейка
    проверяется ВТОРОЙ, только на happy-path (`ok is True`); порча кириллицы на
    ОШИБОЧНОМ ответе всё ещё не теряется -- `run_bridge.js` эхо-ит `canaryEcho`
    и в ветке ошибки (см. `main()`), поэтому здесь она допечатывается в текст
    `RuntimeError`, а не проглатывается молча."""
    canary = payload.get("canary", DEFAULT_CANARY)
    response = _bridge_call_raw(payload, timeout=timeout)
    if not response.get("ok", False):
        canary_note = ""
        if canary is not None and response.get("canaryEcho") != canary:
            canary_note = (
                " [ДОПОЛНИТЕЛЬНО: кириллическая канарейка протокола тоже НЕ совпала "
                f"на этом ошибочном ответе (отправлено {canary!r}, получено "
                f"{response.get('canaryEcho')!r}) -- round-trip encoding мог быть "
                "сломан даже на пути ошибки]"
            )
        raise RuntimeError(
            "bridge-harness вернул ok=false: "
            f"error={response.get('error')!r} stack={response.get('stack')!r}{canary_note}"
        )
    if canary is not None and response.get("canaryEcho") != canary:
        raise AssertionError(
            "кириллическая канарейка протокола НЕ совпала -- round-trip encoding "
            f"сломан (отправлено {canary!r}, получено {response.get('canaryEcho')!r})"
        )
    return response


@pytest.fixture()
def bridge_call():
    """Возвращает callable `(payload: dict, *, timeout=30.0) -> dict` —
    happy-path обёртка (ассертит ok=true + канарейку)."""
    return _bridge_call


@pytest.fixture()
def bridge_call_raw():
    """Возвращает callable `(payload: dict, *, timeout=30.0) -> dict` — СЫРОЙ
    ответ харнесса, без ассертов (красные пробы/граница таймаута)."""
    return _bridge_call_raw


@pytest.fixture()
def bridge_js_path() -> Path:
    return BRIDGE_JS_PATH
