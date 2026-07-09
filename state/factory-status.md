# Статус фабрики (генерируется, НЕ редактировать руками)

generated_at: 2026-07-09T13:11:49Z · генератор: `scripts/queue_snapshot.py`
Счётчики очереди ведутся ТОЛЬКО здесь (ревью A4/G1, docs/09). Ручные числа в HANDOFF/докках не имеют силы.

## Сборка под тестом

- 1.10 (versionCode 11), commit `63f6aac3`, built_at 2026-07-02T02:39:46
- smoke: passed · regression: not_run

## Тест-кейсы (55)

- Draft: **1** · Review: **14** · Approved: **19** · Automated: **21**
- автотесты (B3): active: **21**

| Область | Draft | Review | Approved | Automated | Blocked |
|---|---|---|---|---|---|
| backup |  |  | 1 |  |  |
| browser |  |  |  | 6 |  |
| downloads |  | 3 | 2 | 3 |  |
| errors |  |  | 1 |  |  |
| filter-profiles |  |  | 3 |  |  |
| library | 1 | 1 | 4 | 2 |  |
| rating |  | 5 | 2 | 2 |  |
| settings |  | 1 | 2 | 3 |  |
| smoke |  |  |  | 5 |  |
| tabs |  | 1 | 4 |  |  |
| visibility |  | 3 |  |  |  |

## Баги (1)

- Open: **1**
- BUG-001 [minor] Open — Подписи вкладок Library и меню рейтинга расходятся с PROJECT.md

## Известные проблемы, known_issue (0)

- нет

## Test debt (3)

- AT-BUG-004 [missing_fixture] Fixed — Replay-инфраструктура не доведена: нет записей work/листинг-страниц и mitm-фикстуры в conftest — блокирует автоматизацию 10 P0/P1 кейсов
- AT-BUG-005 [missing_fixture] Open — SAF file/folder picker не автоматизируется штатными Appium-локаторами — блокирует TC-021 (P0, backup/restore) и часть download/backup-кейсов
- AT-BUG-006 [missing_fixture] Open — Таблица filter_profiles не поддержана в seed_db.py и нет replay-записи формы AO3 Sort&Filter — блокирует автоматизацию батча filter-profiles (TC-040/041/042, P1)

## Прогоны (1)

- Closed: **1**

## Активные локи (0)

- нет

## Эскалации (0)

- нет
