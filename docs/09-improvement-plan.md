# 09 — План улучшений по итогам внешнего ревью

Дата: 2026-07-07
Основание: [08-external-architecture-review.md](08-external-architecture-review.md) + решения владельца (2026-07-07).
Статус пунктов ревью сверен с фактическим состоянием репозитория (см. §1).

## 0. Решения владельца (2026-07-07)

- **Порядок работ:** сначала архитектурные долги (Этап 1), затем исполняемые контракты
  (Этап 2), затем возврат к автоматизации Approved-кейсов (Этап 3).
- **Non-functional скоуп:** performance/stability smoke (E2), accessibility smoke (E1),
  compatibility matrix (E3). **Security/privacy canary (E4) — не берём.**
- **Каналы к разработчику:** борда + комментарии в тасках + дневной дайджест;
  для багов severity **выше major** (critical/blocker) — создавать GitLab Issues
  в репозитории приложения. **Commit status (D2) — не подключаем.**
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
   debt» в rules.yaml. Первый клиент: BUG-002 (test_debt на нарушения arch_check
   в test_smoke.py). Подробности — docs/06 «B3/B4».
4. **C2 — evidence contract.** Минимальный пакет доказательств на каждый вердикт
   (таблица из ревью §4 C2) → инструкции failure-analyst/fix-verifier + проверка
   в self-tests.
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
7. **GitLab Issues для критичных багов** (решение владельца): bug-reporter при
   severity выше major создаёт Issue в репозитории приложения; ссылка — в frontmatter
   бага. Нужен GitLab-токен (запросить у владельца при реализации).
8. **C1 — архитектурные чеки фреймворка.** ✅ 2026-07-07 (Sonnet-сессия):
   `scripts/arch_check.py` (AST-чек: запрет импортов screens/web/локаторов и
   `.find_element`/`.by_text` в tests/, обязательные `@allure.id` + suite-маркер
   из pytest.ini) + 23 теста; преflight-шаг 3 в /qa-loop. Найденные реальные
   нарушения test_smoke.py — в ALLOWLIST скрипта + BUG-002 (test_debt).

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
5. **D1 — impact-based test selection:** карта `changed files → areas → TC`;
   risk score → размер suite; fallback на полную регрессию при неизвестном impact.
6. **Расписание + дайджест:** heartbeat `/qa-loop`, ночная регрессия, дневной canary
   (анти-наложение `state/loop.lock`); дневной дайджест-файл + release-readiness
   сводка (D3): сборка, smoke, open blockers, known issues, карантин, stale locks,
   pending decisions.
7. **Telegram-бот** для дайджеста/эскалаций — последним, после стабилизации
   файлового канала.

## Отклонено / вне скоупа (решения владельца)

- E4 security/privacy canary — не берём.
- D2 GitLab commit status / protected branch gates — не подключаем
  (разработчик = владелец, гейт через борду и дайджест).

## Мелкое хозяйство (попутно с Этапом 1)

- Убрать из корня `scratch_screen*.png` (3 × ~1.3 МБ) — в .gitignore/удалить.
- Закоммитить накопившееся: README.md, docs/08, docs/09, `.agents/`.
- Bypass ExecutionPolicy зашить в функции `tasks.ps1` (находка репетиции, не блокер).
