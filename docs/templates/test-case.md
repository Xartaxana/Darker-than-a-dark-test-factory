---
id: TC-000            # уникальный, никогда не переиспользуется
title: Краткое название сценария   # от ОЖИДАЕМОГО поведения («делает X» / «НЕ делает X» по спецификации),
                                   # не от дефекта сборки — в т.ч. у ожидаемо-красных замков; красный факт
                                   # живёт в Then/заметках (фидбек оператора 2026-08-01, прецедент TC-139)
area: rating          # rating | visibility | tabs | library | downloads | filter-profiles | backup | settings | errors | canary
priority: P1          # P0 | P1 | P2 | P3
risk: R-04            # ссылка на риск из docs/01 §5 (если есть)
status: Draft         # Draft | Review | Approved | Automated (+ Merged — ставится ТОЛЬКО переходом Lead/human, не при создании кейса)
automated_by: ""      # путь к тесту + имя функции, заполняет test-automator
automation_status: "" # B3, только при Automated: active | quarantined | needs_maintenance | deprecated | retired (машина automation в schemas/transitions.yaml)
quarantine_reason: "" # обязателен при quarantined (иначе ERROR валидатора)
quarantine_since: ""  # ISO-время входа в карантин; обязателен при quarantined
quarantine_expiry: "" # дедлайн карантина; пусто = quarantine_since + sla.quarantine_max
quarantine_owner: ""  # кто выводит из карантина (обычно test-maintainer)
merged_into: ""       # П1 spec-p1-dedup v7: TC-id кейса, поглотившего этот дубль — ТОЛЬКО при status: Merged (двустороннее правило validate_frontmatter)
layer: ""             # П2 spec-p2-pyramid v4: L2 (bridge) | L3 (e2e-replay) | L4 (e2e-live) | L5 (manual-agent+exploratory); F1 требует непусто + "почему не L2" для L3/L4 — см. docs/01-test-strategy.md §3
requirements: "PROJECT.md §Screens/Browser"   # источник требования
features: []           # id из docs/feature-registry.yaml (список, можно несколько)
blocked_reason: ""    # environment | missing_fixture | product_decision | dev_answer | permissions — заполнить при status: Blocked (docs/06 B5)
lock: ""              # агент:timestamp — ставит оркестратор
---

# TC-000 — {Название}

## Предусловия
- Состояние приложения (чистое / seed `seeds/<name>.json`), режим (replay/live),
  какая страница/экран открыты.

## Сценарий (Given-When-Then)

**Given** приложение запущено с чистыми данными и открыта страница работы `/works/{id}`
**And** панель рейтинга раскрыта

**When** пользователь нажимает рейтинг «Loved»

**Then** рейтинг сохранён: бейдж «Loved» появляется на странице без перезагрузки
**And** работа отображается во вкладке Loved экрана Library

## Проверяемые данные
| Параметр | Значение |
|---|---|
| Работа | ao3_id из `data/works.py` |

## Заметки для автоматизации
- Какие шаги/экраны фреймворка использовать, известные подводные камни.

## Чекпойнты
<!-- ТОЛЬКО для journey-TC (П1 spec-p1-dedup v7 — несколько поглощённых
     кейсов слиты в один тест). Нумерованный список — машинно читаемая
     форма (validate_frontmatter.py считает пункты). Не-journey кейс эту
     секцию не несёт вовсе. -->
1. {первый чекпойнт: Given/When/Then одной строкой}
2. {второй чекпойнт; пересидинг между чекпойнтами — легален и не считается
   «другой фикстурой», если стоимость Given не меняется}

## Красная проба (red_probe, ретрофит — {дата первой пробы, если применимо})
<!-- Строки `- проба: …` — машинный носитель (validate_frontmatter.py):
     их число обязано быть >= числу пунктов «## Чекпойнты» при
     status: Automated. Заголовок матчится ПРЕФИКСОМ «## Красная проба» —
     суффикс в скобках можно менять свободно. -->
- проба: {чекпойнт N — что портили, как убедились, что тест падает}

## Чек-лист качества (test-designer проходит перед `Review`)
- [ ] Один сценарий — один кейс; нет «и ещё проверить...»
- [ ] Given описывает полное состояние, воспроизводимое фикстурами
- [ ] Then проверяет наблюдаемое поведение, а не реализацию
- [ ] Заголовок сформулирован от ожидаемого поведения, не от дефекта сборки
      (ожидаемо-красный замок — тоже: «НЕ делает X», факт красноты — в Then)
- [ ] Указаны приоритет, область и источник требования
- [ ] Кейс независим от порядка выполнения других кейсов
