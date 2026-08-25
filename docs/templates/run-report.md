---
id: RUN-YYYYMMDD-HHMM
suite: regression      # smoke | regression | canary | verification | compatibility
mode: FILL_ME          # replay | live — заполни ФАКТИЧЕСКИМ режимом прогона; плейсхолдер
                       # намеренно вне enum (validate_frontmatter ловит его как ERROR) — незаполненный
                       # mode не должен молча пройти как replay (критик-раунд 2, Б6)
app_version: "1.10 (versionCode 11), build <hash>"
status: NeedsTriage    # NeedsTriage | Triaged | Closed
status_since: "FILL_ME"  # ISO-таймстамп перевода в ТЕКУЩИЙ status (пример "2026-08-25T10:00:00Z");
                         # плейсхолдер намеренно не проходит pattern — SLA-детекторы (sla_sweep) не
                         # смогут определить возраст прогона без этого поля (критик-раунд 2, Б6)
updated: "FILL_ME"       # ISO-таймстамп последней правки отчёта — то же требование, тот же приём
totals: { passed: 0, failed: 0, skipped: 0, quarantined: 0, duration_min: 0 }
allure: "runs/RUN-.../allure/"
device_avd: ""         # имя AVD, на котором ШЁЛ прогон (`ao3_test_api29` / `ao3_corridor_api29` / `ao3_test_api34`).
                       # ОБЯЗАТЕЛЬНО для suite: compatibility — детектор каденции
                       # (sla_sweep._compatibility_run_wanted) без этого поля прогон не засчитывает
                       # и продолжает эскалировать. Для прочих suites — факультативно, но полезно.
blocked_reason: ""    # environment | missing_fixture | product_decision | dev_answer | permissions — заполнить при status: Blocked (docs/06 B5)
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
- [ ] Карта покрытия (`state/coverage-map.md`) перегенерирована (шаг снимка `scripts/coverage_map.py`)
