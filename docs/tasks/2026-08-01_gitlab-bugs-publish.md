# gitlab-bugs-publish — публикация багов в GitLab Issues repo приложения

Основание: запрос оператора 2026-08-01 («настроить публикацию наших
багов в гитлаб и перенести все наши баги (даже минорные) туда») —
расширение решения владельца 2026-07-07 (docs/09 Этап 4 п.8: было
critical+/blocker, ждало токена).

Решения оператора 2026-08-01 (AskUserQuestion, зафиксированы):
- Скоуп: ТОЛЬКО BUG-* (11 багов приложения); AT-BUG-* (test debt,
  36 шт.) в GitLab НЕ публикуются — не адресованы разработчику.
- Полный архив: закрытые статусы (Verified/Rejected/Intended)
  переносятся как closed issues.
- Токен: оператор кладёт PAT (scope api) в env-переменную
  GITLAB_TOKEN; в репо токен не попадает.

Целевой проект: https://gitlab.com/Xartaxana1/ao3-wrapper
(источник — state/app-under-test.yaml:4).

## Узлы

| Узел | Что | Ярус | Статус |
|---|---|---|---|
| N1 | scout-разведка (docs/09 п.8, repo приложения, инвентарь bugs/, схема, заготовки) | scout (haiku) | done (accepted 14:27, сверка негатива grep-контролем) |
| N2 | Развилки оператора: скоуп / закрытые / токен | оператор | done (см. шапку) |
| N3 | builder: scripts/gitlab_sync.py + тесты + аддитивное поле схемы. owns: scripts/gitlab_sync.py, scripts/tests/test_gitlab_sync.py, schemas/bug.schema.yaml | builder (sonnet) | attempt 1 rejected (2 блокера критика: EOL-writeback, устойчивость батча); attempt 2 in flight (delegated 14:54: фиксы + labels add/remove + 4 рекомендации) |
| N4 | critic-вход приёмки N3 (правило 3а: схема данных + новый скрипт >100 строк) | critic (opus) | done (ДОРАБОТАТЬ, accepted 14:53; после attempt 2 — контрольная сверка фиксов за Lead, полный второй критик-круг не требуется при точечном дифф-ответе на блокеры) |
| N5 | Lead: приёмка, механизменный коммит (Rule-10 блок, tier: fable), встройка детектора --check в session-handoff, отметка docs/09 п.8 | Lead (fable) | done (коммит aa7f5da механизм + follow-up коммит миграции; docs/09 п.8 [X]) |
| N6 | Живая миграция 11 BUG-* (нужен GITLAB_TOKEN от оператора), сверка issues в GitLab, writeback gitlab_issue, коммит bugs/ | Lead (fable) | done 2026-08-01 (11 created; 2-й прогон 11 × unchanged; --check exit 0; adopt-поиск живьём находит BUG-011 iid=2; 2 невалидных токена оператора отсеяны диагностикой /user до прогона) |

Статус узла двигается тем же ходом, что его журнальное событие
(routing-log, task_id gitlab-bugs-publish).

## Ключевые решения спеки (для приёмки)

- Однонаправленный sync (фабрика → GitLab); канонический источник —
  bugs/*.md; правки в GitLab обратно не тянутся.
- Идемпотентность: frontmatter-поле `gitlab_issue: <iid>` (writeback
  после создания); при отсутствии поля — adopt-поиск по префиксу
  титула «BUG-NNN» до создания (защита от дублей).
- stdlib-only (urllib.request) — без новых зависимостей.
- Маппинг статусов: Open/Reopened/Fixed/Blocked → open;
  Verified/Rejected/Intended → closed (state_event).
- Labels: qa-factory, severity::<severity>, qa-status::<status>.
- Вложения (attachments/…) НЕ загружаются — ссылки остаются
  фабричными путями с пометкой в футере описания.
- `--dry-run` работает офлайн и без токена; `--check` (офлайн) —
  детектор несинхронизированных BUG-* для session-handoff.
- Labels (решение Lead 2026-08-01 по риску (в) критика): не PUT всего
  множества, а add_labels/remove_labels; снимаем только свои
  severity::/qa-status:: устаревшие, чужие метки разработчика не
  трогаем.
- DoD N6 (дополнен по вердикту N4): (1) живой прогон создаёт 11
  issues; (2) немедленный ВТОРОЙ прогон — witness «11 × unchanged»
  (эмпирический контроль идемпотентности против реального API:
  state-словарь, round-trip description, labels); любой updated во
  втором прогоне = стоп и разбор; (3) коммит bugs/ с gitlab_issue
  СРАЗУ после прогона (атомарности нет, writeback — единственный
  носитель связки до коммита); (4) разовая сверка adopt-поиска
  живым запросом /issues?search=&in=title; (5) ветка close живьём
  не проверяется (все 11 Open) — первый реальный Verified будет
  первым живым прогоном close, отметить при D1.
