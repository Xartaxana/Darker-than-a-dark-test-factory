"""Кириллическая канарейка subprocess-протокола (факт 6 recon,
`docs/tasks/p2-pyramid-bridge.md`, класс AT-BUG-079): node пишет `response.json`
UTF-8, вызывающий Python-подпроцесс живёт в cp1251-локали хоста — `text=True`
БЕЗ явного `encoding="utf-8"` даёт ТИХУЮ порчу кириллицы, при этом `json.loads`
НЕ падает (нет исключения — только неверные символы). `_bridge_call`
(conftest.py) шлёт и сверяет канарейку на КАЖДОМ вызове; этот файл — явный,
именованный тест контракта + красная проба, доказывающая, что класс порчи
реален (не гипотетический риск). Третий тест (Б1, критик-раунд 2) — протокол
ПОРЯДКА проверок `_bridge_call`: ошибка ВНУТРИ харнесса обязана поднимать
`RuntimeError` с РЕАЛЬНЫМ `error`/`stack`, не тонуть за ложным
«канарейка не совпала»."""
from __future__ import annotations

import allure
import pytest


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-cyrillic-canary-round-trips-through-subprocess-protocol")
@allure.title("L2 bridge, канарейка протокола: кириллица round-trip через node-subprocess без порчи")
def test_cyrillic_canary_round_trips_through_subprocess_protocol(bridge_call):
    canary = "Проверка кириллицы, спецсимволы: ёЁйЙщЩ — N5 (docs/tasks/p2-pyramid-bridge.md)"
    response = bridge_call({
        "html": "<!DOCTYPE html><html><head></head><body></body></html>",
        "canary": canary,
    })
    assert response["canaryEcho"] == canary


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-cyrillic-canary-wrong-codec-silently-corrupts-red-probe")
@allure.title("L2 bridge, красная проба: неверная кодировка (cp1251) тихо портит кириллицу без исключения")
def test_wrong_codec_would_silently_corrupt_cyrillic_without_raising():
    """Красная проба (класс, не экземпляр, CLAUDE.md builder п.9): показывает,
    что декодирование UTF-8-байтов кириллицы НЕВЕРНОЙ кодировкой (cp1251 — та
    же локаль, что у venv-python подпроцесса, факт 6 recon) даёт РАЗНУЮ строку
    БЕЗ исключения — именно этот класс отказа и ловит канарейка `_bridge_call`
    (сравнением `canaryEcho`), а не try/except вокруг `json.loads`."""
    original = "проверка кириллицы N5"
    utf8_bytes = original.encode("utf-8")
    corrupted = utf8_bytes.decode("cp1251")
    assert corrupted != original  # тихая порча, не исключение


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-harness-error-surfaces-real-cause-not-canary-assertion")
@allure.title("L2 bridge, протокол: ошибка ВНУТРИ харнесса поднимается как RuntimeError с РЕАЛЬНОЙ причиной, не как ложная канарейка")
def test_harness_error_raises_runtime_error_with_real_cause_not_canary_mismatch(bridge_call):
    """Постоянный тест протокола (Б1, критик-раунд 2, `docs/tasks/
    p2-pyramid-bridge.md`, task_id `p2-n5-bridge-harness` accepted
    2026-08-19T11:42:52): ДО фикса `_bridge_call` проверяла канарейку ПЕРЕД
    `ok`, а ошибочный ответ харнесса не нёс `canaryEcho` -- ЛЮБАЯ ошибка внутри
    `run_bridge.js` (например, исключение в `action.type: "eval"`) поднималась
    как `AssertionError` «round-trip encoding сломан», реальные `error`/`stack`
    терялись. Эта проба заставляет харнесс бросить `Error('BOOM')` внутри
    `runRequest` (через `eval`-action) и доказывает: (1) поднимается
    `RuntimeError`, НЕ `AssertionError`; (2) текст исключения содержит 'BOOM'
    (реальную причину), не текст про канарейку."""
    with pytest.raises(RuntimeError) as exc_info:
        bridge_call({
            "html": "<!DOCTYPE html><html><head></head><body></body></html>",
            "actions": [
                {"id": "boom", "type": "eval", "code": "(function () { throw new Error('BOOM'); })()"},
            ],
        })
    assert not isinstance(exc_info.value, AssertionError)  # не спутана с канарейкой
    assert "BOOM" in str(exc_info.value)  # реальная причина видна, не проглочена
