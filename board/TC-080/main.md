---
key: "TC-080"
project: "AO3"
issueType: "test-case"
status: "tc-automated"
priority: "p0"
summary: "Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (live)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02", "automation:active"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-20T02:40:29Z"
updated: "2026-07-20T02:40:29Z"
archived: false
resolution: "done"
---

# Чекбокс исключения main pairing инжектируется в exclude-фильтр формы Sort&Filter, доступен только при ровно одном выбранном relationship-теге (live)

_Спроецировано из `test-cases/canary/TC-080.md` (источник правды).
Статус в нашей машине: **Automated**._

# TC-080 — Exclude-main-pairing чекбокс: инъекция + доступность (live)

## Предусловия
- Приложение запущено с чистыми данными, режим **live**.
- Открыта форма AO3 Sort & Filter (search) с непустым списком
  `#exclude_relationship_tags`.

## Сценарий (Given-When-Then)

**Given** приложение запущено live, открыта форма Sort & Filter AO3 с
раскрытым списком relationship-тегов exclude-фильтра, ни один пункт не
отмечен

**When** пользователь отмечает РОВНО ОДИН чекбокс из
`#exclude_relationship_tags` (не инжектированный)

**Then** первым пунктом списка `#exclude_relationship_tags` присутствует
инжектированный чекбокс `[data-ao3-excl-main-pairing-cb]` с подписью "Main
pairing only", и он ВКЛЮЧЁН (`disabled=false`)
**And** снятие единственной отметки (0 отмечено) или отметка ВТОРОГО
relationship-чекбокса возвращает `[data-ao3-excl-main-pairing-cb]` в
отключённое состояние (`disabled=true`, opacity 0.4)

**Инвариант:** доступность чекбокса — функция ТОЛЬКО количества отмеченных
(не инжектированных) relationship-чекбоксов EXCLUDE-списка (`detectExcludedShip`
требует ровно 1), симметрично TC-078/079 для include-списка, но независимый
DOM-узел (`#exclude_relationship_tags` ≠ `#include_relationship_tags`).

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Форма | реальная AO3 Sort & Filter (search), список `#exclude_relationship_tags` |
| Селектор | `[data-ao3-excl-main-pairing-cb]` (пока отсутствует в `selectors.py`) |

## Заметки для автоматизации
- Отдельный DOM-узел от TC-078/079 (include-фильтр) — оба §9-якоря
  (`bridge-main-pairing-filter` / `bridge-exclude-main-pairing-filter`)
  требуют СВОИХ кейсов для снятия needs-design (не покрывается одним тестом
  на include-версию).
- Селектор `[data-ao3-excl-main-pairing-cb]` пока не в `selectors.py` —
  добавить при кодировании.
- Маркер: `@pytest.mark.p0 @pytest.mark.live`.
- **GPU-конфиг live-прогона (AT-BUG-021, решение Lead 2026-07-19):**
  live-прогон только под `AO3_EMU_GPU=host` — полная заметка и
  обоснование в TC-078 (тот же live-путь `/tags/Fluff/works`);
  краш под дефолтом сверять с `bugs/AT-BUG-021.md`, не новая находка.
- Сиблинг-кейс TC-081 — тот же контракт в replay.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
