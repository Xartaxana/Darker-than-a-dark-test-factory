# 08 — External architecture review: Darker than a dark test factory

Дата: 2026-07-05  
Роль: внешний ревьюер архитектуры QA-фабрики  
Скоуп: стратегия, архитектура фреймворка, агентная система, roadmap, HANDOFF, dark-factory спецификация, board-inbound, фактическое состояние repo.

## 1. Executive summary

Архитектурное направление выбрано правильно: проект строится не как набор UI-тестов, а как QA-система с собственными артефактами, статусными машинами, агентами, бордой, SLA и обратным каналом от разработчика. Это соответствует современному направлению TestOps / continuous testing / AI-assisted testing / autonomous QA workflows.

Сильные решения:

- артефакты (`test-cases/`, `bugs/`, `runs/`) назначены источником правды;
- борда сделана проекцией + узким обратным каналом, а не вторым источником правды;
- `board_inbound` спроектирован через трехстороннюю сверку с курсором, что правильно решает конфликт "человек изменил борду" vs "агент изменил артефакт";
- стратегия учитывает live/replay режимы и риск нестабильности AO3;
- агенты разделены по ролям, а не свалены в одного "универсального QA";
- матрица D1-D12 покрывает большинство действий разработчика с багами;
- принцип "permission-window = defect" корректен для автономной фабрики.

Главный вывод: базовая архитектура жизнеспособна, но до уровня "человек ушел на день" ей не хватает не столько новых тест-кейсов, сколько исполняемых контрактов вокруг workflow, gating, test lifecycle, observability и самопроверки фабрики.

## 2. Critical findings already identified

Эти пункты были найдены в ревью текущего состояния. Их нужно перенести в отдельные задачи, но они не дублируются ниже как новые предложения.

### A1. Runtime-модель `/qa-loop` противоречит HANDOFF

HANDOFF фиксирует критическую находку: вложенная оркестрация субагентов не работает надежно. Однако текущие skills все еще запускают `qa-orchestrator` как субагента, а тот уже изнутри должен запускать воркеров.

Риск: автономный проход диспатчит только часть работы, оставляет осиротевшие локи и не является настоящим конвейером.

Рекомендация: перенести диспетчеризацию на верхний уровень `/qa-loop`: skill сам читает rules/pre_steps и диспатчит воркеров глубины 1. `qa-orchestrator` оставить планировщиком или удалить из runtime-пути.

### A2. `pre_steps` описаны, но не все исполняемы

В `rules.yaml` есть `stale_locks`, `sla_sweep`, `board_inbound`, `build_watch`. Реально зрелым выглядит только `board_inbound`. `build_watch` остается планом, `state/escalations.md` отсутствует, `attention` в `board_sync` не реализован.

Риск: фабрика описывает самовосстановление и SLA, но в автономном режиме часть зависаний не всплывет.

Рекомендация: сделать `stale_locks`, `sla_sweep`, `build_watch` отдельными идемпотентными скриптами с unit-тестами и единым форматом `state/escalations.md`.

### A3. Окружение тестов не воспроизводимо

Проектный venv не запустился: `framework/.venv/Scripts/python.exe` ссылается на отсутствующий Python, а `python`/`py` не найдены в PATH.

Риск: автономная фабрика не может зависеть от ручного восстановления Python.

Рекомендация: добавить bootstrap/doctor-команду, пересоздание venv или закрепленный portable runtime, и запускать doctor в начале scheduled прохода.

### A4. HANDOFF содержит ручные счетчики очереди

HANDOFF говорит о 41 Approved-кейсе, фактический подсчет frontmatter в момент ревью дал 37 `Approved`, 9 `Automated`, 8 `Review`, 1 `Draft`.

Риск: планирование по тексту расходится с machine-readable state.

Рекомендация: все queue snapshots генерировать скриптом из frontmatter, не вести числа вручную.

## 3. Coverage of bug and task workflows

Текущая матрица D1-D12 хорошо покрывает разработческие действия:

