---
id: RUN-YYYYMMDD-HHMM
suite: regression      # smoke | regression | canary | verification
mode: replay           # replay | live
app_version: "1.10 (versionCode 11), build <hash>"
status: NeedsTriage    # NeedsTriage | Triaged | Closed
totals: { passed: 0, failed: 0, skipped: 0, quarantined: 0, duration_min: 0 }
allure: "runs/RUN-.../allure/"
lock: ""
---

# RUN-YYYYMMDD-HHMM — {suite} на {app_version}

## Контекст запуска
Триггер (новая сборка / расписание / верификация BUG-xxx), эмулятор, commit фреймворка.

## Падения и триаж

| Тест (TC) | Ошибка (кратко) | Вердикт | Действие | Ссылка |
|---|---|---|---|---|
| test_restore_filter_profiles (TC-031) | assert profiles == 2, got 0 | APP_BUG | создан баг | BUG-014 |
| canary/test_blurb_selector | li.work.blurb not found | SITE_CHANGED | recordings обновлены | commit abc123 |

Вердикты: `APP_BUG` — дефект приложения → bug-reporter; `TEST_BUG` — дефект теста →
test-maintainer; `SITE_CHANGED` — AO3 изменил DOM → test-maintainer;
`ENV_ISSUE` — эмулятор/proxy/сеть → перезапуск + фикс окружения;
`FLAKY` — нестабильность → карантин + задача на стабилизацию.

## Условия закрытия прогона (Closed)
- [ ] Каждое падение имеет вердикт и связанное действие (баг / фикс теста / карантин)
- [ ] Для APP_BUG существует или создан BUG-файл
- [ ] Traceability (`state/traceability.md`) обновлена статусами последнего прогона
