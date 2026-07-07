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

1. **C3 + F3 — статусные машины как код.** Transition matrix (bug/TC/run) в YAML +
   тесты переходов и side effects (`status_since`, локи, эскалации, курсор борды);
   self-tests фабрики для sla_sweep/stale_locks/build_watch; репетиция тёмного дня —
   повторяемый регресс фабрики, не разовое событие.
2. **B1/B2/B5 — недостающие ветки workflow.** `resolution: accepted_risk|wontfix`
   (обязателен комментарий человека), `known_issue: true` + дедупликация APP_BUG
   против known issues, `blocked_reason` enum → SLA и дайджест.
3. **B3/B4 — lifecycle автотеста и test debt.** `automation_status:
   active|quarantined|needs_maintenance|deprecated|retired` + `quarantine_*` поля
   с SLA (карантин не бесконечен); test debt — `bugs/` с `type: test_debt`.
4. **C2 — evidence contract.** Минимальный пакет доказательств на каждый вердикт
   (таблица из ревью §4 C2) → инструкции failure-analyst/fix-verifier + проверка
   в self-tests.
5. **F2 — agent output schema.** Каждый агент возвращает machine-readable результат
   (result/changed_files/evidence/escalations); верхний диспетчер не парсит
   свободный текст.
6. **F1 — test-reviewer.** Роль (или режим test-maintainer): ревью нового автотеста
   (архитектурные правила, evidence, flake-риск, traceability) до перевода TC в
   стабильную автоматизацию.
7. **GitLab Issues для критичных багов** (решение владельца): bug-reporter при
   severity выше major создаёт Issue в репозитории приложения; ссылка — в frontmatter
   бага. Нужен GitLab-токен (запросить у владельца при реализации).
8. **C1 — архитектурные чеки фреймворка.** Статический чек: запрет `driver`/локаторов
   в `tests/`, обязательные `@allure.id` и markers.

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
