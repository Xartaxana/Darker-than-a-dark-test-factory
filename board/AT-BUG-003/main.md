---
key: "AT-BUG-003"
project: "AO3"
issueType: "bug"
status: "bug-verified"
priority: "p2"
summary: "Кейсы, автоматизированные до гейта F1 (TC-007/008/016/017), не несут полей жизненного цикла B3 (automation_status/reviewed_by/reviewed_at)"
assignee: "qa-agents"
reporter: "qa-agents"
labels: ["bug", "test_case:TC-001", "test_case:TC-002", "test_case:TC-003", "test_case:TC-004", "test_case:TC-005", "test_case:TC-007", "test_case:TC-008", "test_case:TC-016", "test_case:TC-017", "sev:minor"]
components: []
fixVersions: []
watchers: []
parent: null
epic: null
created: "2026-07-09T10:35:00Z"
updated: "2026-07-09T10:35:00Z"
archived: false
resolution: "done"
---

# Кейсы, автоматизированные до гейта F1 (TC-007/008/016/017), не несут полей жизненного цикла B3 (automation_status/reviewed_by/reviewed_at)

_Спроецировано из `bugs/AT-BUG-003.md` (источник правды).
Статус в нашей машине: **Verified**._

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
| 2026-07-09T10:35:00Z | n/a, test_debt (метаданные, сборка приложения не участвует) | TC-001..005, TC-007, TC-008, TC-016, TC-017 (все 9 из test_cases бага) + полный проход по test-cases/ для класса «Automated без automation_status» | (1) `python scripts/validate_frontmatter.py` → "validate_frontmatter: ошибок 0, предупреждений 0"; (2) grep `^status: Automated` по test-cases/**/*.md → ровно 15 файлов (9 из бага + TC-050..055 browser, не тронутые бэкфиллом); (3) grep `^automation_status:` по test-cases/**/*.md → те же 15 файлов, у всех `active`, множества совпадают 1:1 (0 Automated-кейсов без automation_status) | Все 3 пункта критерия готовности подтверждены независимо → Verified |

## Обсуждение

**2026-07-08T15:25:00Z — оркестратор /qa-loop (со слов test-reviewer):** класс
зафиксирован при приёмке F1-ревью TC-050..055; диспатч по B4 — следующим
проходом (слоты текущего отданы скоупу оператора: автоматизация
downloads/rating).

**2026-07-08T23:20:00Z — test-maintainer (B4):** решение по развилке из
«Анализ» — бэкфилл пометкой, БЕЗ фиктивных `reviewed_by`/`reviewed_at`
(фактического F1-ревью для этих кейсов не было, задним числом не
имитируется). Проставлен `automation_status: active` в frontmatter для
9 кейсов: смоук TC-001..005 (`test-cases/smoke/`), TC-007/TC-008
(`test-cases/rating/`), TC-016/TC-017 (`test-cases/library/`); в тело
каждого добавлена секция «B3-поля» с честной пометкой «автоматизирован до
гейта F1 (B3-поля бэкфилл, ревью задним числом не проводилось)». По правилу
9 CLAUDE.md проверен весь класс: grep `^status: Automated` по test-cases/
даёт ровно 15 файлов — 9 перечисленных выше + TC-050..055 (`test-cases/browser/`),
у которых `automation_status`/`reviewed_by`/`reviewed_at` уже стояли из
штатного F1-прохода (не трогались). Непокрытых Automated-кейсов не осталось.
Смена `status` НЕ производилась ни у одного кейса (только добавление поля
`automation_status`) — по schemas/transitions.yaml машина `automation` имеет
`initial: [active]`, а до бэкфилла поле у этих 9 кейсов отсутствовало вовсе,
т.е. это простановка исходного состояния забытой машины, а не переход
`quarantined→active`/`needs_maintenance→active`, которые закреплены только за
test-maintainer при 3 зелёных прогонах — легально без нарушения матрицы.
`updated` кейсов бампнут (факт правки frontmatter/тела), `status`/`status_since`
кейсов не менялись. Код в `app-under-test/` и логика тестов в `framework/`
не трогались — только frontmatter/тело test-case `.md`. Перевод бага
`Open → Fixed` — guard-переход B4 (`{from: Open, to: Fixed, by:
[test-maintainer, test-automator], guard: {type: test_debt}}`), верифицирует
fix-verifier, сборка приложения не нужна.

**2026-07-09T10:35:00Z — fix-verifier:** независимо перепроверил все 3 пункта
критерия готовности (не на слово отчёту test-maintainer'а):
1. `python scripts/validate_frontmatter.py` → `validate_frontmatter: ошибок 0,
   предупреждений 0` (exit 0).
2. `Select-String -Pattern '^status: Automated'` по `test-cases/**/*.md` →
   ровно 15 файлов: TC-001..005 (smoke), TC-007/TC-008 (rating), TC-016/TC-017
   (library) — 9 из тела бага — плюс TC-050..055 (browser), не входящие в
   scope бага (штатный F1-проход).
3. `Select-String -Pattern '^automation_status:'` по тому же дереву → те же
   15 файлов, у каждого `automation_status: active`. Множества (1) и (2)
   совпадают 1:1 — Automated-кейсов без `automation_status` не осталось.
Переход `Fixed → Verified` легален по `schemas/transitions.yaml`
(`{from: Fixed, to: Verified, by: [fix-verifier]}`, guard по type не требуется
для этого перехода). status → `Verified`, лок снят.
