# 10 — External quality review: Darker than a dark test factory

Дата: 2026-07-13  
Роль: сторонний ревьюер архитектуры и качества тестирования  
Скоуп: стратегия, roadmap, dark-factory спецификация, агентный workflow, текущий статус фабрики, traceability, test debt и фактическая очередь.

## 1. Краткий вердикт

Архитектурное направление выбрано правильно. Проект уже строится не как набор
автотестов, а как автономная QA-система: есть артефакты как source of truth,
агенты, status machine, SLA, борда, test debt, evidence contract, agent output
schema и отдельный reviewer-gate для новых автотестов.

Главный риск сейчас не в оркестрации. После доработок docs/09 базовый runtime
стал значительно зрелее: pre_steps, transitions, evidence, test-reviewer и
test debt уже описаны и частично реализованы. Главный риск сместился в другую
область: фабрика пока лучше автоматизирует QA-процесс, чем доказывает полноту и
силу самого тестирования.

Для цели "пришёл проект, фабрика сама построила все необходимые тесты и не
пропускает баги" нужно усилить три слоя:

- project intake / discovery: как фабрика понимает новый продукт;
- coverage model: как она доказывает, что функции, риски и сценарии покрыты;
- test effectiveness: как она измеряет, что тесты реально ловят дефекты.

Абсолютно "не пропускать багов" невозможно гарантировать инженерно. Но можно
строить фабрику так, чтобы она измеряла escape rate, проверяла силу тестов через
seeded defects, закрывала риски traceability-графом и не разрешала "зелёный"
статус без свежего evidence по критичным областям.

## 2. Что уже хорошо

### 2.1. Правильная модель QA-фабрики

Сильное решение: `test-cases/`, `bugs/`, `runs/` и `state/` являются
операционными артефактами, а не просто документацией. Это даёт фабрике память,
очередь, SLA и возможность работать без постоянного человека.

Сильные элементы:

- file-based source of truth;
- board как проекция, а не второй источник истины;
- status transitions как исполняемый контракт;
- lock/stale-lock модель;
- отдельные роли агентов;
- triage verdicts;
- test debt как первоклассный тип проблемы;
- evidence contract для verdicts;
- machine-readable `agent_output`;
- reviewer-gate F1 для автотестов.

Это правильный фундамент для Dark Factory.

### 2.2. Хороший риск-ориентированный старт

Стратегия уже выделяет реальные риски AO3 Reader:

- потеря локальных данных;
- рассинхронизация Room и WebView-бейджей;
- изменения DOM AO3;
- Cloudflare/live нестабильность;
- фильтрация и сортировка;
- tabs lifecycle;
- темы, шрифт, яркость, side panel.

Разделение live/replay также корректно: live нужен для canary и smoke, replay —
для детерминированной регрессии.

### 2.3. Архитектура фреймворка адекватна ограничениям

Для black-box Android/WebView приложения без права менять код приложения выбор
Appium + UiAutomator2 + pytest + Allure + mitmproxy рационален.

Слои `tests -> steps -> screens/web -> core -> config` и запрет локаторов в
тестах — правильные. Важно, что это уже поддержано архитектурными self-tests,
а не только описано в документе.

### 2.4. Фабрика начала тестировать саму себя

Наличие `scripts/tests/` для transitions, evidence, board sync/inbound,
frontmatter validation, stale locks, sla sweep, permission audit и arch check —
это важный признак зрелости. У автономной QA-фабрики self-tests должны быть
равноправной частью продукта.

## 3. Главные проблемы и риски

### P1. Runtime зрелый, но качество покрытия ещё не доказано

Текущий статус показывает 58 тест-кейсов, из них 21 Automated. Smoke прошёл,
но regression имеет статус `not_run`. Для фабрики, которая должна давать
качество продукта, это критичный сигнал: процесс уже богатый, но свежая
полная проверка качества ещё не является регулярной нормой.

Рекомендация:

- сделать регулярный regression обязательным gate;
- хранить freshness полного regression в release-readiness summary;
- запретить "готово к релизу", если последний regression устарел или не запускался;
- вывести отдельную метрику `regression_freshness_hours`.

### P2. P0 coverage всё ещё имеет дыры

В P0 остаются кейсы, связанные с listing/visibility и backup, которые не доведены
до полной автоматизации. Для продукта с локальными данными и WebView-инъекцией
это высокорисковые зоны.

Рекомендация:

- поставить закрытие P0 automation gaps выше расширения P2/P3;
- довести replay fixtures для listing/visibility;
- закрыть SAF/backup test debt или явно описать альтернативный deterministic
  путь тестирования backup/restore;
