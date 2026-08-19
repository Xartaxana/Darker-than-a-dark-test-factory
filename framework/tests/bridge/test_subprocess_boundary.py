"""Граница введённого лимита `DEFAULT_TIMEOUT_SEC`/subprocess-таймаут
(conftest.py, CLAUDE.md builder п.6а — «у каждого лимита тест НА границе и ЗА
ней»): НА границе — обычный вызов харнесса укладывается в дефолтный таймаут с
большим запасом (косвенно доказано КАЖДЫМ другим тестом этого пакета, все
используют дефолт без явного `timeout=`); ЗА границей — вызов с намеренно
маленьким таймаутом на действии, которое ГАРАНТИРОВАННО не завершится (`while
(true) {}` внутри `window.eval`, синхронный блокирующий JS в
однопоточном jsdom), обязан поднять `subprocess.TimeoutExpired`, а не
зависнуть навсегда."""
from __future__ import annotations

import subprocess

import allure
import pytest

from framework.data import recording_builder as rb
from framework.data.works import LOVED


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-subprocess-timeout-boundary-ordinary-call-within-default")
@allure.title("L2 bridge, граница M6 (НА границе): обычный вызов укладывается в таймаут с большим запасом")
def test_ordinary_call_completes_well_within_default_timeout(bridge_call):
    """НА границе: обычный вызов (badges/getWorkData-класс сложности) укладывается
    с большим запасом в дефолтный таймаут (явный `timeout=5.0` — на порядок
    меньше дефолта 30s, но щедрый над наблюдаемыми ~сотнями мс реального
    прогона)."""
    response = bridge_call(
        {
            "html": rb.render_listing_html([LOVED]),
            "url": "https://archiveofourown.org/works",
            "actions": [
                {"id": "count", "type": "eval", "code": "document.querySelectorAll('[data-ao3-btn-wrap]').length"},
            ],
        },
        timeout=5.0,
    )
    assert response["results"]["count"] == 1


@pytest.mark.bridge
@pytest.mark.p1
@allure.id("bridge-subprocess-timeout-boundary-hanging-action-beyond-timeout")
@allure.title("L2 bridge, граница M6 (ЗА границей): зависшее действие поднимает TimeoutExpired, не виснет")
def test_hanging_action_beyond_tiny_timeout_raises_timeout_expired(bridge_call_raw):
    """ЗА границей: `while (true) {}` в синхронном `window.eval` блокирует
    единственный поток node ГАРАНТИРОВАННО — с таймаутом 0.5s subprocess
    обязан упасть `TimeoutExpired` (и убить процесс, штатное поведение
    `subprocess.run(timeout=...)`), а не зависнуть до конца прогона."""
    with pytest.raises(subprocess.TimeoutExpired):
        bridge_call_raw(
            {
                "html": "<!DOCTYPE html><html><head></head><body></body></html>",
                "actions": [
                    {"id": "hang", "type": "eval", "code": "while (true) {}"},
                ],
            },
            timeout=0.5,
        )
