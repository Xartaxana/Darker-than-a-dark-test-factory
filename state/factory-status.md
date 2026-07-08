# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-08T21:47:44Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (55)

- Draft: **1** · Review: **14** · Approved: **25** · Automated: **15**
- автотесты (B3): active: **15**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  | 1 |  |  |
| browser |  |  |  | 6 |  |
| downloads |  | 3 | 5 |  |  |
| errors |  |  | 1 |  |  |
| filter-profiles |  |  | 3 |  |  |
| library | 1 | 1 | 4 | 2 |  |
| rating |  | 5 | 2 | 2 |  |
| settings |  | 1 | 5 |  |  |
| smoke |  |  |  | 5 |  |
| tabs |  | 1 | 4 |  |  |
| visibility |  | 3 |  |  |  |

## Баги (1)

- Open: **1**
- BUG-001 [minor] Open — Подписи вкладок Library и меню рейтинга расходятся с PROJECT.md

## Известные проблемы, known_issue (0)

- нет

## Test debt (2)

- AT-BUG-003 [missing_evidence] Fixed — Кейсы, автоматизированные до гейта F1 (TC-007/008/016/017), не несут полей жизненного цикла B3 (automation_status/reviewed_by/reviewed_at)
- AT-BUG-004 [missing_fixture] Open — Replay-инфраструктура не доведена: нет записей work/листинг-страниц и mitm-фикстуры в conftest — блокирует автоматизацию 10 P0/P1 кейсов

## Прогоны (1)

- Closed: **1**

## Активные локи (0)

- нет

## Эскалации (0)

- нет
