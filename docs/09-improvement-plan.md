# 09 — План улучшений по итогам внешнего ревью

Дата: 2026-07-07
Основание: [08-external-architecture-review.md](08-external-architecture-review.md) + решения владельца (2026-07-07).
Статус пунктов ревью сверен с фактическим состоянием репозитория (см. §1).

## 0. Решения владельца (2026-07-07)

- **Порядок работ:** сначала архитектурные долги (Этап 1), затем исполняемые контракты
  (Этап 2), затем возврат к автоматизации Approved-кейсов (Этап 3).
- **Non-functional скоуп:** performance/stability smoke (E2), accessibility smoke (E1),
  compatibility matrix (E3). **Security/privacy canary (E4) — не берём**
  *(частично пересмотрено 2026-07-14 — минимальный smoke-скоуп, см. §5 и
  Этап 4 п.13)*.
- **Каналы к разработчику:** борда + комментарии в тасках + дневной дайджест;
  для багов severity **выше major** (critical/blocker) — создавать GitLab Issues
  в репозитории приложения *(уточнение 2026-07-07 вечер: отложено в Этап 4,
  вместе с Telegram-ботом)*. **Commit status (D2) — не подключаем.**
- **Доставка дайджеста/эскалаций:** сейчас файлы + борда (человек приходит сам);
  в будущем — Telegram-бот (Этап 4, последним).

## 1. Сверка находок ревью с фактическим состоянием (2026-07-07)

| Находка | Статус | Комментарий |
|---|---|---|
| A1 вложенная оркестрация | **Подтверждена, не исправлена** | `/qa-loop` всё ещё запускает qa-orchestrator субагентом; совпадает с критической находкой репетиции тёмного дня (HANDOFF) |
| A2 pre_steps неисполняемы | **Подтверждена** | реализован только `board_inbound.py`; `stale_locks`/`sla_sweep`/`build_watch` — описания; `state/escalations.md` нет |
| A3 сломанный venv | **Не воспроизводится** | `framework/.venv` работает (Python 3.12.10), python в PATH; doctor-скрипт всё равно нужен для автономности |
| A4 ручные счётчики | **Подтверждена** | HANDOFF: «41 Approved»; факт по frontmatter: 37 Approved, 9 Automated, 8 Review, 1 Draft |

## Этап 1 — Runtime-фундамент (блокеры автономности) — ✅ ВЫПОЛНЕН 2026-07-07

Все 5 пунктов реализованы (55 pytest scripts/tests зелёные), интеграционная
проверка пройдена: pre_steps в бою (снят протухший лок TC-021), планировщик
--dry-run вернул корректный план + 3 находки (smoke_status исправлен, §9 стратегии
протух — см. HANDOFF, canary-правило переведено в [план] до Этапа 3).
Хвост: блок разрешений новых скриптов в .claude/settings.json ждёт подтверждения
владельца. Задачи «сильной модели». Без этого этапа конвейер полуручной.

1. **A1 — диспетчеризация с верхнего уровня.** `/qa-loop`-скилл сам читает
   `rules.yaml`, выполняет pre_steps-скрипты и диспатчит воркеров глубины 1
   (синхронно). `qa-orchestrator` — либо планировщик (возвращает machine-readable
   план, исполняет верхний уровень), либо убирается из runtime-пути.
   Обновить docs/03 §1, docs/06, `.claude/agents/qa-orchestrator.md`,
   `.claude/skills/qa-loop/SKILL.md`.
   *Выход:* полный проход `/qa-loop` диспатчит >1 воркера, ноль осиротевших локов,
   ноль permission-окон.
2. **A2 — исполняемые pre_steps.** `scripts/stale_locks.py`, `scripts/sla_sweep.py`,
   `scripts/build_watch.py` — идемпотентные, с pytest-тестами в `scripts/tests/`
   (по образцу board_inbound), единый формат `state/escalations.md`.
   build_watch: `git fetch` app-under-test → новые коммиты → `gradlew assembleDebug`
   → `state/app-under-test.yaml` (+ coalescing D11).
   *Выход:* все 4 pre_steps без пометки [план]; первый клиент stale_locks —
   лок TC-021 (висит с 2026-07-02).
3. **A4 + G1 — генерируемый статус.** `scripts/queue_snapshot.py` собирает
   `state/factory-status.md` из frontmatter; HANDOFF сокращается до resume notes;
   ручные счётчики в документах запрещены.
   *Выход:* очередь в HANDOFF/дайджесте всегда совпадает с frontmatter.
