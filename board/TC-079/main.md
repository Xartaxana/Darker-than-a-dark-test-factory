---
key: "TC-079"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-21T22:53:56Z"
updated: "2026-07-21T22:53:56Z"
archived: false
resolution: "done"
---

# Чекбокс 'Main pairing only' инжектируется в include-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (replay)

_Спроецировано из `test-cases/canary/TC-079.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-079 — Main-pairing include-чекбокс: инъекция + доступность (replay)

## Предусловия
- Приложение запущено, режим **replay**
  (`framework/data/recordings/sort_filter_form.mitm` — реальная страница
  `archiveofourown.org/tags/Fluff/works`, форма `#work-filters` в исходной
  разметке, Verified в AT-BUG-006).

## Сценарий (Given-When-Then)

**Given** приложение запущено в replay-режиме и открыта `sort_filter_form.mitm`
с раскрытой формой Sort & Filter, список `#include_relationship_tags` виден,
ни один пункт не отмечен

**When** пользователь отмечает РОВНО ОДИН чекбокс из
`#include_relationship_tags`

**Then** `[data-ao3-main-pairing-cb]` присутствует первым пунктом списка и
включён (`disabled=false`)
**And** снятие отметки возвращает чекбокс в отключённое состояние
(`disabled=true`, opacity 0.4)

**Инвариант:** тот же контракт, что TC-078, детерминированно проверенный на
записанной разметке формы (фикс якорь — не зависит от live-вариативности
списка relationship-тегов).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Фикстура | `framework/data/recordings/sort_filter_form.mitm` |
| Селектор | `[data-ao3-main-pairing-cb]` |

## Заметки для автоматизации
- Фикстура уже существует и Verified (AT-BUG-006, форма подтверждена в
  исходной разметке через page_source живого Appium-сеанса) — блокеров нет.
- Селектор `[data-ao3-main-pairing-cb]` пока не в `selectors.py` — добавить
  при кодировании (не блокер).
- Маркер: `@pytest.mark.p0 @pytest.mark.replay`.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`

## Ревью автотеста

Вердикт: **PASS** (Approved → Automated, automation_status: active).
Ревьюер: test-reviewer, 2026-07-21T22:53:56Z. Критик-вход приёмки самой
автоматизации (routing-log TC-079-review, 2026-07-21T16:08-16:11, PASS) —
входной контекст; ниже — независимое полное F1-ревью.

Чек-лист:
1. **Архитектура (C1):** `python scripts/arch_check.py` → «ошибок 0,
   предупреждений 0». ALLOWLIST пуст (файл не добавлен «под себя»). Локатор
   `[data-ao3-main-pairing-cb]` — в `framework/web/selectors.py:78`, page-object
   `SortFilterFormPage` — в `framework/web/sort_filter_form_page.py`, шаги — в
   `framework/steps/browser_steps.py`, ожидания — через `core/waits.wait_until`,
   `sleep` в тесте нет. OK.
2. **Traceability:** `@allure.id("TC-079")` == id кейса; маркеры
   `@pytest.mark.p0 @pytest.mark.replay` соответствуют frontmatter (priority P0,
   replay) и «Заметкам для автоматизации»; `automated_by` указывает на реальную
   функцию `test_main_pairing_checkbox_availability_replay`
   (test_ao3_selectors.py:344). OK.
3. **Соответствие кейсу по смыслу:** кейс несёт строку `Инвариант:` (доступность
   зависит только от количества отмеченных, не от того, какой тег). Тест проверяет
   именно свойство по трём классам кардинальности: 0 отмечено → disabled, 1 →
   enabled, 2 → disabled. Assert'ы проверяют суть (disabled-состояние + opacity
   label 1/0.4 через `checkbox_availability_state`), а не «элемент существует». OK.
4. **Фикстуры и данные:** порядок `clean_app, replay, driver` — `clean_app`
   чистит состояние ДО создания Appium-сессии (driver), `replay` поднимает
   mitmdump с гарантированным teardown (proxy сброшен, mitm заглушён в `finally`).
   Кейс канареечный — данных сидить не нужно, владение через clean_app корректно.
   Не зависит от порядка других тестов. OK.
5. **Flake-риск:** все ожидания явные (`wait_until` с таймаутом),
   `_wait_relationship_controls_ready` дожидается инъекции чекбоксов до
   взаимодействия; клик — настоящий `element.click()` через JS (штатно всплывает
   `change`, на который подписан `updateAvailability`), гонки с анимацией нет;
   replay-режим — к живому AO3 обращения нет. OK.
6. **Независимое воспроизведение:** среда поднята каноническими формами
   (`Start-Emulator -WritableSystem` + mitm-CA, `Start-Appium`);
   `Invoke-Pytest -k test_main_pairing_checkbox_availability_replay` → `1 passed`,
   `PYTEST_EXIT=0` (35.5s). OK.
7. **Красная проба (мутационная), 2026-07-21T22:53:56Z:**
   - Что портил: временно добавлена вторая отметка чекбокса
     (`toggle_relationship_checkbox(driver, "include", 1)`) перед
     `assert_relationship_checkbox_enabled` — итого 2 отмечено, что по контракту
     обязано держать инжектированный чекбокс отключённым (порча проверяемого
     условия «ровно один → enabled»).
   - Команда: `Invoke-Pytest -k test_main_pairing_checkbox_availability_replay`.
   - Результат: `1 failed`, `PYTEST_EXIT=1`; текст падения по существу —
     «чекбокс include-списка не стал доступен (disabled остаётся true)» на строке
     `assert_relationship_checkbox_enabled` (осмысленный assert доступности, не
     таймаут-мусор — сообщение называет суть контракта).
   - Откат: `git checkout -- framework/tests/canary/test_ao3_selectors.py`,
     `git status --porcelain` пуст (дифф чист).

Дефектов-собратьев (D-0043) при ревью не замечено: парные кейсы TC-078/080/081
той же формы Sort&Filter несут строку `Инвариант:` и проверяют свойство по
классам кардинальности аналогично.
