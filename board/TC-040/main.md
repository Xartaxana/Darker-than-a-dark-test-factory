---
key: "TC-040"
project: "AO3"
issueType: "test-case"
status: "tc-awaiting-review"
priority: "p1"
summary: "Save filter сохраняет текущий запрос AO3 Sort&Filter под именем"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["test-case", "area:filter-profiles", "risk:R-09"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-19T01:52:00Z"
updated: "2026-07-19T01:52:00Z"
archived: false
resolution: null
---

# Save filter сохраняет текущий запрос AO3 Sort&Filter под именем

_Спроецировано из `test-cases/filter-profiles/TC-040.md` (источник правды).
Статус в нашей машине: **Approved**._

# TC-040 — Сохранение фильтр-профиля из формы AO3 Sort&Filter

## Предусловия
- Приложение запущено с чистыми данными (нет сохранённых `FilterProfile`).
- Открыта страница AO3 с формой Sort & Filter (напр. tag browse или search,
  replay-запись), в форму внесены произвольные значения (напр. word count min),
  форма не отправлена.

## Сценарий (Given-When-Then)

**Given** открыта форма Sort & Filter AO3 с заданными значениями полей, рядом с
кнопкой отправки формы виден инжектированный "Save filter" (JS)

**When** пользователь нажимает "Save filter", в появившемся диалоге вводит имя
"My saved search" и подтверждает

**Then** сохраняется `FilterProfile` с этим именем и `queryString`, соответствующим
текущим значениям формы (`work_search[…]` параметры)
**And** новый профиль появляется в списке сохранённых фильтров в Settings ("Filters")
с указанным именем

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Форма | Sort & Filter AO3, replay-страница с валидной разметкой формы |
| Имя профиля | "My saved search" |

## Заметки для автоматизации
- Требует replay-записи страницы с формой Sort & Filter в исходной разметке AO3 (не
  синтетической) — селекторы инжекции кнопки зависят от реального DOM формы, риск
  R-02 (bridge/DOM) косвенно пересекается здесь, но основной риск кейса —
  корректность сохранения/применения, не факт инъекции кнопки (это ближе к canary).
- `queryString` — URL-encoded, не проверяется напрямую в UI-тесте посимвольно;
  косвенная проверка через TC-041 (применение сохранённого профиля даёт тот же
  результат фильтрации).
- Риск R-09 предложен test-designer, не в матрице §5 — см. §10 docs/01, ждёт решения
  человека.

## Чек-лист качества (test-designer проходит перед `Review`)
- [x] Один сценарий — один кейс; нет «и ещё проверить...»
- [x] Given описывает полное состояние, воспроизводимое фикстурами
- [x] Then проверяет наблюдаемое поведение, а не реализацию
- [x] Указаны приоритет, область и источник требования
- [x] Кейс независим от порядка выполнения других кейсов

## Разблокировано (test-maintainer, 2026-07-19, B4)

Было заблокировано `bugs/AT-BUG-016.md` (test_debt, broken_environment,
major) — детерминированный краш qemu (`0xc0000005`)/зависание при
переходе в Settings после сохранения фильтра. Два ремедиационных захода
(2026-07-19, попытка 1 — дождаться пост-save навигации; попытка 2 —
self-contained первая живая страница) сняли причину частично, но не
дали 3 зелёных подряд.

**Попытка 3 (2026-07-19, critic-directed, ЗАКРЫЛА долг):** довела
`sort_filter_form.mitm` до полной изоляции — записан ВТОРОЙ
self-contained flow для пост-save навигации (`work_search[sort_column]
=revised_at&work_search[words_from]=1000`, URL выведен детерминированно
статическим разбором записанной разметки `#work-filters` + JS-логики
`ao3_bridge.js::injectSaveFilterButton`, подтверждён диагностическим
mitm-addon-логом: `is_replay=response` для обеих live-страниц, ни
одного forward). После этого краш qemu ни разу не воспроизвёлся — но
вскрылась ВТОРАЯ, ранее не диагностированная причина исходной
нестабильности: усечение `<link rel=stylesheet>` (self-contained
truncation) снимает и CSS-скрытие, на которое полагается
`framework/screens/navigation.py::_find_pill` («самый нижний
кликабельный не-WebView View») — без внешней CSS `.narrow-hidden`
(форма `#work-filters`) и `.dropdown .menu` (выпадающие подменю хедера)
рендерятся развёрнуто, `_find_pill` подбирает ссылку ВНУТРИ WebView
(напр. `/people/search`) вместо нативной ручки-пилюли и кликает по ней
— реальная live-навигация уводит WebView с ожидаемой страницы.
Восстановлено минимальным inline `<style>` в теле обоих flow
(`.narrow-hidden, .hidden, .dropdown .menu { display: none !important; }`)
— без единого сетевого запроса, точное соответствие исходному поведению
живого AO3 (форма и так скрыта CSS на узких вьюпортах в реальности).

DoD выполнен: TC-040 3 зелёных подряд (`PYTEST_EXIT=0` ×3,
`Get-Device: DEVICE` перед каждым), TC-041 регрессия зелёная,
`@pytest.mark.skip` снят, `automated_by` заполнен ниже. `status`
намеренно НЕ переведён в `Automated` этим ходом — по
`schemas/transitions.yaml` (Approved→Automated легален только
`by: [test-reviewer]`, `effects: [automated_by_required]`) это следующий
шаг test-reviewer, не test-maintainer.