- считать P0 неполным, пока все P0 не имеют свежий зелёный run.

### P3. Canary suite отсутствует как исполняемый датчик

В стратегии canary заявлен как защита от изменения DOM AO3, но в `rules.yaml`
ежедневный canary пока закомментирован, потому что suite ещё не существует.
Для WebView-обёртки это не второстепенная функция, а ранний датчик поломки
основного контракта.

Рекомендация:

- создать `framework/tests/canary/test_ao3_selectors.py`;
- проверять минимальный контракт bridge: work blurb, work id, rating button,
  note button, badge, filter/save profile controls;
- разделить canary на live DOM contract и replay contract;
- включить дневной canary в schedule только после зелёного baseline.

### P4. Нет полноценного Project Intake слоя

Текущая фабрика хорошо описана для AO3 Reader, но цель проекта шире: фабрика
должна уметь принимать новый проект и строить QA-процесс почти сама. Сейчас не
хватает явного workflow "новый проект -> карта продукта -> риск-модель ->
coverage graph -> тестовая стратегия -> наборы тестов".

Рекомендация: добавить отдельную фазу и агентов intake/discovery.

Предлагаемые роли:

- `project-scout`: строит карту продукта: экраны, API, данные, роли, интеграции,
  permissions, storage, background jobs, critical flows.
- `risk-modeler`: превращает карту продукта в risk register и severity model.
- `coverage-planner`: строит feature/risk/requirement coverage graph.
- `testability-reviewer`: оценивает test hooks, fixtures, logs, deterministic data,
  observability и предлагает изменения разработчикам.
- `exploratory-tester`: планирует и исполняет exploratory charters.
- `mutation/fault-injection agent`: проверяет силу тестов через seeded defects.

### P5. Coverage сейчас больше кейс-ориентированный, чем модельный

Given-When-Then кейсы полезны, но для сложных областей ручной список кейсов не
докажет полноту. Фильтры, сортировки, рейтинги, backup/restore и tabs имеют
комбинаторный характер. Их лучше проверять инвариантами.

Рекомендация: добавить property/metamorphic слой.

Инварианты:

- сортировка не меняет множество работ, только порядок;
- фильтр downloaded-only даёт подмножество Library;
- hide disliked никогда не показывает Disliked;
- work с рейтингом X виден только в соответствующей вкладке;
- clear all очищает все рейтинговые множества;
- backup -> clear -> restore сохраняет множество записей и ключевые поля;
- изменение темы не меняет URL, активную вкладку и сохранённые данные;
- undo закрытия таба восстанавливает URL, scroll и позицию.

### P6. Нет измерения силы тестов

Pass rate показывает только то, что тесты не падают. Он не показывает, что тесты
ловят баги. Для "не пропускать баги" нужна проверка эффективности.

Рекомендация:

- для white-box проектов добавить mutation score;
- для black-box проектов добавить seeded defects/fault injection;
- регулярно запускать controlled defect rehearsal: испорченный replay DOM,
  corrupted backup, stale DB schema, network timeout, broken selector, missing
  file, wrong rating mapping;
- считать `seeded_defect_kill_rate`.

### P7. Exploratory testing пока не является первоклассным артефактом

Фабрика должна выполнять функции команды тестировщиков. Команда тестировщиков
делает не только scripted regression, но и exploratory testing.

Рекомендация:

- добавить каталог `exploratory-charters/`;
- описать шаблон charter: mission, scope, risks, heuristics, data setup,
  observations, found bugs, follow-up TC;
- добавить агента `exploratory-tester`;
- запускать exploratory pass при новой крупной функции, после APP_CHANGED и
  перед релизом;
- измерять `bugs_per_charter` и `new_tc_from_charters`.

### P8. Non-functional suites нужно поднять выше

В docs/09 уже запланированы accessibility, performance/stability и compatibility.
Это правильное направление. Я бы не откладывал их до поздней эксплуатации:
минимальные smoke checks должны появиться раньше.

Минимум:

- accessibility labels для ключевых controls;
- font scaling на основных экранах;
- contrast sanity для dark/light;
- cold start threshold;
- WebView first load threshold;
- no crash/ANR/logcat fatal в smoke;
- long WebView session memory sanity;
- второй API level по расписанию;
- system dark/light matrix.

### P9. Security/privacy canary зря полностью отклонён

Полная security сертификация может быть вне скоупа. Но для Android/WebView
приложения минимальный canary нужен даже в личном sideload-проекте.