- `Fixed` с новой сборкой;
- `Fixed` без новой сборки;
- новая сборка без перевода бага;
- `Rejected`;
- `Intended`;
- комментарии/вопросы;
- регрессии от фикса;
- reopen/dispute ping-pong;
- изменение поведения без тикета;
- duplicate;
- coalescing нескольких пушей;
- approve тест-кейса через борду.

Что стоит добавить поверх D1-D12:

### B1. Явный workflow "accepted risk / won't fix"

Сейчас есть `Rejected` и `Intended`, но нет отдельного состояния для случая "дефект реален, но владелец сознательно принимает риск / не чинит в этом релизе".

Рекомендация:

- добавить статус или поле `resolution: accepted_risk|wontfix`;
- требовать комментарий человека;
- держать linked TC активными, но не блокировать релизный gate, если риск принят.

### B2. Явный workflow "known issue"

Если баг подтвержден, но релиз идет с ним, фабрика должна уметь:

- оставить баг открытым;
- добавить его в known-issues/digest;
- не заводить дубликаты на каждом прогоне;
- проверять, что баг не ухудшился.

Рекомендация: добавить поле `known_issue: true` и правило дедупликации APP_BUG against known issues.

### B3. Отдельный lifecycle для автотеста

Сейчас lifecycle есть у тест-кейса: `Draft -> Review -> Approved -> Automated`. Но автотест после появления тоже живет: он может быть активным, flaky, quarantined, deprecated, retired, needs-maintenance.

Рекомендация:

- добавить поля `automation_status: active|quarantined|needs_maintenance|deprecated|retired`;
- добавить `quarantine_reason`, `quarantine_since`, `quarantine_owner`, `quarantine_expiry`;
- запретить бесконечный карантин без SLA.

### B4. Отдельный workflow для test debt

Фабрика должна видеть не только баги приложения, но и долг тестовой системы:

- flaky test;
- slow test;
- missing replay fixture;
- weak locator;
- obsolete test case;
- missing evidence;
- broken environment.

Рекомендация: завести артефакт `test-debt/TD-xxx.md` или использовать `bugs/` с типом `test_debt`, чтобы такие проблемы не терялись в HANDOFF.

### B5. Explicit "needs product decision"

Есть `Blocked`, но он слишком общий. Для продуктовых решений полезно отличать:

- blocked by environment;
- blocked by missing fixture;
- blocked by product decision;
- blocked by developer answer;
- blocked by permissions.

Рекомендация: добавить `blocked_reason` enum и использовать его в SLA/digest.

## 4. Test framework architecture review

Текущая архитектура Appium + pytest + Allure + Screen/Page Objects рациональна для black-box Android/WebView приложения, где нельзя менять код приложения.

Что улучшить:

### C1. Добавить executable architecture checks

Документы требуют "tests -> steps -> screens/web -> core", но это пока конвенция.

Рекомендация:

- добавить статический чек импортов;
- запретить прямой `driver` в `tests/` кроме фикстур;
- запретить локаторы в `tests/`;
- проверять наличие `@allure.id` и pytest marker у каждого теста.

### C2. Strengthen evidence contract

Для каждого verdict нужен минимальный evidence pack.

Рекомендация:

| Verdict | Minimum evidence |
|---|---|
| `APP_BUG` | build hash, TC, steps, screenshot, logcat, page source, expected/actual |
| `TEST_BUG` | failing test, root cause in test/framework, fix or debt item |
| `SITE_CHANGED` | live/replay comparison, affected selector/recording |
| `APP_CHANGED` | app commit range, changed behavior, affected TC |
| `ENV_ISSUE` | environment check, retry result, logs |
| `FLAKY` | rerun history, failure signature, quarantine decision |

### C3. Add model/state-machine testing for workflows

Bug, TC, run, board-inbound and SLA flows are state machines. They should be tested as such.

Рекомендация:

