---
id: AT-BUG-097
title: "framework/web/base_page.py::contrast_of() оракул контраста даёт ложнокрасные вердикты: фантомный color у icon-only элементов (D1) + захардкоженный белый fallback фона в тёмной теме (D2) — блокирует automation-приёмку TC-149"
type: test_debt
debt_kind: broken_oracle
severity: major
status: Open
found_in: "lead (p3-n4-tc149-contrast-triage, вердикт триажа 2026-08-21), TC-149 (Red вне контроля test-automator), стек 1 (api34, chromedriver новый) и стек 2 (api29, WebView 74), Appium, APK dev-local vc12, 2026-08-21"
fixed_in: ""
last_seen_in: ""
test_cases: ["TC-149"]
runs: []
duplicates: []
regression_of: ""
status_since: "2026-08-21T15:00:00Z"
updated: "2026-08-21T15:00:00Z"
reopen_count: 0
dispute_count: 0
awaiting: none
resolution: ""
resolution_comment: ""
known_issue: "false"
blocked_reason: ""
lock: ""
gitlab_issue: ""
---

# AT-BUG-097 — `contrast_of()` оракул контраста даёт ложнокрасные вердикты на ДВУХ независимых дефектах: фантомный color + захардкоженный белый fallback

## Окружение

- Стеки 1 и 2: api34 (новый chromedriver) и api29 (WebView 74, стек 2);
  Appium; APK dev-local versionCode 12.
- Поверхность: `framework/web/base_page.py::contrast_of()` (:98-112) и
  инжектированный JS `_CONTRAST_OF_ELEMENT_JS` (:47-96) — вычисление
  WCAG-контраста DOM-узла по getComputedStyle, используется TC-149
  `test_computed_contrast_holds_wcag_threshold_light_and_dark`.
- Долг тестовой системы (`type: test_debt`, `debt_kind: broken_oracle`) —
  дефекты оракула, не логики теста/кейса.

## Суть долга

Оракул контраста `contrast_of` содержит ДВА независимых дефекта, которые
порождают ложнокрасные вердикты на РАЗНЫХ узлах в РАЗНЫХ средах:

### D1 — Фантомный `color` у icon-only элементов (строки ~74-75)

Оракул вытягивает `getComputedStyle(el).color` БЕЗ проверки, есть ли у элемента
фактическое текстовое содержимое:

```javascript
// framework/web/base_page.py:74-75
var cs = window.getComputedStyle(el);
var fg = parseColor(cs.color);
```

На icon-only элементах (SVG/иконка, текста нет) вычисленный `color` **не
рендерится как текст вообще** — браузер вычисляет его, но он не участвует в
отрисовке. Сравнение такого «фантомного» `color` с фоном дёт бессмысленный
ratio.

Экземпляр: API29 (стек 2, WebView 74) листинг×Dark инжектированные
Rate-бейдж и Note-кнопка держат вычисленный фантомный color, в то время как
реально видимые их SVG-иконки используют другие цвета (BADGE-палитра
`ao3_bridge.js`). Allure witness в `test-cases/browser/TC-149.md` — см.
прогон TC-149 при автоматизации.

### D2 — Захардкоженный белый fallback фона (строки ~62-69)

Подъём по предкам в поисках непрозрачного `background-color` завершается
безусловным fallback'ом на белый:

```javascript
// framework/web/base_page.py:62-69
function effectiveBackground(node) {
    while (node) {
        var bg = parseColor(window.getComputedStyle(node).backgroundColor);
        if (bg && bg.a > 0) return bg;
        node = node.parentElement;
    }
    return {r: 255, g: 255, b: 255, a: 1};  // ← захардкоженный белый
}
```

В тёмной теме, когда фон канвы фактически тёмный (отрисован движком/мостом или
глобальным стилем, а не явным CSS-предком в DOM-дереве), подъём завершается
`null`-значением и fallback лжёт, возвращая белый → ratio становится 1.00
(«белое-на-белом»).

Экземпляр: API34 work×Dark `h2.title.heading` и `.wrapper > p`:
- Вычисленный `color=rgb(255,255,255)` (белый текст, корректно)
- Эффективный фон `effective_bg=rgba(255,255,255,1)` (белый, **НЕВЕРНО** — должен быть тёмный)
- Ratio = 1.00 (ниже любого порога), но это ложь: текст видим на тёмном фоне страницы

Allure ID: `53a1e47f-dfe9-4353-ac83-b72d369a19f7`, attachment
«TC-149 замеры контраста (все точки маршрута × обе темы)» — строки Dark:

```
work-страница×Dark: заголовок (h2.title.heading): ratio=1.00 (порог 3) 
  color=rgb(255, 255, 255) effective_bg=rgba(255, 255, 255, 1) fontSize=24.0px bold=True
work-страница×Dark: первый абзац тела (.wrapper > p): ratio=1.00 (порог 4.5) 
  color=rgb(255, 255, 255) effective_bg=rgba(255, 255, 255, 1) fontSize=16.0px
```

## Влияние

TC-149 стабильно красный в **ОБЕИХ** средах (api29/WebView74 и api34), но на
**РАЗНЫХ узлах** — красным управляет оракул, не продукт. Ложнокрасные вердикты
**блокируют automation-приёмку TC-149**: поле `automated_by` кейса не может быть
заполнено, так как оракул физически не валиден.

