---
key: "AT-BUG-011"
project: "AO3"
issueType: "bug"
status: "bug-fixed"
priority: "p1"
summary: "Фикстура replay не проверяет присутствие mitm-CA перед тестом — без CA каждый replay-тест умирает 120–240с ReadTimeoutError вместо мгновенной диагностики (мисдиагнозы каскадом: ESC-001, ложный Reopened AT-BUG-006)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "sev:major"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-17T18:40:00Z"
updated: "2026-07-17T18:40:00Z"
archived: false
resolution: null
---

# Фикстура replay не проверяет присутствие mitm-CA перед тестом — без CA каждый replay-тест умирает 120–240с ReadTimeoutError вместо мгновенной диагностики (мисдиагнозы каскадом: ESC-001, ложный Reopened AT-BUG-006)

_Спроецировано из `bugs/AT-BUG-011.md` (источник правды).
Статус в нашей машине: **Fixed**._

# AT-BUG-011 — replay-фикстура без fail-fast проверки mitm-CA

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: broken_environment`). Заведён по рекомендации critic из
  диагностики at-bug-009-env-diagnosis (решение Lead, слово оператора о
  fail-fast классе 2026-07-16).

## Суть долга

mitm-CA ставится волатильным tmpfs-mount'ом (`install-mitm-ca.sh`: «не
переживает reboot») и стирается ЛЮБЫМ ребутом эмулятора; `Install-MitmCA`
вызывается только из `Start-Emulator -WritableSystem`. Если среда поднята
иначе (холодный ребут `-no-snapshot-load` без переустановки CA, `adb
reboot`), фикстура `replay` (`framework/tests/conftest.py`) стартует тест
как ни в чём не бывало: WebView отвергает TLS к mitmproxy, мост
chromedriver↔WebView виснет, и КАЖДЫЙ replay-тест умирает
`ReadTimeoutError` через 120с (×2 с rerun-гейтом AT-BUG-007 = до 240с),
не называя причину.

Доказанная стоимость отсутствия проверки: сессия fix-verifier 65 мин
(~52 мин — ожидание таймаутов), ложный `Reopened` AT-BUG-006, эскалация
ESC-001, мисдиагноз «новый класс деградации» — всё при исправной среде,
которой не хватало одной строки диагностики. Полный след — A/B/A'
critic'а в Обсуждении `bugs/AT-BUG-009.md` (запись 2026-07-17).

## Критерий готовности (Fixed)

- Фикстура `replay` перед стартом mitmdump/теста проверяет присутствие
  mitm-CA в системном сторе доверия (та же проверка, что печатает
  «CA visible in apex store: OK» в `Install-MitmCA`/`install-mitm-ca.sh`)
  и при отсутствии падает НЕМЕДЛЕННОЙ явной ошибкой с рецептом:
  «mitm-CA отсутствует (стирается любым ребутом) — поднимите среду
  `Start-Emulator -WritableSystem` или выполните `Install-MitmCA`
  (AT-BUG-011)».
- Проверка выполняется один раз на сессию/первый replay-тест (не
  замедлять каждый тест повторным adb-вызовом без нужды) — способ
  кеширования на усмотрение исполнителя.
- Device-free юнит-проба механизма (монки-патч adb-вызова: CA есть /
  CA нет → мгновенный явный отказ с текстом AT-BUG-011) — по образцу
  `test_subprocess_timeout_unit.py`, 3 прогона подряд зелёные.
- Device-регресс: один replay-тест (например `test_replay_infra_probe.py`)
  зелёный на корректно поднятой среде (`-WritableSystem`) — проверка не
  ломает здоровый путь.
- Runbook-строка «ReadTimeoutError на replay → первым кандидатом
  проверить CA» в HANDOFF («Как поднять окружение») — внесена Lead'ом
  2026-07-16 этим же проходом; исполнителю сверить актуальность.

## Анализ

Класс — «environment-предусловие не проверяется на входе, отказ
диагностируется таймаутом» (тот же дух, что правило п.6 дисциплины команд:
негатив валиден только с позитивной сверкой). Родственный механизм в
очереди Lead — fail-fast для device-воркеров (HANDOFF «СЛЕДУЮЩИЙ ШАГ»
п.5): этот баг закрывает слой фикстуры, механизм — слой протокола
воркеров; не дублируют друг друга.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-16T22:50:00Z — Lead (Fable), заведение по рекомендации critic
(at-bug-009-env-diagnosis):** рекомендация №2 вердикта critic оформлена
отслеживаемым артефактом (класс «заметка вместо артефакта» не повторяем —
правило 9). Диспатч — штатным B4-правилом; приоритет высокий внутри
очереди (major: каждая встреча с классом стоит десятки минут и порождает
мисдиагнозы).

**2026-07-17T18:40:00Z — test-maintainer, Open → Fixed:** реализован
`mitm.is_ca_installed()` (`framework/core/mitm.py`) — ТА ЖЕ проверка, что
`install-mitm-ca.sh` печатает как «CA visible in apex store: OK»:
`subject_hash_old` CA-сертификата через `openssl` (тот же бинарь/флаг, что
и install-скрипт) + `adb shell ls /apex/com.android.conscrypt/cacerts/`,
сравнение по имени файла `<hash>.0`. Зависший adb/openssl оборачивается в
явную `TimeoutError` (тот же класс, что AT-BUG-009) — не «второй немой
таймаут» поверх старого.

Фикстура `replay` (`framework/tests/conftest.py`) зовёт новую
`_ensure_replay_ca()` первой строкой; при отсутствии CA — мгновенная
`RuntimeError` с текстом «AT-BUG-011» и рецептом (`Start-Emulator
-WritableSystem` / `Install-MitmCA`). Результат кешируется в
module-level `_ca_checked` — проверка происходит один раз на сессию
(первый replay-тест), не на каждом (критерий п.2).

Witness:
- Device-free юнит-проба `framework/tests/test_replay_ca_check_unit.py`
  (5 тестов: `is_ca_installed()` true/false-ветки, `_ensure_replay_ca()`
  проходит/падает мгновенно явной ошибкой, кеш на сессию) — 3 прогона
  подряд `Invoke-Pytest tests/test_replay_ca_check_unit.py -v`,
  PYTEST_EXIT=0, 5 passed каждый раз (0.09-1.00s, не таймаут).
- Device-регресс на корректно поднятой среде (`Start-Emulator
  -WritableSystem` → CA visible in apex store: OK → `Start-Appium` →
  `Install-App` → `Invoke-Pytest tests/test_replay_infra_probe.py -v`):
  `test_rate_from_listing_bottom_sheet_on_replay_fixture[listing_basic.mitm]
  PASSED`, PYTEST_EXIT=0 (23.66s) — новая проверка не ломает здоровый путь.
- `python scripts/arch_check.py` → «ошибок 0, предупреждений 0».
- Регресс `test_subprocess_timeout_unit.py` (соседний AT-BUG-009-класс,
  проверка на неслучайную поломку соседнего механизма) — 8 passed.
- Среда погашена после device-регресса (`adb emu kill` + `Stop-NodeProcesses`,
  `Get-Device` → `NO DEVICE`).

Runbook-строка в `docs/HANDOFF.md` («Как поднять окружение», диагноз
critic + ссылка AT-BUG-011) уже на месте с 2026-07-16 — сверено, не
дублировалась.

Пункты критерия готовности (1-5) закрыты. Готово к `fix-verifier` (B4→D1,
долг фреймворка — сборку приложения ждать не нужно).
