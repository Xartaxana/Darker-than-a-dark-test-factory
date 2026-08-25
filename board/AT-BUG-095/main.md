---
key: "AT-BUG-095"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "framework/core/mitm.py::is_ca_installed() проверяет ТОЛЬКО APEX-стор доверия — на стеке 2 (ao3_test_api29, apex conscrypt отсутствует) ложно сообщает «CA не установлен», хотя CA реально стоит в системном сторе — блокирует ЛЮБОЙ replay-тест на этом стеке"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-149", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-08-21T11:51:00Z"
updated: "2026-08-21T11:51:00Z"
archived: false
resolution: null
---

# framework/core/mitm.py::is_ca_installed() проверяет ТОЛЬКО APEX-стор доверия — на стеке 2 (ao3_test_api29, apex conscrypt отсутствует) ложно сообщает «CA не установлен», хотя CA реально стоит в системном сторе — блокирует ЛЮБОЙ replay-тест на этом стеке

_Спроецировано из `bugs/AT-BUG-095.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-095 — `mitm.is_ca_installed()` смотрит только в APEX-стор — ложный «CA не установлен» на стеке 2 (api29, apex conscrypt отсутствует), блокирует ЛЮБОЙ replay-тест на этом стеке

## Окружение

- Стек 2: `emulator-5556` (AVD `ao3_test_api29`, тот же образ, что
  `bugs/AT-BUG-028.md` перевёл в рабочее состояние), Appium `:4725`, APK
  dev-local versionCode 12. Долг тестовой системы (`type: test_debt`,
  `debt_kind: broken_environment`) — не зависит от сборки приложения.
- Поверхность: `framework/core/mitm.py::is_ca_installed()`, вызывается из
  `framework/tests/conftest.py::_ensure_replay_ca()` (фикстура `replay`,
  ЕДИНСТВЕННЫЙ путь запуска replay-теста).

## Суть долга

`scripts/install-mitm-ca.sh` (см. `bugs/AT-BUG-024.md:79-88`) уже умеет
переключаться между двумя сторами доверия по факту присутствия APEX-модуля
conscrypt:

```sh
if [ -d /apex/com.android.conscrypt/cacerts ]; then
  ls /apex/com.android.conscrypt/cacerts/ | grep -q "${HASH}" && echo "CA visible in apex store: OK" ...
else
  ls /system/etc/security/cacerts/ | grep -q "${HASH}" && echo "CA visible in system store: OK" ...
fi
```

На стеке 2 (`ao3_test_api29`) `/apex/com.android.conscrypt/cacerts`
**отсутствует** (подтверждено `bugs/AT-BUG-028.md:173-177`: «apex conscrypt
store absent», и живым `adb shell test -d ... && echo APEX_EXISTS ||
echo APEX_ABSENT` → `APEX_ABSENT`, этим ходом) — CA устанавливается и
проверяется install-скриптом ИСКЛЮЧИТЕЛЬНО через `/system/etc/security/
cacerts/` (`store=139 apex=0`, «CA visible in system store: OK», подтверждено
живым замером ЭТОГО хода: `adb shell ls /system/etc/security/cacerts/ | wc -l`
→ `139`).

Но **Python-сторона проверки** (`framework/core/mitm.py::is_ca_installed()`,
заведена `bugs/AT-BUG-011.md`, ДО появления второго AVD/api29-ветки
AT-BUG-024/028) хардкодит единственный путь и НЕ несёт условной ветки:

```python
_APEX_CACERTS_DIR = "/apex/com.android.conscrypt/cacerts/"
...
def is_ca_installed() -> bool:
    ...
    ls_cp = subprocess.run(
        [settings.ADB, "-s", settings.DEVICE_NAME, "shell", "ls", _APEX_CACERTS_DIR],
        ...
    )
    return f"{ca_hash}.0" in ls_cp.stdout