**Опровержение продуктового кандидата:** на основе прямого свидетеля TC-048
(luma-оракул, AT-BUG-096/AT-BUG-095 перед ним закрыты) на стеке 2 api29:
`1 passed in 37.09s` (журнал 13:13 прогона). Тёмная тема **работает корректно** на
WebView<76 — продуктовый дефект «тёмная тема не темнит веб-контент»
**ОПРОВЕРГНУТ**. Красный TC-149 — чистый дефект оракула, не приложения.

## Ожидание после фикса

1. **D1**: Проверка контраста выполняется **только для элементов с фактическим
   текстовым содержимым** (отсутствие text nodes → skip с логом, не ложный
   ratio). Альтернатива: явный список селекторов icon-only (rate/note-кнопки),
   которые исключены из оракула по конструкции.

2. **D2**: Эффективный фон **без белого вранья** — например: (а) замер
   фактического фона канвы/viewport-luma подложка; (б) явный маркер в коде
   страницы о том, что фон задан неявно; (в) fallback на другой механизм
   (например, screenshot-luma фона узла). Ложный белый fallback недопустим.

Ожидание: TC-149 **зелёный в обеих средах** (api29 и api34) по реальным
контраст-данным, без ложных белых.

## Связи

- **AT-BUG-095** (`framework/core/mitm.py::is_ca_installed()` смотрит только в
  APEX-стор, ложный CA-чек на стеке 2) — соседний блокер TC-149, той же
  семьи, иной слой (test_debt, broken_environment). Статус: **Fixed**.

- **AT-BUG-096** (`contrast_of()` передаёт WebElement аргументом в
  execute_script, chromedriver=74 не резолвит как Element) — соседний
  блокер TC-149, той же семьи, иной дефект. Оракул был **недостижим**
  (`JavascriptException` до первого ассерта). Статус: **Fixed** (переписан
  на CSS-селектор).

- **TC-149**: `test_computed_contrast_holds_wcag_threshold_light_and_dark`
  (`tests/test_accessibility.py:290`, allure.id="TC-149") — единственный
  потребитель `contrast_of()`, Red из-за ложных вердиктов D1/D2.

## Критерий готовности (для test-maintainer — fix не твоя задача)

- [ ] Оракул контраста `contrast_of()` резолвит **ТОЛЬКО узлы с текстовым
      содержимым** (D1) — icon-only элементы (rate-бейдж, note-кнопка)
      либо исключены, либо явно помечены с skip-логом, либо проверяется
      наличие text nodes перед вытягиванием `color`.

- [ ] Эффективный фон **не берёт захардкоженный белый fallback** (D2) —
      фактический фон канвы резолвится через читаемый механизм (snapshot
      effectiveBackground отличается от чистого rgba(255,255,255,1) в
      тёмной теме).

- [ ] Живой прогон TC-149 (`@pytest.mark.replay`) на **ОБОИХ стеках**
      (api29 + api34) доходит до и проходит финальный Then-ассерт
      (`assert_all_nodes_meet_contrast_threshold`) с реальными
      контраст-данными (ratio > threshold для ВСЕХ узлов ОБЕИХ тем).

- [ ] Листинг×Light и листинг×Dark: Rate/Note-кнопки держат пороги (если на
      них есть фактический текст или явный механизм проверки icon-only).

- [ ] Work×Light и work×Dark: `h2.title.heading`/`.wrapper > p` держат пороги
      без ложного белого fallback в тёмной теме.

## Верификация (заполняет fix-verifier)

| Дата | Версия сборки | Стеки | Результат | Вердикт |
|---|---|---|---|---|
| | | | | |

## Обсуждение

**[Lead @ 2026-08-21T15:00:00Z]** Вердикт триажа p3-n4-tc149-contrast-triage:
TC-149 стабильно красный из-за ДВУх дефектов оракула, опровергнут продуктовый
кандидат. Заведён тест_debt-баг (AT-BUG-097) на дефекты D1 и D2, оба требуют
фикса перед automation-приёмкой. Предшествующие блокеры (AT-BUG-095, AT-BUG-096)
закрыты Fixed; этот — последний в цепочке.

## Чек-лист качества

- [x] Проверены дубликаты среди открытых AT-BUG-* (`contrast_of`, `icon-only`,
      `effective.*background`, захардкоженный fallback) — не найдено; соседние
      AT-BUG-095/096 — иные слои, не дублируют

- [x] Точные цитаты кода (`effectiveBackground` функция строки 62-69,
      `getComputedStyle(el).color` строки 74-75) приложены из
      framework/web/base_page.py:47-112

- [x] Severity обоснована — major: блокирует automation-приёмку P2-кейса
      (TC-149), оракул даёт ложные вердикты на двух независимых дефектах,
      опровергнут продуктовый дефект (тёмная тема работает — доказано TC-048)

- [x] Evidence приложены: allure ID 53a1e47f-dfe9-4353-ac83-b72d369a19f7,
      дословные ratio/color/effectiveBackground выводы из attachment
      TC-149 замеры контраста, прогоны обоих стеков

- [x] Влияние разделено по стекам/узлам: D1 появляется на icon-only, D2 на
      Dark×work-странице (api34), их независимость показана

- [x] Ни одного изменения в `framework/` и `app-under-test/` этим тикетом не
      внесено — только анализ и триаж

- [x] `type: test_debt`, `debt_kind: broken_oracle` — оракульный дефект, не
      окружение и не логика теста

- [x] Взаимные ссылки: AT-BUG-095/096 указаны в разделе «Связи»; обратные
      ссылки (095/096 → 097) не требуются, т.к. 095/096 уже Fixed и
      закоммичены