- хранить transition matrix в YAML;
- генерировать tests over transitions;
- проверять illegal transitions;
- проверять side effects: `status_since`, lock, escalation, discussion, board cursor.

### C4. Add metamorphic/property checks for high-combinatorics areas

Фильтры, ratings, tabs, backup/restore имеют много комбинаций. Ручные кейсы быстро перестанут масштабироваться.

Рекомендация добавить invariant-based tests:

- работа с рейтингом X видна только в соответствующей вкладке;
- `clear all` очищает все рейтинговые множества;
- backup -> clear -> restore сохраняет множество записей;
- hide disliked никогда не показывает Disliked;
- сортировка не меняет состав множества, только порядок;
- фильтр downloaded-only является подмножеством library.

### C5. Test data contract

Сейчас сидинг Room и replay fixtures критичны. Нужно формализовать test data lifecycle.

Рекомендация:

- каталог fixtures с manifest-файлом;
- версия схемы Room/backup JSON;
- проверка совместимости fixtures при изменении приложения;
- правило: новый тест не принимается без fixture ownership и cleanup strategy.

## 5. Continuous testing and release gates

Современные continuous testing практики сходятся на том, что тесты должны быть частью delivery gate, а не только отчетом.

Что добавить:

### D1. Impact-based test selection

Сейчас правила запускают smoke/regression крупными блоками. Фабрика должна выбирать targeted suite по изменению.

Рекомендация:

- `changed files -> impacted areas -> TC list`;
- `risk score -> suite size`;
- учитывать historical failures и flaky history;
- если impact неизвестен, fallback на broad regression.

Пример:

| Изменение | Запуск |
|---|---|
| `BrowserViewModel`, `ao3_bridge.js` | browser/rating/visibility + canary |
| Room schema / backup code | backup/download/library data suite |
| UI theme/settings | settings + browser overlay controls |
| tests/framework core | full smoke + affected test framework tests |

### D2. External quality gates

Борда удобна для человека, но разработчику нужен машинный gate.

Рекомендация:

- публиковать результат smoke/targeted regression как commit/PR status;
- использовать required checks на protected branch;
- хранить ссылку на run report в status;
- блокировать `Fixed -> Verified`, если build hash не соответствует проверенной сборке.

### D3. Release readiness dashboard

Нужен не только board view, но и release gate summary:

- последняя сборка;
- smoke status;
- targeted regression status;
- open blocker/critical;
- known issues;
- quarantined tests;
- stale locks;
- pending human decisions.

## 6. Non-functional quality gaps

Текущая стратегия сильна функционально, но "команда тестировщиков" обычно закрывает больше, чем функциональные E2E.

Рекомендуемые suites:

### E1. Accessibility smoke

Минимум:

- ключевые controls имеют accessibility labels;
- tappable areas доступны;
- font scaling не ломает основные экраны;
- dark/light contrast sanity.

### E2. Performance and stability smoke

Минимум:

- cold start threshold;
- WebView first meaningful load threshold;
- no ANR/crash in smoke;
- logcat scan for fatal errors;
- memory sanity for long WebView session.

### E3. Compatibility matrix

Минимум:

- API 34 как primary;
- хотя бы один lower API по расписанию;
- portrait/landscape если поддерживается;
- system dark/light.

### E4. Security/privacy canary

Для Android/WebView приложения стоит добавить отдельный smoke:

- exported components sanity;
- cleartext traffic policy;
- WebView dangerous settings;
- file access / downloads path;
- backup/restore privacy;
- cookies/session handling;
- debug-only assumptions.

Ориентир: OWASP MASVS/MSTG как чек-лист, не как полная сертификация.

## 7. Agentic workflow improvements

AI-assisted testing сейчас обычно описывается как closed loop:

1. discover/generate;
2. execute;
3. analyze;
4. repair/optimize;
5. human review only for policy/product decisions.

У проекта это уже есть частично. Что добавить:

### F1. Reviewer/critic role for test changes

Агент, который пишет тест, не должен быть финальным судьей качества своего теста.

Рекомендация:

