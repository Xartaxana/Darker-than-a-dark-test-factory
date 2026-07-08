---
key: "AT-BUG-003"
project: "AO3"
issueType: "bug"
status: "bug-open"
priority: "p2"
summary: "Кейсы, автоматизированные до гейта F1 (TC-007/008/016/017), не несут полей жизненного цикла B3 (automation_status/reviewed_by/reviewed_at)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-007", "test_case:TC-008", "test_case:TC-016", "test_case:TC-017", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-08T15:25:00Z"
updated: "2026-07-08T15:25:00Z"
archived: false
resolution: null
---

# Кейсы, автоматизированные до гейта F1 (TC-007/008/016/017), не несут полей жизненного цикла B3 (automation_status/reviewed_by/reviewed_at)

_Спроецировано из `bugs/AT-BUG-003.md` (источник правды).
Статус в нашей машине: **Open**._

# AT-BUG-003 — Automated-кейсы до гейта F1 без полей жизненного цикла B3

## Окружение
- Не зависит от сборки приложения: долг метаданных тестовой системы
  (`type: test_debt`), найден test-reviewer'ом при F1-ревью батча browser
  (TC-050..055) как класс-аналог (правило 9 CLAUDE.md, доклад по D-0037).

## Суть долга

`test-cases/rating/TC-007.md`, `TC-008.md`, `test-cases/library/TC-016.md`,
`TC-017.md` имеют `status: Automated`, но были автоматизированы «де-факто»
(2026-07-02/03) ДО внедрения гейта F1 и машины automation (B3). В отличие от
кейсов, прошедших гейт (TC-050..055), у них отсутствуют:

1. `automation_status` — кейсы невидимы для правила «Починить автотест в
   карантине/на обслуживании» (B3) и для выборок по automation-машине;
2. `reviewed_by` / `reviewed_at` — нет свидетельства ревью автотеста.

Смоук-кейсы TC-001..005 при проверке тоже сверить: тот же класс «Automated до
гейта» (их тесты чинились по AT-BUG-002 и верифицированы, но поля B3 могли не
проставляться).

## Критерий готовности (Fixed)

- Всем Automated-кейсам без полей B3 проставлен `automation_status`
  (ожидаемо `active` — тесты живут в suite и зелёные), честно: БЕЗ
  фиктивных `reviewed_by`/`reviewed_at`, если F1-ревью фактически не было;
  вместо этого — строка в теле кейса «автоматизирован до гейта F1» либо
  фактическое ревью test-reviewer'ом, если оно проводится.
- `python scripts/validate_frontmatter.py` — 0 ошибок.
- Grep `status: Automated` по test-cases/ не находит кейсов без
  `automation_status`.

## Анализ

Не регрессия, а легализация кейсов, созданных до машины B3 (тот же паттерн,
что AT-BUG-002 для arch_check/C1). Чинит test-maintainer по правилу «Устранить
test debt» (B4); Fixed не ждёт сборку приложения. Решение «бэкфилл пометкой
vs фактическое F1-ревью задним числом» — за исполнителем с докладом Lead.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение

**2026-07-08T15:25:00Z — оркестратор /qa-loop (со слов test-reviewer):** класс
зафиксирован при приёмке F1-ревью TC-050..055; диспатч по B4 — следующим
проходом (слоты текущего отданы скоупу оператора: автоматизация
downloads/rating).
