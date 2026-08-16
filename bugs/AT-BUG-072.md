---
id: AT-BUG-072
title: "Нет автоматизационного примитива нажатия клавиш громкости (KEYCODE_VOLUME_UP/DOWN) — блокирует листание страниц кнопками громкости"
type: test_debt
debt_kind: missing_fixture
severity: major
status: Open
found_in: "test-designer, дизайн области «reading-UX: листание страниц кнопками громкости» (docs/01-test-strategy.md §9, needs-design заведена test-strategist 2026-08-15 по QAREADY-38)"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-252", "TC-253", "TC-254", "TC-255"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-15T00:10:14Z"
updated: "2026-08-15T00:10:14Z"
reopen_count: 0
dispute_count: 0
awaiting: none
lock: "test-maintainer:2026-08-16T10:50:00Z"
---

# AT-BUG-072 — нет обёртки над `adb shell input keyevent KEYCODE_VOLUME_UP/DOWN` с наблюдаемым подтверждением

## Окружение
- Не зависит от сборки приложения: долг тестовой системы (`type: test_debt`,
  `debt_kind: missing_fixture`).

## Суть долга

`browse-volume-button-paging` (сборка 59be96c6, `MainActivity.kt:105-124`)
перехватывает `KEYCODE_VOLUME_DOWN`/`KEYCODE_VOLUME_UP` для листания
страниц кнопками громкости. Тестопригодность прямо названа
test-strategist (docs/01-test-strategy.md §9): «клавиши подаются `adb
shell input keyevent 24/25` — примитива в фабрике может не быть».

Проверено: в `framework/steps/app_steps.py` есть только
`send_app_to_background` (`input keyevent KEYCODE_HOME`, с ожиданием
факта ухода в фон через `driver.query_app_state`) — прецедент формы, но
НЕ примитив для VOLUME_UP/DOWN. Голого `adb shell input keyevent 24`
недостаточно по классу «пустой/ошибочный вывод env-инструмента ≠ факт»
(CLAUDE.md, дисциплина команд п.6): нажатие клавиши само по себе не
наблюдаемо (`adb.shell` глотает returncode), поэтому тихо не сработавшее
нажатие неотличимо от штатного эффекта без явного ожидания последствия
(здесь — сдвиг scroll-позиции активной вкладки), тем же приёмом, что
`send_app_to_background` ждёт уход в фон.

Заблокированные кейсы: TC-252 (основной эффект листания обеими клавишами),
TC-253 (off-инвариант — клавиши при выключенной настройке), TC-254
(асимметрия перехвата поверх оверлея/панели/диалога), TC-255 (граница
перехвата — вкладки Library/Settings) — все требуют реального нажатия
клавиш громкости.

## Критерий готовности (Fixed)

- В `framework/steps/app_steps.py` (или аналоге) есть функция вида
  `press_volume_key(driver, direction)`, отправляющая `input keyevent
  KEYCODE_VOLUME_DOWN`/`KEYCODE_VOLUME_UP` и дожидающаяся наблюдаемого
  последствия (параметризуемый oracle — например, сдвиг scroll-позиции
  активной вкладки ЛИБО появление системного индикатора громкости, в
  зависимости от сценария), по образцу `send_app_to_background`.
- Хотя бы один из заблокированных кейсов (рекомендация: TC-252, основной
  позитивный путь) доведён до зелёного прогона на этом примитиве.
- Smoke без регресса.

## Анализ

Класс — «механизм адб есть, обёртки с наблюдаемым подтверждением нет»,
тот же, что породил `send_app_to_background`/`AT-BUG-004`-класс общих
`app_steps`-примитивов. Чинит фабрика по правилу «Устранить test debt»
(B4). Fixed не ждёт сборку приложения.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|
| | | | | |

## Обсуждение

**2026-08-15T00:10:14Z — test-designer (заведение при дизайне области
«reading-UX: листание кнопками громкости»):** блокер найден при
проектировании TC-252..255 — заведён тем же ходом, по правилу
test-designer (шаг 4 воркфлоу). Кейсы оставлены в `status: Review`
(Given/Then полны и воспроизводимы по смыслу, ограничение чисто
инструментальное — та же логика, что AT-BUG-071).