Рекомендация: вернуть не "security audit", а малый `security/privacy smoke`:

- exported components sanity;
- cleartext traffic policy;
- WebView dangerous settings;
- file access/download path;
- backup/restore privacy;
- cookies/session handling;
- debug-only assumptions;
- sensitive data in logs.

### P10. R-09/R-10 остаются proposed

`filter-profiles` и `notes/tags` пока помечены как proposed risks. Если эти
функции реально пользовательские, их нужно утвердить или явно снять.

Рекомендация:

- формально добавить R-09/R-10 в risk matrix, если функции входят в поддерживаемый
  продукт;
- назначить им risk score;
- включить в release gate при изменениях соответствующих областей.

## 4. Что исправить в документации

### D1. Разделить target spec и текущий status до конца

Это уже начато: `state/factory-status.md` генерируется. Но в стратегии всё ещё
есть исторические снимки покрытия. Их лучше убрать или пометить как historical.

Правило:

- docs описывают правила, критерии и архитектуру;
- `state/factory-status.md` хранит текущие числа;
- roadmap хранит план;
- HANDOFF хранит только resume notes.

### D2. Добавить release-readiness summary

Нужен отдельный generated report:

- build under test;
- smoke status/freshness;
- regression status/freshness;
- canary status/freshness;
- open blocker/critical;
- known issues;
- accepted risks;
- quarantined tests;
- stale locks;
- pending human decisions;
- P0/P1 coverage gaps;
- test debt blocking release.

### D3. Roadmap сделать ещё более gate-driven

Для каждого крупного пункта roadmap стоит иметь:

- owner agent;
- input artifacts;
- output artifacts;
- exit criteria;
- self-tests;
- degradation behavior;
- release impact.

Это особенно важно для Project Intake, canary, impact-based selection,
exploratory testing и non-functional suites.

## 5. Рекомендуемая новая архитектурная надстройка

### 5.1. Intake pipeline для нового проекта

Новая фаза перед обычным тест-дизайном:

1. Собрать project inventory.
2. Определить тип приложения: mobile/web/API/backend/desktop/hybrid.
3. Построить карту пользовательских flows.
4. Построить data map: где хранятся данные, где возможна потеря/коррупция.
5. Построить integration map.
6. Определить testability gaps.
7. Сгенерировать risk register.
8. Сгенерировать initial test strategy.
9. Сгенерировать coverage graph.
10. Создать первые P0/P1 charters и GWT cases.

### 5.2. Coverage graph как источник истины по полноте

Добавить структуру вроде `state/coverage-model.yaml`:

```yaml
features:
  rating:
    risks: [R-04]
    requirements: [REQ-RATING-001, REQ-RATING-002]
    test_cases: [TC-007, TC-008, TC-009]
    automated_tests:
      - framework/tests/test_rating.py::test_rate_work_from_work_page_panel
    last_green_run: RUN-...
    coverage_status: partial
```

Это лучше, чем считать только статусы тест-кейсов.

### 5.3. Test effectiveness loop

Добавить регулярный цикл:

1. выбрать критичную область;
2. внести controlled defect в fixture/replay/mocked input или mutation branch;
3. прогнать targeted tests;
4. проверить, поймали ли дефект;
5. если нет — создать test gap;
6. добавить/усилить тест;
7. обновить effectiveness metrics.

## 6. Метрики качества тестирования

### 6.1. Метрики пропущенных дефектов

- `escaped_defects_total`: дефекты, найденные после green gate или после релиза.
- `escaped_defects_by_severity`: blocker/critical/major/minor.
- `severity_weighted_escape_rate`: escape rate с весом severity.
- `defect_detection_percentage`: дефекты до релиза / все дефекты за период.
- `mean_time_to_detect`: время от появления дефекта до обнаружения.
- `mean_time_to_triage`: время от failed run до verdict.

### 6.2. Метрики покрытия

- `risk_coverage`: доля рисков R-* с Approved/Automated тестами.
- `risk_coverage_weighted`: покрытие с весом risk score.
- `p0_automation_coverage`: доля P0 с active automated test.
- `p1_automation_coverage`: доля P1 с active automated test.
- `requirement_coverage`: requirement -> TC -> automated test -> last run.
- `coverage_freshness`: возраст последнего зелёного прогона по каждой области.
- `untested_changed_area_count`: изменённые области без targeted run.

### 6.3. Метрики эффективности тестов

- `seeded_defect_kill_rate`: пойманные seeded defects / все seeded defects.
- `mutation_score`: для проектов, где возможен white-box mutation testing.
- `assertion_strength_score`: доля тестов с проверкой бизнес-инварианта, а не
  только "экран открылся".