4. **A3-профилактика — doctor.** `scripts/doctor.py`: python/venv/adb/эмулятор/
   Appium/node/gradle; запуск в начале каждого scheduled-прохода, при провале —
   эскалация вместо тихого падения.
5. **G3 — схемы frontmatter.** `schemas/{test-case,bug,run,rules}.schema.yaml` +
   валидация в preflight `/qa-loop`.
   *Выход:* битый frontmatter ловится до диспетчеризации, а не в момент падения агента.

## Этап 2 — Исполняемые контракты workflow

1. **C3 + F3 — статусные машины как код.** ✅ 2026-07-07: `schemas/transitions.yaml`
   (акторы, via_board, эффекты, ссылки на D1–D12) + `scripts/transitions.py`;
   whitelist board_inbound выводится из матрицы; 15 self-tests (валидность, паритет,
   границы акторов, эффекты); попутно исправлен pingpong в sla_sweep (Fixed не
   блокируем — шанс fix-verifier; Rejected-спор блокируем по D4).
   *Хвосты:* тесты парсера permission_audit — ✅ 2026-07-07 (Sonnet-сессия,
   35 тестов + вынос collect_suspects из main); репетиция тёмного дня как
   повторяемый регресс (после F2, когда появится machine-readable результат
   агентов) — осталось.
2. **B1/B2/B5 — недостающие ветки workflow.** ✅ 2026-07-07: `resolution:
   accepted_risk|wontfix` + обязательный `resolution_comment` (bug.schema.yaml,
   validate_frontmatter кросс-проверка), `known_issue: true` (дедуп APP_BUG в
   bug-reporter.md — сверка known_issue в первую очередь; still-repro D3 расширен
   на known_issue любой severity; digest — секция «Известные проблемы» в
   queue_snapshot.py), `blocked_reason` enum (bug/test-case/run — все три схемы,
   т.к. `Blocked` есть в каждой машине; sla_sweep pingpong и board_inbound-конфликт
   проставляют `product_decision` автоматически; validate_frontmatter — WARN при
   отсутствии на status Blocked). sla_sweep больше не шлёт периодический
   bug_open_severity-варнинг для resolution/known_issue багов (docs/06 D13/D14).
   10 новых self-tests (86 всего в scripts/tests).
3. **B3/B4 — lifecycle автотеста и test debt.** ✅ 2026-07-07: машина `automation`
   в transitions.yaml (active/quarantined/needs_maintenance/deprecated/retired;
   карантинит failure-analyst с обязательными quarantine_reason/since, выводит
   ТОЛЬКО test-maintainer после 3 зелёных); sla_sweep `quarantine_expired`
   (expiry или since+quarantine_max 336ч); test debt — `bugs/` c `type: test_debt`
   + `debt_kind`, guard-переходы Open|Reopened→Fixed для test-maintainer/
   test-automator (только test_debt; app_bug Fixed — по-прежнему человек),
   Fixed не ждёт сборку, severity-SLA молчит, отдельная секция digest; правила
   «Починить автотест в карантине» (выше новой автоматизации) и «Устранить test
   debt» в rules.yaml. Первый клиент: AT-BUG-002 (test_debt на нарушения arch_check
   в test_smoke.py). Подробности — docs/06 «B3/B4».
4. **C2 — evidence contract.** ✅ 2026-07-07 (Sonnet-сессия): `schemas/evidence.yaml`
   (6 вердиктов, 21 элемент; FLAKY включает quarantine_decision по B3/B4) +
   `scripts/evidence.py` (load/validate/missing + CLI) + разделы «Evidence
   contract (C2)» в failure-analyst/fix-verifier + 9 self-tests.