```

`adb shell ls /apex/com.android.conscrypt/cacerts/` на отсутствующем пути
не находит хэш CA в выводе → функция возвращает `False` ВСЕГДА на этом
классе устройств, независимо от того, установлен ли CA фактически (а он
установлен — `install-mitm-ca.sh` это подтверждает своим собственным,
корректным, условным чеком). `conftest.py::_ensure_replay_ca()` при `False`
бросает:

```
RuntimeError: mitm-CA отсутствует в системном сторе доверия (устройство
должно быть загружено как -writable-system) и установлен через
`Start-Emulator -WritableSystem` или отдельно `Install-MitmCA`/`bash
scripts/install-mitm-ca.sh` (AT-BUG-011).
```

— **ложно**, до первого `driver.get()` теста, на КАЖДОМ replay-тесте на
стеке 2. Живой замер этого хода (`Invoke-Pytest tests/test_accessibility.py
-k test_computed_contrast_holds_wcag_threshold_light_and_dark`, стек 2,
CA живым `install-mitm-ca.sh`-путём подтверждённо установлен): `ERROR at
setup` на этой самой строке, `RuntimeError` с текстом выше, до какой-либо
навигации/сети.

## Влияние

Блокирует автоматизацию/стабилизацию TC-149 на стеке 2 — ЛЮБОЙ
`@pytest.mark.replay` тест, запущенный на api29-классе устройств
(`apex conscrypt` отсутствует), падает на этом же чеке ДО первого шага
теста. Класс шире одного TC-149: любой будущий replay-тест на стеке 2
получит идентичную ложную ошибку — сиблинг-риск для всех будущих
replay-прогонов на api29 (доклад по правилу 9 CLAUDE.md, не расширяю scope
самостоятельным фиксом — `framework/core/mitm.py` вне разрешённого DoD
test-automator, ограниченного правкой тестов/страниц).

## Критерий готовности (Fixed)

- `framework/core/mitm.py::is_ca_installed()` получает ту же условную
  ветку, что уже есть в `install-mitm-ca.sh`/`ca-mount.sh`: если
  `/apex/com.android.conscrypt/cacerts` присутствует на устройстве —
  проверять его (текущее поведение, регресс на api34 недопустим); если
  отсутствует — проверять `/system/etc/security/cacerts/`.
- Юнит-покрытие (по аналогии с `framework/tests/test_replay_ca_check_unit.py`,
  заведённым AT-BUG-011): обе ветки (apex present/absent) на true/false CA.
- Живой прогон `@pytest.mark.replay`-теста (например TC-149) на стеке 2
  проходит фикстуру `replay` без ложного `RuntimeError`.
- Регресс на стеке 1 (api34, apex присутствует) — без изменений (существующий
  путь не трогается по логике, только оборачивается условием).

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| 2026-08-21 | dev-local (versionCode 12) | `test_cases: ["TC-149"]` — carve-out: сам TC-149 этим ходом не гонялся (вне DoD builder-диспатча, диспатч ограничен фиксом `mitm.py` + юнитами + живым read-only witness чека). Замена: (1) юнит-набор `tests/test_replay_ca_check_unit.py` + `tests/test_mitm_adb_serial_addressing_unit.py` (14 тестов, включая 4 новых на apex/system-branch + честный False + explicit adb-failure); (2) `python scripts/arch_check.py`; (3) `python -m py_compile mitm.py`; (4) ЖИВОЙ read-only witness `is_ca_installed()` на стеке 2 (emulator-5556, api29) | Юниты: `14 passed in 5.57s`, `PYTEST_EXIT=0`. `arch_check.py`: `ошибок 0, предупреждений 26` (все 26 — известные, не связанные с этой правкой). `py_compile`: чист (exit 0). Живой witness: `adb -s emulator-5556 shell test -d /apex/com.android.conscrypt/cacerts` → `APEX_ABSENT`; `adb -s emulator-5556 shell ls /system/etc/security/cacerts/ \| wc -l` → `139`; `python -c "from framework.config import settings; from framework.core import mitm; print(mitm.is_ca_installed())"` (venv-python, стек 2) → `True` — раньше (до фикса) этот же живой сценарий возвращал `False` и блокировал `_ensure_replay_ca()`. | builder: реализация закрыта, DoD выполнен. Финальная приёмка Fixed→Verified (включая живой прогон TC-149 через `@pytest.mark.replay`) — за fix-verifier/координатором. |

## Обсуждение

**[test-automator @ 2026-08-21T00:00:00Z]** Заведён при попытке
стабилизировать TC-149 на стеке 2 (N4, продолжение открытого коридорного
тикета). Прогон уткнулся в `RuntimeError` из `_ensure_replay_ca()` сразу на
setup, притом что манифест диспатча явно подтверждал живой witness
«CA visible in system store: OK» для этого стека — расхождение между
заявленным состоянием среды и результатом теста указало на сам чек, не на
реальное отсутствие CA. Прочитан `framework/core/mitm.py::is_ca_installed()`
целиком — хардкод `_APEX_CACERTS_DIR`, ни одной ветки на system-store.
Сверено с `scripts/install-mitm-ca.sh` (уже условный, AT-BUG-024) — налицо
рассинхрон между shell-стороной (которая устанавливает/подтверждает CA
корректно) и Python-стороной (которая проверяет неверно). Живой независимый
замер этим ходом: `adb -s emulator-5556 shell test -d
/apex/com.android.conscrypt/cacerts` → `APEX_ABSENT`; `adb -s emulator-5556
shell ls /system/etc/security/cacerts/ | wc -l` → `139`. Дубликаты
проверены (`Grep bugs/` по `is_ca_installed`/apex/system store) — не
найдено, `AT-BUG-011` завёл функцию ДО появления api29-ветки,
`AT-BUG-024`/`AT-BUG-028` чинили только shell-скрипты/AVD/chromedriver, не
эту Python-функцию. `test_cases: ["TC-149"]` — первый пойманный экземпляр;
класс шире (любой будущий replay-тест на стеке 2). Правку `framework/
core/mitm.py` сам не делаю — вне DoD этого диспатча (ограничен тестами/
страницами при технической нестабильности, не core-инфраструктурой);
решение о диспатче фикса — за Lead (D-0037).

**[builder (Sonnet) @ 2026-08-21T11:51:00Z] Реализация.** Прочитан `mitm.py`
целиком, `install-mitm-ca.sh`/`ca-mount.sh` (эталон условной логики) и
существующие юниты `test_replay_ca_check_unit.py`/
`test_mitm_adb_serial_addressing_unit.py` (последний — не владею, но менял
бы поведение, которое он проверяет). `is_ca_installed()` теперь строит ОДИН
`adb shell` вызов с `if [ -d apex ]; then ls apex; else ls system; fi` —
ветвление на устройстве, не по предположению вызывающей стороны об API;
сохраняет инвариант «ровно один adb-вызов на проверку» (тот же, что
проверяет `test_mitm_adb_serial_addressing_unit.py::
test_is_ca_installed_addresses_serial`, не владею этим файлом — дизайн
специально выбран так, чтобы не потребовалось его трогать; прогон
подтвердил зелёный без изменений).

ТЕМ ЖЕ ходом закрыт п.2 спеки (env-негатив ≠ факт): `ls_cp.returncode != 0`
теперь бросает `RuntimeError` с дословным stdout/stderr вместо того, чтобы
`f"{ca_hash}.0" in ls_cp.stdout` тихо дал `False` на пустом/ошибочном
выводе — тот же класс, что уже закрыт для `get_device_proxy()` (AT-BUG-064
F2), но здесь риск выше (напрямую блокирует КАЖДЫЙ replay-тест сессии, а не
только один fail-safe слой), поэтому реакция — явное исключение, а не
fail-open `None`.

4 новых юнит-теста в `test_replay_ca_check_unit.py` (apex-ветка регресс,
system-store ветка — основной случай бага, честный `False` при отсутствии
хэша в актуальном сторе, явная `RuntimeError` на отказе adb с
`returncode=1`/`stderr="error: device offline"`) — новый файл не заводился,
расширен существующий (манифест диспатча предлагал оба варианта, выбран
менее инвазивный). Живой read-only witness на стеке 2 (лиза
`Use-DeviceStack -N 2`, устройство не модифицировалось): `is_ca_installed()`
через venv-python вернула `True` там, где до фикса возвращала бы `False`
(подтверждено независимой read-only сверкой APEX_ABSENT/139 файлов system
store — тот же результат, что зафиксирован при заводе бага). Полный
witness — в отчёте координатору/логе диспатча.

Сиблинги (правило 9 CLAUDE.md): `Grep` по `apex.*conscrypt|APEX_CACERTS|
cacerts` во всём `framework/` — совпадения только в `mitm.py` и двух
юнит-файлах, ни одного другого места с тем же хардкодом класса не найдено.

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* — не найдено покрытия
      именно Python-стороны чека (`is_ca_installed`); AT-BUG-011/024/028 —
      соседние, но не дублирующие слои
- [x] Точная цитата кода (`_APEX_CACERTS_DIR`, `is_ca_installed`) и точная
      цитата контрастного условного shell-чека приложены
- [x] Severity обоснована — major: блокирует ЛЮБОЙ replay-тест на целом
      классе устройств (стек 2/api29), не только TC-149
- [x] Направление фикса приложено (условная ветка apex/system store,
      зеркалящая уже существующую в install-mitm-ca.sh/ca-mount.sh)
- [x] Живой замер (APEX_ABSENT, store count 139) приложен дословно, не
      гипотеза
- [x] Ни одного изменения в `framework/`/`app-under-test/` этим тикетом не
      внесено — только анализ и живой read-only замер
- [x] `type: test_debt`, `debt_kind: broken_environment` — расхождение
      специфично для образа стека 2 (api29 без apex conscrypt)
- [x] Лок не нужен (баг Open, никто не начал фикс)