- `false_negative_incidents`: случаи, когда тест прошёл, но поведение было неверным.
- `bug_reproduction_success_rate`: доля багов с воспроизводимым automated repro.

### 6.4. Метрики стабильности тестов

- `flaky_rate`: flaky failures / total test executions.
- `quarantine_count`: количество quarantined tests.
- `quarantine_age_max`: максимальный возраст карантина.
- `rerun_dependency_rate`: доля тестов, которые проходят только после rerun.
- `env_issue_rate`: ENV_ISSUE / total failures.
- `test_bug_rate`: TEST_BUG / total failures.

### 6.5. Метрики данных и fixtures

- `fixture_ownership_coverage`: доля тестов с явно описанным owner/cleanup.
- `fixture_freshness`: возраст replay/recording относительно live/source changes.
- `recording_contract_failures`: failures из-за устаревших replay contracts.
- `data_seed_reliability`: pass rate setup/seed fixtures.

### 6.6. Метрики triage и evidence

- `verdict_evidence_completeness`: доля verdicts с полным evidence pack.
- `untriaged_failure_age`: максимальный возраст NeedsTriage.
- `duplicate_bug_rate`: доля дублей среди созданных багов.
- `known_issue_dedup_success`: сколько повторных APP_BUG корректно сопоставлены с
  known_issue.

### 6.7. Метрики автономности фабрики

- `permission_incidents`: любые permission-window в автономном периоде.
- `stale_lock_count`: активные stale locks.
- `qa_loop_success_rate`: успешные qa-loop проходы / все проходы.
- `agent_degraded_rate`: degraded/failed agent_output / all agent outputs.
- `self_test_pass_rate`: pass rate scripts/tests.
- `dark_day_rehearsal_pass`: регулярная репетиция суток без человека.

### 6.8. Метрики exploratory testing

- `charters_executed`: количество выполненных exploratory charters.
- `bugs_per_charter`: найденные уникальные баги на charter.
- `new_tests_from_charters`: сколько новых TC создано по итогам exploratory.
- `risk_discoveries`: новые риски, найденные exploratory testing.

## 7. Рекомендуемый порядок работ

1. Закрыть P0 automation gaps: listing/rating/visibility и backup/restore.
2. Сделать полный regression регулярным и видимым в release-readiness summary.
3. Создать и включить canary suite для AO3 DOM/bridge.
4. Утвердить или отклонить R-09/R-10; убрать вечный proposed status.
5. Добавить coverage graph как machine-readable модель полноты.
6. Добавить metrics collector и сгенерированный quality dashboard.
7. Ввести seeded defects/fault injection для проверки силы тестов.
8. Добавить Project Intake pipeline и новых агентов discovery/risk/coverage.
9. Добавить exploratory charters как первоклассные артефакты.
10. Поднять accessibility/performance/compatibility smoke в обязательные gates.
11. Вернуть минимальный security/privacy canary.
12. Включить impact-based test selection.
13. Запустить регулярную dark-day rehearsal как regression самой фабрики.

## 8. Критерии зрелости Darker-than-dark factory

Фабрику можно считать близкой к целевому состоянию, когда выполняются условия:

- новый проект проходит intake без ручного написания стратегии с нуля;
- P0/P1 риски имеют coverage graph и traceability до run evidence;
- каждый release candidate имеет свежий smoke, targeted regression и актуальный
  release-readiness summary;
- canary ловит изменения внешних контрактов до массовых падений regression;
- seeded defect rehearsal показывает высокий kill rate;
- flaky/test debt не копится без SLA;
- exploratory testing регулярно создаёт новые знания, TC или баги;
- любые APP_BUG verdicts имеют полный evidence pack;
- escape rate измеряется и ретроспективно приводит к новым тестам;
- человек нужен для product decisions и фикса кода приложения, а не для движения
  QA-очереди.

## 9. Bottom line

Проект уже имеет сильную основу автономной QA-фабрики. Следующий качественный
скачок — не в добавлении ещё одного агента-исполнителя, а в добавлении
доказательности:

- фабрика должна доказывать, что поняла продукт;
- доказывать, что покрыла риски;
- доказывать, что тесты ловят дефекты;
- измерять, какие баги всё же ушли мимо;
- автоматически превращать каждый пропуск в новый тест, метрику или правило.

Именно этот слой отличает "автоматизированную команду тестировщиков" от
"автоматического раннера с хорошей документацией".
