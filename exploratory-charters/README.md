# exploratory-charters/ — исследовательские сессии как артефакты (P7 ревью docs/10)

Charter — план и протокол одной exploratory-сессии. Scripted-регрессия ловит
известное; charter ищет неизвестное: новые риски, баги вне кейсов, пробелы
дизайна. Charter — первоклассный артефакт фабрики, как test-case и bug.

## Конвенции

- Один файл `CH-NNN.md` = одна сессия с таймбоксом. ID `CH-NNN` уникален и
  не переиспользуется (max+1).
- Шаблон — `docs/templates/charter.md`; исполняет агент `exploratory-tester`.
- Статусы: `Planned` (заведён, не исполнялся) → `InProgress` (лок взят,
  сессия идёт) → `Done` (протокол и follow-up заполнены). Схема-валидация и
  машина статусов — шаг 2 внедрения (docs/09 Этап 4 п.11).
- Находки НЕ живут только прозой протокола (класс AT-BUG-004/005/006 —
  «знание в теле артефакта, которого не видит конвейер»): каждый
  воспроизводимый баг → через bug-reporter в `bugs/` (ссылка в frontmatter
  `found_bugs`), каждый пробел покрытия → follow-up TC через test-designer
  (ссылка в `followup_tc`); новый риск → предложение в docs/01 §10.
- Вложения (скриншоты, дампы) — `exploratory-charters/attachments/CH-NNN/`,
  не корень репо.

## Триггеры заведения charter'а (docs/10 P7, docs/09 Этап 4 п.11)

- новая крупная функция приложения;
- вердикт APP_CHANGED в триаже;
- перед релизом;
- зона с повторными багами (эвристика «где один — там два»).

До шага 2 (правило в rules.yaml) charter'ы заводит и диспатчит Lead вручную,
с записью delegated/accepted в logs/routing-log.jsonl. Метрики
(`charters_executed`, `bugs_per_charter`, `new_tc_from_charters`) — тоже
шаг 2, считать будет queue_snapshot из frontmatter этого каталога.
