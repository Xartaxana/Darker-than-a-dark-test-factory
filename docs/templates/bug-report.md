---
id: BUG-000
title: Краткая формулировка дефекта (что сломано, где)
type: app_bug          # app_bug | test_debt (B4: долг тестовой системы — flaky/slow/фикстуры/локаторы; чинит фабрика, Fixed не ждёт сборку)
debt_kind: ""          # только для test_debt: flaky_test | slow_test | missing_fixture | weak_locator | obsolete_test_case | missing_evidence | broken_environment
severity: major        # blocker | critical | major | minor | trivial
status: Open           # Open | Fixed | Verified | Reopened | Rejected | Intended | Blocked
found_in: "1.10 (versionCode 11), build <hash>"   # из state/app-under-test.yaml
fixed_in: ""           # заполняет человек при переводе в Fixed
last_seen_in: ""       # последняя сборка, где репро подтверждено (fix-verifier, mode=still-repro)
test_cases: [TC-031]   # связанные тест-кейсы
runs: [RUN-20260702-0130]   # прогоны, где воспроизводился
duplicates: []         # если dubl — ссылка на оригинал, статус Rejected
regression_of: ""      # если баг — регрессия от фикса другого бага (docs/06 D7)
status_since: "2026-07-03T00:00:00Z"   # когда установлен текущий status (для SLA-sweep)
reopen_count: 0        # сколько раз Reopened; >= sla.reopened_pingpong → эскалация
dispute_count: 0       # сколько раз фабрика оспаривала Rejected (docs/06 D4)
awaiting: none         # dev | qa | none — чей ход в ## Обсуждение
resolution: ""         # accepted_risk | wontfix (docs/06 D13) — обязателен resolution_comment
resolution_comment: "" # обоснование человека, если задан resolution
known_issue: "false"   # true — подтверждён, релиз идёт с ним (docs/06 D14, дедуп + digest)
blocked_reason: ""     # environment | missing_fixture | product_decision | dev_answer | permissions (docs/06 B5) — заполнить при status: Blocked
lock: ""
---

# BUG-000 — {Название}

## Окружение
- Версия приложения, эмулятор/устройство + API level, режим (replay/live), тема.

## Шаги воспроизведения (Given-When-Then)

**Given** ...
**When** ...
**Then (ожидалось)** ...
**Actual (фактически)** ...

## Частота
Всегда / N из M попыток (failure-analyst обязан перепроверить изолированным запуском).

## Артефакты
- Скриншот: `runs/RUN-.../artifacts/...png`
- Logcat: `runs/RUN-.../artifacts/...log` (ключевые строки процитировать ниже)
- Page source / URL таба на момент падения

## Анализ (failure-analyst)
Почему это баг приложения, а не теста/окружения/сайта: наблюдения, исключения из
logcat, сопоставление с ожидаемым поведением по PROJECT.md.

## Верификация (заполняет fix-verifier)
| Дата | Версия сборки | Прогнанные TC | Результат | Вердикт |
|---|---|---|---|---|

## Обсуждение
Канал человек ↔ фабрика (зеркалится в комментарии карточки на борде, docs/06 §3).
Формат реплики: `**[автор @ ISO-время]** текст`. После своей реплики автор ставит
`awaiting:` на противоположную сторону; фабрика отвечает на `awaiting: qa` в
ближайший проход (bug-reporter, role=responder), просрочка `awaiting: dev`
контролируется SLA `question_unanswered`.

## Чек-лист качества (bug-reporter проходит перед публикацией)
- [ ] Проверены дубликаты среди открытых багов (`bugs/`, status != Verified/Rejected)
- [ ] Репро-шаги воспроизводят проблему на чистом состоянии
- [ ] Severity обоснована влиянием на пользователя, а не эмоцией
- [ ] Приложены logcat и скриншот; указана точная версия сборки
- [ ] Ни одно изменение не внесено в код приложения
