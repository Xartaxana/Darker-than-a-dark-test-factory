"""spec-p3-second-emulator N3: чокпоинт машинной лизы device-стека в
`driver_factory.create_driver` (B14 — на пути исполнения прогона,
function/driver-scoped) + дополнительная ранняя сверка в
`conftest.py::_ensure_app_installed` (B22/B26) + `pytest_runtest_setup`
(non-blocker 2, критик-вход rework attempt 2).

Device-free: `driver_factory._device_lease_file` монки-патчится на
`tmp_path`-based путь (тот же приём, что `isolated_state_file` в
`test_device_liveness_guard_unit.py` для `_EMULATOR_SESSION_STATE_FILE`) —
никакой реальный `state/device-lease-*.json` не трогается.

Матрица ТРЁХМЕРНАЯ (план N3): {активная|idle|reclaimed|отсутствующая} x
{стек 1|стек 2} x {свой|чужой владелец} — см. секции ниже, каждая проба
поименована по комбинации. Плюс B1/B5/B6/B7 (критик-вход rework attempt 2)
дополнение матрицы: мёртвый pid, /wd/hub-URL, рассинхрон device/url, битый
heartbeat+валидный taken.

B1 (критик-вход rework attempt 2): статус ТЕПЕРЬ по живости `pytest_pid`
(`driver_factory._is_pid_alive`), не по полю `status` файла — тесты,
симулирующие idle/active по pid, ЯВНО monkeypatch'ат `_is_pid_alive`
(детерминированно, не полагаясь на случайное несуществование фиксированного
PID на хосте, прогоняющем тесты — критик-требование "не на примитиве ОС")."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import allure
import pytest

from framework.config import settings
from framework.core import driver_factory

# Захват НАСТОЯЩЕЙ реализации ДО того, как autouse-фикстура `_default_pid_dead`
# подменит её моком: пробы блокера B-R2-2 обязаны опираться на РЕАЛЬНУЮ
# живость процесса (`monkeypatch.setattr(driver_factory, "_is_pid_alive",
# driver_factory._is_pid_alive)` внутри теста вернул бы УЖЕ ПОДМЕНЁННЫЙ мок —
# фикстуры отрабатывают раньше тела теста).
_REAL_IS_PID_ALIVE = driver_factory._is_pid_alive


@pytest.fixture(scope="session", autouse=True)
def _ensure_app_installed():
    """Переопределяет device-фикстуру conftest.py — эта проба чисто
    локальная, устройство не трогает (паттерн остальных *_unit.py)."""
    yield


@pytest.fixture(autouse=True)
def _isolated_lease_files(monkeypatch, tmp_path):
    """Отвязывает `_device_lease_file` от реального `state/` репозитория —
    КАЖДЫЙ тест получает свой tmp_path, реальные лизы не читаются/не
    пишутся."""
    def _fake_path(stack: int):
        return tmp_path / f"device-lease-{stack}.json"
    monkeypatch.setattr(driver_factory, "_device_lease_file", _fake_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_lease_env(monkeypatch):
    monkeypatch.delenv("AO3_DEVICE_LEASE_TOKEN", raising=False)
    yield
    # B-R2-1: адопция чокпоинтом ставит env-токен НАПРЯМУЮ (`os.environ[...]`,
    # не через monkeypatch — это продакшен-код), поэтому `delenv` выше его НЕ
    # откатит: снимаем явно, иначе токен протёк бы в соседние пробы сессии.
    os.environ.pop("AO3_DEVICE_LEASE_TOKEN", None)


@pytest.fixture(autouse=True)
def _default_pid_dead(monkeypatch):
    """B1: дефолт ЭТОГО файла — pid считается МЁРТВЫМ, если тест явно не
    просит живой (`_alive_pid`/`monkeypatch` ниже). Раньше тесты неявно
    полагались на то, что фиксированный `pytest_pid=999` СЛУЧАЙНО не
    существует на хосте прогона — детерминированный монки-патч убирает эту
    зависимость от среды (тот же класс, что PS-сторона закрыла явным
    `-PidAliveResolver`)."""
    monkeypatch.setattr(driver_factory, "_is_pid_alive", lambda pid: False)


def _alive_pid(monkeypatch) -> None:
    monkeypatch.setattr(driver_factory, "_is_pid_alive", lambda pid: True)


def _write_lease(tmp_path, stack: int, *, owner_token: str, owner_label: str = "owner@HOST",
                  heartbeat_offset_sec: float = 10, pytest_pid=None, status: str = "active",
                  now: datetime | None = None, heartbeat_literal=None, taken_offset_sec=None) -> None:
    now = now or datetime.now(timezone.utc)
    taken = now - timedelta(seconds=taken_offset_sec if taken_offset_sec is not None else heartbeat_offset_sec)
    hb = now - timedelta(seconds=heartbeat_offset_sec)
    payload = {
        "owner_token": owner_token, "owner_label": owner_label,
        "taken_utc": taken.isoformat(),
        "heartbeat_utc": heartbeat_literal if heartbeat_literal is not None else hb.isoformat(),
        "pytest_pid": pytest_pid, "status": status,
    }
    (tmp_path / f"device-lease-{stack}.json").write_text(json.dumps(payload), encoding="utf-8")


def _set_stack(monkeypatch, stack: int) -> None:
    """B5 (критик-вход rework attempt 2): `_detect_device_lease_stack`
    теперь сверяет ОБА сигнала (порт APPIUM_URL И DEVICE_NAME) - патчить
    ТОЛЬКО APPIUM_URL (как раньше, до B5) для стека 2 даёт РАССИНХРОН с
    `settings.DEVICE_NAME`, оставшимся на дефолте ('emulator-5554' -> стек
    1 по устройству), и ложно триггерит НОВЫЙ B5-отказ 'рассинхрон
    AO3_DEVICE' на КАЖДОЙ существующей стек-2 пробе этого файла (найдено
    именно в этой сессии - 9 тестов упали именно так после добавления B5-
    проверки). Оба сигнала патчатся СОГЛАСОВАННО здесь; отдельные B5-пробы
    ниже (`test_detect_stack_device_url_mismatch_explicit_refusal` и
    сиблинги) патчат их НЕСОГЛАСОВАННО НАРОЧНО, напрямую, в обход этого
    хелпера."""
    port = {1: 4723, 2: 4725}[stack]
    device = driver_factory._DEVICE_LEASE_STACK_DEVICES[stack]
    monkeypatch.setattr(settings, "APPIUM_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(settings, "DEVICE_NAME", device)
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", device)


# --- легаси/кастомный порт: чокпоинт полностью no-op ---

@pytest.mark.p1
@allure.id("P3-N3-lease-legacy-port-noop")
@allure.title("Незнакомый порт APPIUM_URL (легаси/кастомный вызов) - чокпоинт no-op, лиза не участвует (device-free)")
def test_legacy_unknown_port_checkpoint_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:9999")
    driver_factory.check_device_lease()  # не бросает, ничего не пишет
    assert list(tmp_path.iterdir()) == []


# --- стек 1: отказ ТОЛЬКО при конфликте с чужой АКТИВНОЙ лизой ---

@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-absent-proceeds")
@allure.title("Стек 1, лиза отсутствует - легальный дефолт, проходит без исключения (device-free)")
def test_stack1_absent_lease_proceeds(monkeypatch):
    _set_stack(monkeypatch, 1)
    driver_factory.check_device_lease()  # не бросает


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-active-own-heartbeats")
@allure.title("Стек 1, своя активная лиза (живой pid, B1) - heartbeat/pytest_pid обновляются (device-free)")
def test_stack1_active_own_heartbeats(monkeypatch, tmp_path):
    # B-R4-2: легитимный «свой активный» = pid СВОЕГО процесса (повторный
    # create_driver того же прогона). Чужой живой pid под своим токеном
    # теперь отказ — см. test_stack1_active_own_token_but_foreign_live_pid_blocks.
    _set_stack(monkeypatch, 1)
    _alive_pid(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    _write_lease(tmp_path, 1, owner_token="MY-TOKEN", heartbeat_offset_sec=5,
                 pytest_pid=driver_factory.os.getpid())
    driver_factory.check_device_lease()
    data = json.loads((tmp_path / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == driver_factory.os.getpid()
    assert data["status"] == "active"
    # B5: device/appium_url теперь тоже записаны диагностическим следом
    assert data["device"] == settings.DEVICE_NAME
    assert data["appium_url"] == "http://127.0.0.1:4723"


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-active-foreign-blocks")
@allure.title("Стек 1, чужая АКТИВНАЯ лиза (живой pid) - DeviceLeaseError, DEVICE_LEASE_BLOCKED, имя владельца (device-free)")
def test_stack1_active_foreign_blocks(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 1)
    _alive_pid(monkeypatch)
    _write_lease(tmp_path, 1, owner_token="OTHER", owner_label="other@HOST", heartbeat_offset_sec=5, pytest_pid=4242)
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "other@HOST" in message
    assert "стек 1" in message


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-idle-own-returns-to-active")
@allure.title("Стек 1, своя idle-лиза (B28, мёртвый pid - B1) - принимается, возвращается в active, ТОТ ЖЕ owner_token (device-free)")
def test_stack1_idle_own_returns_to_active(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 1)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    # дефолтный фикстур-монки-патч _default_pid_dead -> pid мёртв, age (100с)
    # > grace(600с)? нет, < grace... нужно ЗА grace, чтобы не остаться "active"
    # без pid: age > grace(600) обязателен для idle без живого pid.
    _write_lease(tmp_path, 1, owner_token="MY-TOKEN", heartbeat_offset_sec=700, pytest_pid=999, status="idle")
    driver_factory.check_device_lease()
    data = json.loads((tmp_path / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["status"] == "active"
    assert data["owner_token"] == "MY-TOKEN"
    assert data["pytest_pid"] == driver_factory.os.getpid()


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-idle-foreign-proceeds-without-touching")
@allure.title("Стек 1, чужая idle-лиза (мёртвый pid) - легальный дефолт (НЕ active-конфликт), проходит, файл НЕ тронут (device-free)")
def test_stack1_idle_foreign_proceeds_without_touching(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 1)
    _write_lease(tmp_path, 1, owner_token="OTHER", owner_label="other@HOST",
                 heartbeat_offset_sec=700, pytest_pid=999, status="idle")
    before = (tmp_path / "device-lease-1.json").read_text(encoding="utf-8")
    driver_factory.check_device_lease()  # не бросает
    after = (tmp_path / "device-lease-1.json").read_text(encoding="utf-8")
    assert before == after  # чужая лиза НЕ украдена/не тронута


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-reclaimed-proceeds")
@allure.title("Стек 1, истёкшая (reclaimed) лиза - проходит как легальный дефолт (device-free)")
def test_stack1_reclaimed_proceeds(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 1)
    _write_lease(tmp_path, 1, owner_token="STALE", heartbeat_offset_sec=20000)  # >> TTL 4h, >> idle 30min
    driver_factory.check_device_lease()  # не бросает


# --- стек 2: лиза БЕЗУСЛОВНА (асимметричный дефолт B27/B18) ---

@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-absent-blocks")
@allure.title("Стек 2, лиза отсутствует - DeviceLeaseInvalidStackError, DEVICE_LEASE_BLOCKED (device-free)")
def test_stack2_absent_lease_blocks(monkeypatch):
    _set_stack(monkeypatch, 2)
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "Use-DeviceStack -N 2" in message


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-reclaimed-blocks")
@allure.title("Стек 2, истёкшая (reclaimed) лиза - тот же безусловный отказ, что 'нет лизы вовсе' (device-free)")
def test_stack2_reclaimed_blocks(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _write_lease(tmp_path, 2, owner_token="STALE", heartbeat_offset_sec=20000)
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError):
        driver_factory.check_device_lease()


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-active-own-heartbeats")
@allure.title("Стек 2, своя активная лиза (живой pid) - heartbeat/pytest_pid обновляются, прогон проходит (device-free)")
def test_stack2_active_own_heartbeats(monkeypatch, tmp_path):
    # B-R4-2: см. комментарий в test_stack1_active_own_heartbeats.
    _set_stack(monkeypatch, 2)
    _alive_pid(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    _write_lease(tmp_path, 2, owner_token="MY-TOKEN", heartbeat_offset_sec=5,
                 pytest_pid=driver_factory.os.getpid())
    driver_factory.check_device_lease()
    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == driver_factory.os.getpid()


@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-own-token-foreign-live-pid-blocks")
@allure.title("Стек 1, СВОЙ токен, но под лизой ЖИВОЙ чужой pytest_pid - отказ B-R4-2, pid не затёрт (device-free)")
def test_stack1_active_own_token_but_foreign_live_pid_blocks(monkeypatch, tmp_path):
    """B-R4-2 (критик-раунд 4): унаследованный env-токен НЕ легализует второй
    одновременный прогон — токенная ветка обязана проверять живость pid тем же
    предикатом, что адопция. До фикса: PASSED + pid живого прогона затирался."""
    _set_stack(monkeypatch, 1)
    _alive_pid(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    _write_lease(tmp_path, 1, owner_token="MY-TOKEN", heartbeat_offset_sec=5, pytest_pid=4242)
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "B-R4-2" in message and "4242" in message
    data = json.loads((tmp_path / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == 4242, "pid живого прогона затёрт отказавшим чокпоинтом"


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-own-token-foreign-live-pid-blocks")
@allure.title("Стек 2, СВОЙ токен, но под лизой ЖИВОЙ чужой pytest_pid - отказ B-R4-2, pid не затёрт (device-free)")
def test_stack2_active_own_token_but_foreign_live_pid_blocks(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _alive_pid(monkeypatch)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    _write_lease(tmp_path, 2, owner_token="MY-TOKEN", heartbeat_offset_sec=5, pytest_pid=4242)
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    assert "B-R4-2" in str(exc_info.value)
    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == 4242


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-active-foreign-blocks-no-wait")
@allure.title("Стек 2, чужая АКТИВНАЯ лиза (живой pid) - DeviceLeaseError 'ждать нечего', имя владельца (device-free)")
def test_stack2_active_foreign_blocks(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _alive_pid(monkeypatch)
    _write_lease(tmp_path, 2, owner_token="OTHER", owner_label="other@HOST", heartbeat_offset_sec=5, pytest_pid=4242)
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "other@HOST" in message
    assert "ждать нечего" in message


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-idle-own-returns-to-active")
@allure.title("Стек 2, своя idle-лиза (мёртвый pid, B28) - принимается, возвращается в active (device-free)")
def test_stack2_idle_own_returns_to_active(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    monkeypatch.setenv("AO3_DEVICE_LEASE_TOKEN", "MY-TOKEN")
    _write_lease(tmp_path, 2, owner_token="MY-TOKEN", heartbeat_offset_sec=700, pytest_pid=999, status="idle")
    driver_factory.check_device_lease()
    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["status"] == "active"
    assert data["owner_token"] == "MY-TOKEN"


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-idle-foreign-blocks-with-wait-hint")
@allure.title("Стек 2, чужая idle-лиза (мёртвый pid) - DeviceLeaseError с 'жди до <момент>', не тихое ожидание (device-free)")
def test_stack2_idle_foreign_blocks_with_wait_hint(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _write_lease(tmp_path, 2, owner_token="OTHER", owner_label="other@HOST",
                 heartbeat_offset_sec=700, pytest_pid=999, status="idle")
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "other@HOST" in message
    assert "жди до" in message


# --- B1 (критик-вход rework attempt 2): мёртвый pid при heartbeat в пределах TTL ---

@pytest.mark.p1
@allure.id("P3-N3-lease-stack1-dead-pid-recent-heartbeat-is-idle-not-active")
@allure.title("Стек 1, СВЕЖИЙ heartbeat но МЁРТВЫЙ pid - idle (НЕ active по одному лишь свежему heartbeat, B1) (device-free)")
def test_stack1_dead_pid_recent_heartbeat_is_idle_not_active(monkeypatch, tmp_path):
    """Раньше живость pytest_pid не проверялась вовсе -- свежий heartbeat сам
    по себе означал active. B1-редизайн: мёртвый pid (даже со свежим
    heartbeat, age << grace) НЕ active, а idle (own -> принимается, но
    отдельно проверяется явный отказ ниже для чужого случая)."""
    _set_stack(monkeypatch, 1)
    _write_lease(tmp_path, 1, owner_token="OTHER", owner_label="other@HOST",
                 heartbeat_offset_sec=5, pytest_pid=4242, status="active")
    # мёртвый pid -> idle (не active) -> чужой idle это НЕ active-конфликт,
    # стек 1 легально проходит БЕЗ throw (см. test_stack1_idle_foreign_
    # proceeds_without_touching) - но КЛЮЧЕВАЯ проверка здесь: НЕ throw как
    # "active foreign" (что случилось бы на СТАРОМ поведении).
    driver_factory.check_device_lease()  # НЕ throw DeviceLeaseError("ждать нечего")


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-dead-pid-recent-heartbeat-foreign-idle-not-active-block")
@allure.title("Стек 2, чужая лиза со свежим heartbeat но МЁРТВЫМ pid - idle-отказ ('жди до'), НЕ active-отказ ('ждать нечего') (device-free)")
def test_stack2_dead_pid_recent_heartbeat_is_idle_block_message(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _write_lease(tmp_path, 2, owner_token="OTHER", owner_label="other@HOST",
                 heartbeat_offset_sec=5, pytest_pid=4242, status="active")
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory.check_device_lease()
    message = str(exc_info.value)
    assert "жди до" in message  # idle-класс сообщения
    assert "ждать нечего" not in message  # НЕ active-класс сообщения


# --- адверсариальная батарея: битый JSON / отсутствующий timestamp / пустой файл ---

@pytest.mark.p1
@allure.id("P3-N3-lease-corrupted-json-treated-as-absent-stack2-blocks")
@allure.title("Битый JSON лизы - трактуется как отсутствующая; стек 2 отказывает (device-free)")
def test_corrupted_lease_json_stack2_blocks(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    (tmp_path / "device-lease-2.json").write_text("{ not valid json !!!", encoding="utf-8")
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError):
        driver_factory.check_device_lease()


@pytest.mark.p1
@allure.id("P3-N3-lease-corrupted-json-treated-as-absent-stack1-proceeds")
@allure.title("Битый JSON лизы - трактуется как отсутствующая; стек 1 проходит (device-free)")
def test_corrupted_lease_json_stack1_proceeds(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 1)
    (tmp_path / "device-lease-1.json").write_text("{ not valid json !!!", encoding="utf-8")
    driver_factory.check_device_lease()  # не бросает


@pytest.mark.p1
@allure.id("P3-N3-lease-empty-zero-byte-file-treated-as-absent-stack2-blocks")
@allure.title("B6: пустой (0-байтный) файл лизы - трактуется как отсутствующая (не как 'лиза без данных'); стек 2 отказывает (device-free)")
def test_empty_zero_byte_lease_file_stack2_blocks(monkeypatch, tmp_path):
    """Python-сторона `_read_device_lease`: `json.loads("")` кидает
    `ValueError` (пустая строка - невалидный JSON), уже перехваченный веткой
    `except ValueError` -> `return None` - тот же результат, что PS-сторона
    ТЕПЕРЬ даёт явной проверкой `IsNullOrEmpty` (B6). Регрессионный тест на
    пустой файл КОНКРЕТНО (не только "битый JSON" с непустым содержимым)."""
    _set_stack(monkeypatch, 2)
    (tmp_path / "device-lease-2.json").write_bytes(b"")
    assert (tmp_path / "device-lease-2.json").stat().st_size == 0
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError):
        driver_factory.check_device_lease()


@pytest.mark.p1
@allure.id("P3-N3-lease-missing-timestamp-is-free")
@allure.title("Лиза без timestamp'ов (defensive) - трактуется как free/отсутствующая (device-free)")
def test_lease_missing_timestamps_is_free():
    now = datetime.now(timezone.utc)
    assert driver_factory._lease_status({"owner_token": "X"}, now) == "free"


# --- B7 (критик-вход rework attempt 2): битый heartbeat_utc + валидный taken_utc ---

@pytest.mark.p1
@allure.id("P3-N3-lease-corrupted-heartbeat-falls-back-to-valid-taken-utc")
@allure.title("B7: битый heartbeat_utc + валидный taken_utc - фолбэк на taken_utc, СТАТУС ПО НЕМУ (не 'free' от одного лишь битого поля) (device-free)")
def test_lease_corrupted_heartbeat_falls_back_to_valid_taken_utc():
    """B7 (критик-вход rework attempt 2): расхождение реализаций - Python
    ВСЕГДА фолбэчился на taken_utc через `or`-цепочку
    (`_parse_lease_timestamp(heartbeat_utc) or _parse_lease_timestamp(taken_utc)`),
    PS-сторона раньше уходила в `catch -> free` на битом heartbeat, ИГНОРИРУЯ
    валидный taken_utc целиком. Эта проба - явный вход из блокера в ОБЕИХ
    юнит-матрицах (зеркало `test_corrupted_heartbeat_falls_back_to_valid_
    taken_utc` в `scripts/tests/test_p3_device_lease_status.py`), закрепляет,
    что Python-сторона УЖЕ была верна и остаётся верна после рефакторинга B1."""
    now = datetime.now(timezone.utc)
    taken = now - timedelta(seconds=5)
    status = driver_factory._lease_status(
        {
            "owner_token": "X", "heartbeat_utc": "NOT-A-VALID-TIMESTAMP",
            "taken_utc": taken.isoformat(), "pytest_pid": None,
        },
        now,
    )
    assert status == "active"  # age~5s <= grace(600s), pid отсутствует


# --- B1: чистая матрица `_lease_status` (мёртвый/живой pid x grace/idle/ttl границы) ---

@pytest.mark.p1
@allure.id("P3-N3-lease-status-pid-alive-within-ttl-is-active")
@allure.title("_lease_status: pid жив, age<=TTL - active (device-free)")
def test_lease_status_pid_alive_within_ttl_is_active():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=100)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": 4242},
        now, pid_alive_fn=lambda pid: True,
    )
    assert status == "active"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-pid-alive-beyond-ttl-falls-through")
@allure.title("_lease_status: pid жив, но age>TTL - НЕ active (падает в idle/reclaimed по age) (device-free)")
def test_lease_status_pid_alive_beyond_ttl_falls_through_to_reclaimed():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=20000)  # >> TTL(14400) и >> idle(1800)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": 4242},
        now, pid_alive_fn=lambda pid: True,
    )
    assert status == "reclaimed"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-no-pid-within-grace-is-active")
@allure.title("_lease_status: pid отсутствует, age<=grace(600с) - active (короткое стартовое окно) (device-free)")
def test_lease_status_no_pid_within_grace_is_active():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=100)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": None}, now,
    )
    assert status == "active"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-no-pid-beyond-grace-is-idle-not-reclaimed")
@allure.title("_lease_status: pid отсутствует, age>grace НО age<=idle - idle (B1-редизайн, НЕ прямиком reclaimed) (device-free)")
def test_lease_status_no_pid_beyond_grace_is_idle_not_reclaimed():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=700)  # > grace(600), <= idle(1800)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": None}, now,
    )
    assert status == "idle"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-dead-pid-within-idle-window-is-idle")
@allure.title("_lease_status: pid МЁРТВ, age<=idle(1800с) - idle (device-free)")
def test_lease_status_dead_pid_within_idle_window_is_idle():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=1000)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": 4242},
        now, pid_alive_fn=lambda pid: False,
    )
    assert status == "idle"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-dead-pid-beyond-idle-window-is-reclaimed")
@allure.title("_lease_status: pid МЁРТВ, age>idle(1800с) - reclaimed (device-free)")
def test_lease_status_dead_pid_beyond_idle_window_is_reclaimed():
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=1900)
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": 4242},
        now, pid_alive_fn=lambda pid: False,
    )
    assert status == "reclaimed"


@pytest.mark.p1
@allure.id("P3-N3-lease-status-default-pid-alive-fn-uses-real-is-pid-alive")
@allure.title("_lease_status без явного pid_alive_fn - использует РЕАЛЬНЫЙ _is_pid_alive (device-free, детерминированный негативный контроль)")
def test_lease_status_default_pid_alive_fn_uses_real_is_pid_alive():
    """Негативный контроль БЕЗ мока: заведомо неправдоподобный PID
    (999999999) - `driver_factory._is_pid_alive` (реальная, НЕ
    monkeypatch'нутая функция - см. явный `pid_alive_fn=driver_factory.
    _is_pid_alive` ниже, обходящий autouse-фикстуру `_default_pid_dead`
    этого файла) обязана вернуть False детерминированно на любом хосте."""
    now = datetime.now(timezone.utc)
    hb = now - timedelta(seconds=5)  # << grace, было бы "active" будь pid жив
    status = driver_factory._lease_status(
        {"heartbeat_utc": hb.isoformat(), "taken_utc": hb.isoformat(), "pytest_pid": 999999999},
        now, pid_alive_fn=driver_factory._is_pid_alive,
    )
    assert status == "idle"  # мёртвый pid, age(5s) <= idle(1800s)


# --- B5 (критик-вход rework attempt 2): /wd/hub-URL + рассинхрон device/url ---

@pytest.mark.p1
@allure.id("P3-N3-detect-stack-wd-hub-url-suffix-still-detected")
@allure.title("B5: APPIUM_URL с /wd/hub-хвостом ('http://127.0.0.1:4725/wd/hub') - стек 2 ВСЁ РАВНО определяется (urlparse, не .endswith) (device-free)")
def test_detect_stack_with_wd_hub_url_suffix(monkeypatch):
    """Раньше `.endswith(f':{port}')` молча возвращал None на ЛЮБОМ хвосте
    пути после порта -> стек 2 проходил чокпоинт БЕЗ ЛИЗЫ ВООБЩЕ (дыра в
    асимметричном B27-дефолте). urlparse(...).port устойчив к хвосту."""
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4725/wd/hub")
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", "emulator-5556", raising=False)
    assert driver_factory._detect_device_lease_stack() == 2


@pytest.mark.p1
@allure.id("P3-N3-detect-stack-wd-hub-url-without-lease-still-blocks-stack2")
@allure.title("B5 регресс: /wd/hub-URL стека 2 БЕЗ лизы - ТЕПЕРЬ отказывает (раньше молча проходил, дыра в B27) (device-free)")
def test_wd_hub_url_without_lease_blocks_stack2(monkeypatch, tmp_path):
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4725/wd/hub")
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", "emulator-5556", raising=False)
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError):
        driver_factory.check_device_lease()


@pytest.mark.p1
@allure.id("P3-N3-detect-stack-device-url-mismatch-explicit-refusal")
@allure.title("B5: AO3_DEVICE называет один стек, APPIUM_URL - другой - явный DeviceLeaseError-отказ, чокпоинт не угадывает (device-free)")
def test_detect_stack_device_url_mismatch_explicit_refusal(monkeypatch):
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4723")  # стек 1 по порту
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", "emulator-5556", raising=False)  # стек 2 по устройству
    with pytest.raises(driver_factory.DeviceLeaseError) as exc_info:
        driver_factory._detect_device_lease_stack()
    message = str(exc_info.value)
    assert message.startswith("DEVICE_LEASE_BLOCKED")
    assert "рассинхрон AO3_DEVICE" in message


@pytest.mark.p1
@allure.id("P3-N3-detect-stack-device-url-agree-no-mismatch")
@allure.title("B5 контрольная проба: AO3_DEVICE и APPIUM_URL называют ОДИН И ТОТ ЖЕ стек - НЕ отказ (device-free)")
def test_detect_stack_device_url_agree_no_mismatch(monkeypatch):
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4725")
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", "emulator-5556", raising=False)
    assert driver_factory._detect_device_lease_stack() == 2


@pytest.mark.p1
@allure.id("P3-N3-detect-stack-unknown-device-known-port-uses-port")
@allure.title("B5: незнакомое DEVICE_NAME, но знакомый порт - использует порт (back-compat, не отказ) (device-free)")
def test_detect_stack_unknown_device_known_port_uses_port(monkeypatch):
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4723")
    monkeypatch.setattr(driver_factory.settings, "DEVICE_NAME", "some-other-unrelated-device", raising=False)
    assert driver_factory._detect_device_lease_stack() == 1


# --- create_driver зовёт чокпоинт ПЕРВОЙ строкой ---

@pytest.mark.p1
@allure.id("P3-N3-create-driver-calls-lease-checkpoint-first")
@allure.title("create_driver вызывает check_device_lease() ДО попытки создать сессию (device-free)")
def test_create_driver_calls_lease_checkpoint_before_session(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(driver_factory, "check_device_lease", lambda: calls.append("lease"))

    def _boom(*a, **kw):
        calls.append("build_options")
        raise RuntimeError("stop here - proves ordering, session never actually created")

    monkeypatch.setattr(driver_factory.capabilities, "build_options", _boom)

    with pytest.raises(RuntimeError):
        driver_factory.create_driver(no_reset=True, settle_retries=0)

    assert calls == ["lease", "build_options"]


@pytest.mark.p1
@allure.id("P3-N3-create-driver-lease-blocked-propagates-before-any-attempt")
@allure.title("create_driver: лиза блокирует - DeviceLeaseError долетает наружу, build_options НЕ вызван (device-free)")
def test_create_driver_lease_error_propagates_without_attempt(monkeypatch):
    def _raise_lease_error():
        raise driver_factory.DeviceLeaseError("DEVICE_LEASE_BLOCKED (test)")

    monkeypatch.setattr(driver_factory, "check_device_lease", _raise_lease_error)
    build_calls: list = []
    monkeypatch.setattr(driver_factory.capabilities, "build_options", lambda **kw: build_calls.append(1))

    with pytest.raises(driver_factory.DeviceLeaseError):
        driver_factory.create_driver(no_reset=True, settle_retries=0)

    assert build_calls == []


# --- conftest.py: ранняя сверка session-фикстуры ---
#
# ПРИМЕЧАНИЕ (не расширяю scope, D-0043-репорт): `_ensure_app_installed`
# декорирована `@pytest.fixture` и звать её напрямую (даже через
# `.__wrapped__`) нельзя без риска — pytest 9 намеренно ломает прямой вызов
# fixture-функций (см. докстринг `_ensure_no_residual_device_proxy` в
# conftest.py: "pytest 9 запрещает прямой вызов декорированной fixture-
# функции"), и именно ПОЭТОМУ её сиблинги (`_ensure_no_residual_device_
# proxy`/`_ensure_default_font_scale`/`_ensure_default_night_mode`) вынесены
# в отдельные ЧИСТЫЕ функции, тестируемые напрямую. `_ensure_app_installed`
# сама таким твином НЕ обзавелась (её тело инлайновое) уже ДО этой задачи —
# N3 добавила туда только одну строку (`check_device_lease()` первой), не
# меняя эту структуру (вне owns/DoD спеки). Поэтому здесь — статическая
# (source-level) проверка порядка вызовов, а не рантайм-вызов фикстуры;
# рантайм-путь уже покрыт `test_create_driver_calls_lease_checkpoint_first`
# (авторитетная точка) выше. Дефект-класс (не рефакторю сам, только
# докладываю): `_ensure_app_installed` — единственная session-autouse
# фикстура conftest.py БЕЗ чистого твина, поэтому единственная в файле, что
# не тестируется рантайм-вызовом — то же наблюдение стоит сверить на
# аналогичных фикстурах при следующей структурной правке conftest.py.

@pytest.mark.p1
@allure.id("P3-N3-conftest-early-lease-check-runs-first-source-order")
@allure.title("conftest._ensure_app_installed: check_device_lease() - ПЕРВЫЙ вызов в теле фикстуры, до adb-путей (static/source, device-free)")
def test_conftest_early_lease_check_is_first_statement_in_source():
    import inspect
    import framework.tests.conftest as _conftest_mod

    src = inspect.getsource(_conftest_mod._ensure_app_installed)
    # тело после докстринга: первая исполняемая строка обязана быть
    # check_device_lease() - раньше _ensure_no_residual_device_proxy()/
    # font_scale/night_mode/is_installed (adb) - индекс подстрок в исходнике
    # функции однозначно фиксирует порядок появления вызовов.
    lease_idx = src.index("driver_factory.check_device_lease()")
    proxy_idx = src.index("_ensure_no_residual_device_proxy()")
    font_idx = src.index("_ensure_default_font_scale()")
    night_idx = src.index("_ensure_default_night_mode()")
    installed_idx = src.index("adb.is_installed()")

    assert lease_idx < proxy_idx < font_idx < night_idx < installed_idx


@pytest.mark.p1
@allure.id("P3-N3-conftest-pytest-runtest-setup-lease-check-before-ensure-ready-source-order")
@allure.title("Non-blocker 2: conftest.pytest_runtest_setup - check_device_lease() ДО ensure_ready() (static/source, device-free)")
def test_conftest_pytest_runtest_setup_lease_check_before_ensure_ready_source_order():
    """Non-blocker 2 (критик-вход rework attempt 2): `pytest_runtest_setup`
    зовёт `driver_factory.check_device_lease()` РАНЬШЕ `_DEVICE_GUARD.
    ensure_ready()` - тот же приём статической (source-order) проверки, что
    сосед выше (`test_conftest_early_lease_check_is_first_statement_in_
    source`), по той же причине (хук не годится звать напрямую в рамках
    device-free юнита - `item` пришлось бы полноценно мокать, а порядок ДВУХ
    КОНКРЕТНЫХ вызовов внутри тела функции - как раз то, что source-order
    надёжно фиксирует)."""
    import inspect
    import framework.tests.conftest as _conftest_mod

    src = inspect.getsource(_conftest_mod.pytest_runtest_setup)
    lease_idx = src.index("driver_factory.check_device_lease()")
    ensure_ready_idx = src.index("_DEVICE_GUARD.ensure_ready()")
    assert lease_idx < ensure_ready_idx


# =====================================================================
# БЛОКЕР B-R2-1/B-R2-2 (критик-раунд 2): АДОПЦИЯ ЧОКПОИНТОМ
# =====================================================================
# Связка, которую воспроизвёл критик: `Use-DeviceStack` исполняется в
# ОДНОРАЗОВОМ powershell-процессе А, а pytest живёт в процессе Б -
# `$env:AO3_DEVICE_LEASE_TOKEN` в Б НЕ наследуется, и лиза, взятая секунду
# назад тем же человеком на той же машине для того же устройства, читалась
# чокпоинтом как "чужая АКТИВНАЯ" -> DeviceLeaseError. Ниже - матрица
# адопции: разрешена (метка+устройство+URL совпали, живого pid нет) и
# ЗАПРЕЩЕНА (любое несовпадение / ЖИВОЙ чужой pid).

def _write_adoptable_lease(tmp_path, stack: int, *, owner_token: str = "TICKET-FROM-POWERSHELL",
                           owner_label=None, device=None, appium_url=None,
                           pytest_pid=None, heartbeat_offset_sec: float = 10) -> dict:
    """Лиза в том виде, в каком её пишет `tasks.ps1::Use-DeviceStack` ПОСЛЕ
    взятия: `pytest_pid: null` (pytest ещё не стартовал), `device`/
    `appium_url` заполнены (B5-след)."""
    now = datetime.now(timezone.utc)
    payload = {
        "owner_token": owner_token,
        "owner_label": owner_label if owner_label is not None else driver_factory._current_owner_label(),
        "taken_utc": (now - timedelta(seconds=heartbeat_offset_sec)).isoformat(),
        "heartbeat_utc": (now - timedelta(seconds=heartbeat_offset_sec)).isoformat(),
        "pytest_pid": pytest_pid,
        "status": "active",
        "device": device if device is not None else driver_factory._DEVICE_LEASE_STACK_DEVICES[stack],
        "appium_url": appium_url if appium_url is not None else f"http://127.0.0.1:{ {1: 4723, 2: 4725}[stack] }",
    }
    (tmp_path / f"device-lease-{stack}.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


@pytest.fixture
def live_stub_pid():
    """НАСТОЯЩИЙ живой процесс в роли `pytest_pid` (блокер B-R2-2): гейт
    "живой прогон -> отказ" проверяется РЕАЛЬНОЙ живостью (`_is_pid_alive`
    НЕ монки-патчится), а не тем, что мы сами сказали моку."""
    import subprocess
    import sys as _sys
    proc = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=30)


@pytest.mark.p1
@pytest.mark.parametrize("stack", [1, 2])
@allure.id("P3-N3-lease-adoption-by-owner-label-cross-process")
@allure.title("B-R2-1: лиза взята другим процессом (env-токена нет) - чокпоинт АДОПТИРУЕТ её, штампует свой PID (device-free)")
def test_checkpoint_adopts_own_lease_without_env_token(monkeypatch, tmp_path, stack):
    """Ядро блокера: env-токен ОТСУТСТВУЕТ (как у pytest, запущенного отдельно
    от powershell-процесса взятия), owner_label/device/appium_url совпадают,
    `pytest_pid` пуст -> НЕ отказ, а адопция + heartbeat со своим PID."""
    _set_stack(monkeypatch, stack)
    _write_adoptable_lease(tmp_path, stack)

    driver_factory.check_device_lease()  # НЕ бросает

    data = json.loads((tmp_path / f"device-lease-{stack}.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == os.getpid(), "адопция обязана заштамповать PID ЭТОГО процесса"
    assert data["owner_token"] == "TICKET-FROM-POWERSHELL", "токен тикета не меняется чокпоинтом"
    assert data["status"] == "active"
    # env-токен проставлен - следующий create_driver идёт быстрым путём is_own
    assert os.environ.get("AO3_DEVICE_LEASE_TOKEN") == "TICKET-FROM-POWERSHELL"


@pytest.mark.p1
@allure.id("P3-N3-lease-adoption-idempotent-second-create-driver")
@allure.title("B-R2-1: ВТОРОЙ чокпоинт того же процесса не отказывает сам себе (свой ЖИВОЙ pid - не 'чужой прогон')")
def test_checkpoint_adoption_is_idempotent_for_same_process(monkeypatch, tmp_path):
    """Регрессия на самоблокировку: после первой адопции `pytest_pid` = НАШ
    (заведомо ЖИВОЙ) pid. Без ветки "pid == os.getpid()" второй
    `create_driver` увидел бы живой pid и отказал бы прогону, который сам же
    и штампует. `_is_pid_alive` НЕ патчим - наш pid жив по-настоящему."""
    _set_stack(monkeypatch, 1)
    monkeypatch.setattr(driver_factory, "_is_pid_alive", _REAL_IS_PID_ALIVE)
    _write_adoptable_lease(tmp_path, 1)

    driver_factory.check_device_lease()
    monkeypatch.delenv("AO3_DEVICE_LEASE_TOKEN", raising=False)  # худший случай: env потерян
    driver_factory.check_device_lease()  # не бросает

    data = json.loads((tmp_path / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == os.getpid()


@pytest.mark.p1
@allure.id("P3-N3-lease-adoption-wd-hub-url-form")
@allure.title("B-R2-1: APPIUM_URL с хвостом /wd/hub - тот же сервер, адопция проходит (сверка по хосту+порту)")
def test_checkpoint_adoption_tolerates_wd_hub_url_form(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    monkeypatch.setattr(driver_factory.settings, "APPIUM_URL", "http://127.0.0.1:4725/wd/hub")
    _write_adoptable_lease(tmp_path, 2, appium_url="http://127.0.0.1:4725")

    driver_factory.check_device_lease()

    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == os.getpid()


@pytest.mark.p1
@allure.id("P3-N3-lease-adoption-refused-device-mismatch")
@allure.title("B-R2-2: device лизы НЕ совпадает с settings.DEVICE_NAME - адопция запрещена, прежний отказ (device-free)")
def test_checkpoint_adoption_refused_on_device_mismatch(monkeypatch, tmp_path):
    """Сверка device/appium_url — обязательная часть адопции: лиза, взятая
    для ДРУГОГО устройства, не наша, сколько бы ни совпадал owner_label."""
    _set_stack(monkeypatch, 2)
    _write_adoptable_lease(tmp_path, 2, device="emulator-9999")

    with pytest.raises(driver_factory.DeviceLeaseError) as exc:
        driver_factory.check_device_lease()
    assert "DEVICE_LEASE_BLOCKED" in str(exc.value)
    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] is None, "отказавшая адопция НИЧЕГО не пишет в чужую лизу"


@pytest.mark.p1
@allure.id("P3-N3-lease-adoption-refused-appium-url-mismatch")
@allure.title("B-R2-2: appium_url лизы указывает на ДРУГОЙ порт - адопция запрещена (device-free)")
def test_checkpoint_adoption_refused_on_appium_url_mismatch(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    _write_adoptable_lease(tmp_path, 2, appium_url="http://127.0.0.1:4799")

    with pytest.raises(driver_factory.DeviceLeaseError):
        driver_factory.check_device_lease()


@pytest.mark.p1
@allure.id("P3-N3-lease-adoption-refused-live-foreign-pid")
@allure.title("B-R2-2: под лизой ЖИВОЙ pytest_pid (настоящий процесс) - адопция запрещена ВСЕГДА")
def test_checkpoint_adoption_refused_over_live_pytest_pid(monkeypatch, tmp_path, live_stub_pid):
    """Жёсткий гейт блокера B-R2-2: `_is_pid_alive` НЕ патчится - живость
    настоящего подпроцесса-заглушки решает. Даже при полном совпадении
    owner_label/device/appium_url адопция запрещена: под лизой идёт
    настоящий прогон."""
    _set_stack(monkeypatch, 2)
    monkeypatch.setattr(driver_factory, "_is_pid_alive", _REAL_IS_PID_ALIVE)
    _write_adoptable_lease(tmp_path, 2, pytest_pid=live_stub_pid)

    with pytest.raises(driver_factory.DeviceLeaseError) as exc:
        driver_factory.check_device_lease()
    assert "DEVICE_LEASE_BLOCKED" in str(exc.value)
    data = json.loads((tmp_path / "device-lease-2.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == live_stub_pid, "лиза живого прогона НЕ перехвачена"


# --- non-blocker 3: не-числовой pytest_pid ---

@pytest.mark.p1
@pytest.mark.parametrize("bad_pid", ["не-число", True, [1, 2], {"a": 1}, "", 0, -5])
@allure.id("P3-N3-lease-non-numeric-pytest-pid-is-absent")
@allure.title("Non-blocker 3: не-числовой pytest_pid = 'pid отсутствует', НЕ TypeError посреди чокпоинта")
def test_non_numeric_pytest_pid_treated_as_absent(monkeypatch, tmp_path, bad_pid):
    """Раньше `pid <= 0` на строке падал `TypeError` ПОСРЕДИ чокпоинта и
    заклинивал прогон до ручного `-Release`. Теперь не-число = отсутствует ->
    лиза своя, живого прогона нет -> штатная адопция."""
    assert driver_factory._coerce_lease_pid(bad_pid) is None
    assert driver_factory._is_pid_alive(bad_pid) is False
    _set_stack(monkeypatch, 1)
    monkeypatch.setattr(driver_factory, "_is_pid_alive", _REAL_IS_PID_ALIVE)
    _write_adoptable_lease(tmp_path, 1, pytest_pid=bad_pid)

    driver_factory.check_device_lease()  # не бросает, не TypeError

    data = json.loads((tmp_path / "device-lease-1.json").read_text(encoding="utf-8"))
    assert data["pytest_pid"] == os.getpid()


@pytest.mark.p1
@allure.id("P3-N3-lease-coerce-pid-boundaries")
@allure.title("Non-blocker 3 (M6): границы нормализации pid - 0/-1/'' -> None, '123'/123 -> 123")
def test_coerce_lease_pid_boundaries():
    assert driver_factory._coerce_lease_pid(0) is None
    assert driver_factory._coerce_lease_pid(-1) is None
    assert driver_factory._coerce_lease_pid(1) == 1          # граница ВНУТРИ домена
    assert driver_factory._coerce_lease_pid("123") == 123
    assert driver_factory._coerce_lease_pid(123) == 123
    assert driver_factory._coerce_lease_pid(True) is None     # int(True)==1, но JSON true - не PID
    assert driver_factory._coerce_lease_pid(None) is None


# --- non-blocker 6: sharing violation != отсутствие файла ---

@pytest.mark.p1
@allure.id("P3-N3-lease-read-retries-on-sharing-violation")
@allure.title("Non-blocker 6: PermissionError (окно take-лока) ретраится, а не читается как 'лизы нет'")
def test_read_device_lease_retries_sharing_violation(monkeypatch, tmp_path):
    """Окно, в которое `Take-DeviceLeaseSlot` держит файл эксклюзивно
    (FileShare.None), давало на стеке 2 ЛОЖНЫЙ отказ "лиза отсутствует -
    возьми Use-DeviceStack -N 2" поверх штатно берущегося стека."""
    payload = _write_adoptable_lease(tmp_path, 2)
    path = tmp_path / "device-lease-2.json"
    real_read_text = type(path).read_text
    calls = {"n": 0}

    def _flaky_read_text(self, *args, **kwargs):
        if self.name == path.name:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "read_text", _flaky_read_text)
    monkeypatch.setattr(driver_factory, "_LEASE_READ_RETRY_DELAY", 0.001)

    lease = driver_factory._read_device_lease(2)

    assert calls["n"] == 3, "два транзиентных отказа обязаны быть переиграны"
    assert lease is not None and lease["owner_token"] == payload["owner_token"]


@pytest.mark.p1
@allure.id("P3-N3-lease-read-gives-up-after-retries")
@allure.title("Non-blocker 6 (граница): sharing violation НЕ разошёлся за все попытки - WARN + 'как отсутствующая'")
def test_read_device_lease_gives_up_after_retries(monkeypatch, tmp_path, capsys):
    _write_adoptable_lease(tmp_path, 2)
    path = tmp_path / "device-lease-2.json"

    def _always_locked(self, *args, **kwargs):
        raise PermissionError(13, "locked")

    monkeypatch.setattr(type(path), "read_text", _always_locked)
    monkeypatch.setattr(driver_factory, "_LEASE_READ_RETRY_DELAY", 0.001)

    assert driver_factory._read_device_lease(2) is None
    assert "sharing violation" in capsys.readouterr().err


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-refusal-names-lock-not-absence")
@allure.title("Мелкий 2: файл лизы ЗАНЯТ конкурентом - отказ стека 2 называет ИСТИННУЮ причину, не 'лизы нет'")
def test_stack2_refusal_names_sharing_violation_not_absence(monkeypatch, tmp_path):
    """Прежде исчерпанный sharing violation давал отказ «лиза отсутствует —
    возьми Use-DeviceStack -N 2»: совет ВРЕДНЫЙ (повторное взятие затрёт
    чужое), а истинная причина оставалась только в WARN."""
    _set_stack(monkeypatch, 2)
    _write_adoptable_lease(tmp_path, 2)
    path = tmp_path / "device-lease-2.json"
    monkeypatch.setattr(type(path), "read_text",
                        lambda self, *a, **k: (_ for _ in ()).throw(PermissionError(13, "locked")))
    monkeypatch.setattr(driver_factory, "_LEASE_READ_RETRY_DELAY", 0.001)

    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError) as exc:
        driver_factory.check_device_lease()

    msg = str(exc.value)
    assert "DEVICE_LEASE_BLOCKED" in msg
    assert "ЗАНЯТ другим процессом" in msg, msg
    assert "ПОВТОРИ прогон через секунду" in msg, msg
    assert "НЕ бери лизу заново" in msg, msg
    # Вредный совет прежней формулировки не должен остаться единственным
    assert "лиза отсутствует или" not in msg, msg


@pytest.mark.p1
@allure.id("P3-N3-lease-stack2-refusal-corrupt-vs-missing")
@allure.title("Мелкий 2 (пара): битый JSON и ПУСТОЕ место различимы в тексте отказа стека 2")
def test_stack2_refusal_distinguishes_corrupt_from_missing(monkeypatch, tmp_path):
    _set_stack(monkeypatch, 2)
    (tmp_path / "device-lease-2.json").write_text("{ не json !!!", encoding="utf-8")
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError) as exc_corrupt:
        driver_factory.check_device_lease()
    assert "НЕ РАЗОБРАН" in str(exc_corrupt.value)

    (tmp_path / "device-lease-2.json").unlink()
    with pytest.raises(driver_factory.DeviceLeaseInvalidStackError) as exc_missing:
        driver_factory.check_device_lease()
    assert "НЕ РАЗОБРАН" not in str(exc_missing.value)
    assert "Возьми: Use-DeviceStack -N 2." in str(exc_missing.value)


@pytest.mark.p1
@allure.id("P3-N3-lease-read-reason-codes")
@allure.title("Мелкий 2: _read_device_lease_with_reason различает missing/locked/corrupt")
def test_read_device_lease_reason_codes(monkeypatch, tmp_path):
    assert driver_factory._read_device_lease_with_reason(2) == (None, driver_factory._LEASE_ABSENT_MISSING)

    (tmp_path / "device-lease-2.json").write_text("{ битый", encoding="utf-8")
    assert driver_factory._read_device_lease_with_reason(2)[1] == driver_factory._LEASE_ABSENT_CORRUPT

    path = tmp_path / "device-lease-2.json"
    monkeypatch.setattr(driver_factory, "_LEASE_READ_RETRY_DELAY", 0.001)
    monkeypatch.setattr(type(path), "read_text",
                        lambda self, *a, **k: (_ for _ in ()).throw(PermissionError(13, "locked")))
    assert driver_factory._read_device_lease_with_reason(2)[1] == driver_factory._LEASE_ABSENT_LOCKED


@pytest.mark.p1
@allure.id("P3-N3-lease-read-missing-file-is-not-retried")
@allure.title("Non-blocker 6 (контрольная пара): отсутствующий файл - сразу None, БЕЗ ретраев")
def test_read_device_lease_missing_file_not_retried(monkeypatch, tmp_path):
    """Граница ретрая: `FileNotFoundError` - честное 'лизы нет', ретраить
    нечего (иначе каждый штатный `free`-путь платил бы задержкой)."""
    path = tmp_path / "device-lease-2.json"
    calls = {"n": 0}
    real_read_text = type(path).read_text

    def _counting(self, *args, **kwargs):
        if self.name == path.name:
            calls["n"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "read_text", _counting)
    assert driver_factory._read_device_lease(2) is None
    assert calls["n"] == 1


def _write_cas_lock(tmp_path, pid):
    lock_path = tmp_path / "device-lease-2.json.lock"
    lock_path.write_text(
        json.dumps({"pid": pid, "taken_utc": "2026-08-20T00:00:00+00:00"}),
        encoding="utf-8",
    )
    return lock_path


@pytest.mark.p1
@allure.id("P3-N3-lease-cas-release-own-lock-removed")
@allure.title("CAS-finally снимает СВОЙ замок (device-free)")
def test_release_cas_lock_own_removed(tmp_path):
    lock_path = _write_cas_lock(tmp_path, driver_factory.os.getpid())
    driver_factory._release_cas_lock_if_owned(lock_path)
    assert not lock_path.exists()


@pytest.mark.p1
@allure.id("P3-N3-lease-cas-release-foreign-lock-kept")
@allure.title("CAS-finally НЕ снимает ЧУЖОЙ замок - взлом по возрасту не каскадирует (device-free)")
def test_release_cas_lock_foreign_kept(tmp_path):
    """Критик-раунд 5, fixes[1] (замер r5_stale2): finally без проверки
    владения снимал замок ВТОРЖЕНЦА после age-взлома - один взлом терял
    взаимное исключение целиком (третий процесс входил мгновенно)."""
    lock_path = _write_cas_lock(tmp_path, 4242)
    driver_factory._release_cas_lock_if_owned(lock_path)
    assert lock_path.exists(), "чужой замок снят - каскад r5_stale2 воспроизводим"


@pytest.mark.p1
@allure.id("P3-N3-lease-cas-release-corrupt-lock-kept")
@allure.title("CAS-finally не трогает нечитаемый замок - его доломает stale-break (device-free)")
def test_release_cas_lock_corrupt_kept(tmp_path):
    lock_path = tmp_path / "device-lease-2.json.lock"
    lock_path.write_text("{битый json", encoding="utf-8")
    driver_factory._release_cas_lock_if_owned(lock_path)
    assert lock_path.exists()