5. **F2 — agent output schema.** ✅ 2026-07-07: `schemas/agent-output.schema.yaml`
   (result: success|blocked|degraded|failed + summary/changed_files/evidence/
   next_rules/escalations), парсер `scripts/agent_output.py` (последний
   ```yaml-блок с ключом agent_output; нет блока → degraded), контракт вшит в
   /qa-loop (требование в промпте каждого диспатча) и docs/03 §5 п.7; 6 тестов.
6. **F1 — test-reviewer.** ✅ 2026-07-07: отдельная роль (`.claude/agents/
   test-reviewer.md`, model: opus) — «вторые глаза», тестовый код не правит.
   Гейт в матрице: Approved→Automated переводит ТОЛЬКО test-reviewer (он же ставит
   automation_status: active); test-automator заполняет automated_by, статус не
   меняет. Возврат: `review: changes_requested` (поле в схеме TC) + замечания в
   кейсе → правило «Доработать автотест по ревью». Чек-лист: arch_check,
   traceability, GWT по смыслу, фикстуры, flake-риск, независимый прогон.
7. **GitLab Issues для критичных багов** — ⏸ отложено решением владельца
   2026-07-07 (вечер): переносится в Этап 4, делать вместе с Telegram-ботом
   (оба — внешние каналы доставки). До того канал для critical+ прежний:
   борда + эскалация в state/escalations.md.
8. **C1 — архитектурные чеки фреймворка.** ✅ 2026-07-07 (Sonnet-сессия):
   `scripts/arch_check.py` (AST-чек: запрет импортов screens/web/локаторов и
   `.find_element`/`.by_text` в tests/, обязательные `@allure.id` + suite-маркер
   из pytest.ini) + 23 теста; преflight-шаг 3 в /qa-loop. Найденные реальные
   нарушения test_smoke.py — в ALLOWLIST скрипта + AT-BUG-002 (test_debt).

## Этап 3 — Возврат к Фазе 3 (автоматизация)

1. 37 Approved-кейсов батчами по area (P0 → P1) через обновлённый конвейер.
2. Разблокировка TC-009/013/014/015: записать replay-фикстуру листинга с блёрбом
   синтетической работы; встроить `install-mitm-ca.sh` в test-runner (replay-режим
   поднимается автономно).
3. TC-021 / SAF-пикер — отдельная задача (не автоматизируется штатно, нужен обход).
4. **C5 — test data contract:** manifest для `framework/data/recordings/` + fixtures,
   версия схемы Room/backup, правило «новый тест не принимается без fixture ownership
   и cleanup strategy».

## Этап 4 — Расширение качества и расписание

1. **E2 performance/stability smoke:** cold start, WebView first load, no ANR/crash,
   скан logcat на fatal, memory sanity длинной WebView-сессии.
2. **E1 accessibility smoke:** лейблы ключевых контролов, font scaling, контраст тем.
3. **E3 compatibility matrix:** второй (нижний) API по расписанию, системная
   dark/light; portrait/landscape — если поддерживается приложением.
4. **C4 — метаморфные/инвариантные проверки** для фильтров/рейтингов/backup
   (рейтинг X виден только в своей вкладке; clear all чистит все множества;
   backup→clear→restore сохраняет множество; сортировка не меняет состав и т.д.).
   *Механизм внедрён 2026-07-14 (банк инвариантов docs/10 P5): обязанность
   `Инвариант: …` в промпте test-designer + детектор в п.3 чек-листа
   test-reviewer; сами инвариантные кейсы/тесты — штатным конвейером.*
5. **D1 — impact-based test selection:** карта `changed files → areas → TC`;
   risk score → размер suite; fallback на полную регрессию при неизвестном impact.
6. **Расписание + дайджест:** heartbeat `/qa-loop`, ночная регрессия, дневной canary
   (анти-наложение `state/loop.lock`); дневной дайджест-файл + release-readiness
   сводка (D3): сборка, smoke, open blockers, known issues, карантин, stale locks,
   pending decisions.
7. **Telegram-бот** для дайджеста/эскалаций — последним, после стабилизации
   файлового канала.
8. **GitLab Issues для критичных багов** (перенесено из Этапа 2 решением
   владельца 2026-07-07): bug-reporter при severity выше major создаёт Issue в
   репозитории приложения; ссылка — в frontmatter бага. Нужен GitLab-токен
   (запросить при реализации). Делать вместе с Telegram-ботом.
9. **Фикс sync-виджета TrackState-борды (кириллица в коммитах)** — низкий
   приоритет, отложено сюда решением владельца 2026-07-08 (внешний канал = борда,
   рядом с Telegram/GitLab). НЕ блокер: контент борды (тикеты, колонки) рендерится
   штатно — падает только виджет статуса синхронизации с git («Repository» →
   `Attention needed`, `Invalid argument (string): Contains invalid characters.`).
   - **Причина (класс):** Dart `ascii/latin1.encode` на не-Latin1 строке
     (`_UnicodeSubsetEncoder` → `ArgumentError` "Contains invalid characters.",
     кладёт саму строку в значение — оттого в ошибке виден весь JSON коммита).
     Кириллица в commit message косвенно попадает в энкодер на шаге `checkSync`.
   - **Уже сделано (2026-07-08):** `install-update-trackstate.yml` перепинен с
     upstream `IstiN/trackstate@v2099.173.100715142411` на наш форк
     `Xartaxana/trackstate-by-Dark-Factory@2b258f68…` (полный 40-символьный SHA —
     короткий checkout не принимает). Путь A (расчёт, что свежий код форка уже без
     бага) проверен эмпирически и **не сработал** — баг есть и в `main` форка.
     Прямого `ascii/latin1.encode` в исходниках `main` нет → вызов косвенный.
   - **План (путь B), при реализации:**
     1. Собрать Flutter web из форка локально (`flutter 3.35.3`, те же
        `--dart-define`, что в workflow), воспроизвести sync на репозитории с
        кириллицей в сообщениях коммитов.
     2. Поймать точный стек-трейс энкодера — сейчас он проглатывается
        (`workspace_sync_service.dart` `on Object catch` показывает только
        `'$error'`); временно пробросить/залогировать `stackTrace`, найти
        файл:строку косвенного `ascii/latin1.encode` (кандидат — путь
        `github_trackstate_provider` `checkSync`/`_readHostedRepositoryDelta`).
     3. Патч в форке: `utf8` вместо `ascii/latin1` в найденном месте; пуш в форк,
        обновить SHA-пин в workflow, передеплой, убедиться что виджет зелёный.
     4. Опционально — PR/issue в upstream `IstiN/trackstate`.
   - **Детектор (F-11в):** сам виджет борды («Attention needed» пропадает при
     успехе) — визуальная приёмка после передеплоя. См. память
     `trackstate-board-sync-cyrillic-defect`, docs/05-board.md.

## Отклонено / вне скоупа (решения владельца)

- E4 security/privacy canary — не берём. *(Частично пересмотрено 2026-07-14
  при сверке ревью docs/10: принят минимальный smoke-скоуп — §5, Этап 4 п.13;
  полный security-аудит по-прежнему вне скоупа.)*
- D2 GitLab commit status / protected branch gates — не подключаем
  (разработчик = владелец, гейт через борду и дайджест).

## Мелкое хозяйство (попутно с Этапом 1)

- Убрать из корня `scratch_screen*.png` (3 × ~1.3 МБ) — в .gitignore/удалить.
- Закоммитить накопившееся: README.md, docs/08, docs/09, `.agents/`.
- Bypass ExecutionPolicy зашить в функции `tasks.ps1` (находка репетиции, не блокер).
- Косметика factory-status.md: секция «Сборка под тестом» использует «?» для
  отсутствующих полей, секция «Release readiness» — «n/a»; привести к одному
  плейсхолдеру (остаток класса, доложен builder'ом r10-release-readiness,
  подтверждён critic 2026-07-14).

## 5. Сверка внешнего ревью docs/10 с фактическим состоянием (2026-07-14)

Основание: [10-external-quality-review.md](10-external-quality-review.md)
(2026-07-13). Фактура сверена разведкой r10-adoption-recon (routing-log
2026-07-14): canary-пакет пуст, coverage-model/exploratory-charters нет,
неавтоматизированные P0 и статусы R-09/R-10 подтверждены пофайлово.

| Пункт ревью | Сверка | Решение |
|---|---|---|
| P1 regression не регулярный | **Подтверждено** (factory-status 2026-07-10: smoke passed, regression not_run) | Release-readiness секция вытягивается вперёд из Этапа 4 п.6 — задача r10-release-readiness (builder), в работе 2026-07-14. Регулярный regression-gate — остаётся в Этапе 4 п.6 (расписание) |
| P2 P0-гэпы | **Подтверждено дословно**: TC-009/013/014/015 (блокер AT-BUG-004), TC-021 (AT-BUG-005, инфраструктура готова) | Уже пункты 2–3 Этапа 3; ревью подтверждает приоритет «P0 раньше P2/P3». Нового не заводим |
| P3 canary отсутствует | **Подтверждено** (`framework/tests/canary/` — пустой пакет, правило в rules.yaml в статусе [план]) | Уже Этап 3/rules.yaml. Контракт bridge из ревью (work blurb, work id, rating/note buttons, badge, filter/save controls; live+replay раздельно) принять как DoD диспатча при реализации |
| P4 project intake | Новое; для качества AO3-тестирования не требуется | Стратегическая развилка владельца (отдельный слой «фабрика для нового проекта»), не пункт очереди |
| P5 инварианты | Частично уже C4 Этапа 4 | C4 дополняется списком инвариантов из ревью P5; при реализации — чек-лист в шаблон/промпт test-designer (механизм — через 4 вопроса F-11) |
| P6 seeded defects | Новое | Этап 4 п.10 (ниже); после закрытия P0 и canary |
| P7 exploratory charters | Новое (каталога нет — сверено) | Этап 4 п.11 (ниже) |
| P8 non-func раньше | E1/E2/E3 уже в Этапе 4 (решение владельца 2026-07-07) | Изменение приоритета — вопрос владельцу; до решения порядок прежний |
| P9 security/privacy smoke | Конфликт с решением владельца 2026-07-07 (E4 отклонён) | Вопрос владельцу: подтвердить отказ или принять урезанный скоуп (WebView settings, cleartext, sensitive data in logs). До решения — отклонено |
| P10 R-09/R-10 proposed | **Подтверждено** (proposed с 2026-07-02; AT-BUG-006 уже блокирует автоматизацию filter-profiles) | Вопрос владельцу: утвердить в матрице §5 или снять |
| D1 historical-снимки в стратегии | **Подтверждено расхождение** (§9: 55/9 Automated против factory-status 2026-07-10: 58/21) | ✅ Исправлено 2026-07-14: числа статусов из docs/01 §9 убраны, раскладка по областям помечена HISTORICAL |
| D2 release-readiness summary | Частично уже Этап 4 п.6 («release-readiness сводка (D3)») | Вытянуто вперёд: секция в `queue_snapshot.py` → `state/factory-status.md`, задача r10-release-readiness. Стартовые метрики — только считаемые из существующих артефактов (`regression_freshness_hours`, `p0_automation_coverage`, `untriaged_failure_age`, quarantine/test-debt счётчики). Метрики escape rate — после появления release gate (данных пока нет) |
| D3 gate-driven roadmap | Принято как форма | Для НОВЫХ крупных пунктов плана — owner agent / input / output / exit criteria; ретроспективно выполненные этапы не переписываем |
| §6 метрики (~35 шт.) | — | Оптом не берём; стартовый набор — в составе release-readiness (см. D2). Остальные — по мере появления данных |
| §5.2 coverage graph | coverage-model.yaml нет (сверено) | Этап 4 п.12 (ниже) — но ГЕНЕРИРУЕМАЯ проекция из frontmatter (принцип «проекция, не второй источник истины»), не рукописный yaml |

**Дополнения к Этапу 4 (по ревью docs/10):**

10. **Seeded defects / test effectiveness loop (P6, §5.3):** регулярная
    controlled-defect репетиция для black-box — испорченный replay DOM,
    corrupted backup, stale DB schema, сломанный селектор, wrong rating
    mapping; непойманный дефект → test gap (test_debt); метрика
    `seeded_defect_kill_rate`. Делать после закрытия P0-гэпов и canary.
11. **Exploratory charters (P7):** каталог `exploratory-charters/` + шаблон
    (mission, scope, risks, heuristics, observations, found bugs, follow-up
    TC) + агент exploratory-tester; триггеры — новая крупная функция,
    APP_CHANGED, перед релизом. Метрики: `bugs_per_charter`,
    `new_tc_from_charters`.
12. **Coverage-проекция (§5.2):** генерируемый из frontmatter граф
    feature → risk → TC → automated test → last green run (расширение
    queue_snapshot или отдельный скрипт); рукописный coverage-yaml не
    заводим.
13. **Security/privacy smoke — минимальный скоуп (P9 docs/10; решение
    владельца 2026-07-14, частичный пересмотр отказа E4):** exported
    components sanity, cleartext traffic policy, опасные настройки WebView
    (JS-бриджи, file access), пути file access/download, privacy
    backup-файла, sensitive data в logcat. Формат — smoke-чеки в духе E2,
    НЕ security-аудит; дизайн кейсов — через штатный конвейер
    (test-designer), приоритет ниже E1–E3.

**Развилки владельца — решены 2026-07-14 (тем же днём):**
(а) R-09/R-10 — **УТВЕРЖДЕНЫ ОБА**, внесены в матрицу §5 стратегии (BUS 4 и
DATA 4); (б) security/privacy — **принят МИНИМАЛЬНЫЙ smoke-скоуп** (частичный
пересмотр отказа E4 от 2026-07-07; полный аудит по-прежнему вне скоупа) —
Этап 4 п.13; (в) non-func — **порядок прежний**, E1–E3 остаются в Этапе 4.
