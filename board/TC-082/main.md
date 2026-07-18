---
key: "TC-082"
project: "AO3"
issueType: "test-case"
status: "tc-approved"
priority: "p0"
summary: "Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (live)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:canary", "risk:R-02"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-18T09:15:17Z"
updated: "2026-07-18T09:15:17Z"
archived: false
resolution: null
---

# Кнопка 'Save filter' инжектируется рядом с submit формы Sort&Filter и не дублируется при повторных мутациях формы (live)

_Спроецировано из `test-cases/canary/TC-082.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-082 — Save filter button: инъекция + идемпотентность (live)

## Предусловия
- Приложение запущено с чистыми данными, режим **live**.
- Открыта форма AO3 Sort & Filter (search/tag browse), форма ещё скрыта
  (AO3 показывает её по клику toggle-ссылки).

## Сценарий (Given-When-Then)

**Given** приложение запущено live, страница с формой Sort & Filter
загружена, форма изначально скрыта

**When** пользователь раскрывает форму (клик по toggle-ссылке AO3, класс/
стиль `#work-filters` меняется — срабатывает `MutationObserver`)

**Then** сразу после submit-кнопки формы (`input[name="commit"][type="submit"]`)
появляется РОВНО ОДНА кнопка `[data-ao3-save-profile]` с текстом "Save filter"
**And** повторное скрытие/раскрытие формы (ещё один toggle, повторный вызов
`injectSaveFilterButton` через `MutationObserver`) НЕ создаёт вторую кнопку —
элемент остаётся ровно один

**Инвариант:** идемпотентность инъекции — свойство, верное для ЛЮБОГО числа
срабатываний `MutationObserver`/повторных вызовов `injectSaveFilterButton`
(guard `|| document.querySelector('[data-ao3-save-profile]')) return`), не
факт «кнопка появилась один раз при одном конкретном клике».

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Форма | реальная AO3 Sort & Filter (search/tag browse) |
| Селектор | `[data-ao3-save-profile]` (`framework/web/selectors.py::SAVE_PROFILE_BTN`) |

## Заметки для автоматизации
- Не дублирует TC-040 (функциональность: клик сохраняет `FilterProfile` с
  именем) — здесь предмет проверки СЕЛЕКТОР/идемпотентность инъекции кнопки,
  а не факт сохранения. TC-040 сам отмечает эту границу («это ближе к
  canary») — данный кейс закрывает её.
- Маркер: `@pytest.mark.p0 @pytest.mark.live`.
- Сиблинг-кейс TC-083 — тот же контракт в replay
  (`sort_filter_form.mitm`, уже Verified в AT-BUG-006, где сам факт инъекции
  кнопки в этой записи уже был зафиксирован вручную test-maintainer'ом —
  этот кейс формализует ту находку регрессионным тестом).
- DoD-блок §9 явно отмечает: у «save profile controls» пока нет ОТДЕЛЬНОГО
  якоря-метки needs-design (в отличие от main-pairing/exclude) — этот кейс
  закрывает контрактный пункт docs/10 P3, не привязываясь к несуществующей
  метке; см. итоговый отчёт test-designer.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов
- [x] Кейс комбинаторной области называет инвариант строкой `Инвариант: …`