- добавить `test-reviewer` или режим review у `test-maintainer`;
- проверять архитектурные правила, evidence, fixture quality, flake risk, traceability;
- только после review переводить TC/test в stable automation.

### F2. Agent output schema

Каждый агент должен возвращать machine-readable result:

```yaml
agent: test-automator
artifact: TC-xxx
result: success|blocked|degraded|failed
changed_files: []
evidence: []
next_rules: []
escalations: []
```

Это позволит верхнеуровневому dispatcher не парсить свободный текст.

### F3. Factory self-tests

Нужно тестировать не только приложение, но и фабрику:

- transition matrix tests;
- board inbound/outbound tests;
- SLA sweep tests;
- stale lock tests;
- build watch tests;
- permission audit parser tests;
- dark-day rehearsal as regular regression.

## 8. Documentation/process improvements

### G1. Split "spec" and "current status"

Сейчас HANDOFF содержит факты, планы, итоги, счетчики, known issues. Для автономной фабрики лучше разделить:

- `docs/06-dark-factory.md` — target spec;
- `docs/04-roadmap.md` — implementation plan;
- `state/factory-status.md` или generated status — текущая очередь;
- `docs/HANDOFF.md` — только resume notes and critical context.

### G2. Make roadmap actionable

В roadmap нужно добавить для каждого пункта:

- owner agent;
- input artifacts;
- output artifacts;
- exit criteria;
- tests;
- rollback/degradation behavior.

### G3. Add schemas for frontmatter

Рекомендация:

- `schemas/test-case.schema.yaml`;
- `schemas/bug.schema.yaml`;
- `schemas/run.schema.yaml`;
- `schemas/rules.schema.yaml`;
- validation script in CI/qa-loop preflight.

## 9. Suggested priority order

Не повторяя детали A1-A4, общий порядок такой:

1. Исправить runtime-модель оркестрации.
2. Сделать executable `pre_steps`.
3. Зафиксировать Python/test runtime reproducibility.
4. Добавить machine-readable transition matrix для bug/TC/run.
5. Добавить test lifecycle (`automation_status`, quarantine, retired/deprecated).
6. Добавить evidence contract для verdicts.
7. Добавить factory self-tests.
8. Добавить impact-based test selection.
9. Добавить non-functional suites: accessibility, performance, compatibility, security.
10. Добавить external quality gates для PR/commit/build.

## 10. Reference practices checked

Внешние ориентиры, по которым сверялась архитектура:

- Martin Fowler, Practical Test Pyramid — баланс уровней тестирования и риск UI-heavy suite.
  https://martinfowler.com/articles/practical-test-pyramid.html
- Android Developers, testing fundamentals — уровни и типы Android testing.
  https://developer.android.com/training/testing/fundamentals
- Google Testing Blog, flaky tests — flaky как отдельный управляемый класс риска.
  https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- DORA metrics / continuous delivery practices — качество как delivery capability.
  https://dora.dev/guides/dora-metrics/
- GitHub protected branches / required status checks — machine gates для delivery.
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- OWASP MASVS/MSTG — ориентир для mobile security/privacy checks.
  https://mas.owasp.org/
- Recent agentic / AI-assisted testing literature — closed-loop generate/execute/analyze/repair workflows.
  https://arxiv.org/abs/2601.02454
  https://arxiv.org/abs/2408.06224

## 11. Bottom line

Проект не упустил базовую архитектурную идею. Напротив, в нем уже есть редкая для тестового проекта часть: собственная QA state machine, agent roles, board inbound, replay/live split, SLA и автономность как явное требование.

Главное, что нужно усилить:

- превратить текстовые workflow в executable contracts;
- добавить lifecycle для автотестов и test debt;
- расширить качество за пределы функционального E2E;
- подключить factory self-tests и external quality gates;
- отделить текущий runtime status от долгоживущей спецификации.

После этих изменений фабрика будет ближе не к "набору автотестов с агентами", а к полноценной autonomous quality platform.
