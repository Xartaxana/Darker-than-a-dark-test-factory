# test-cases/

Тест-кейсы в формате Given-When-Then. Один файл — один кейс, по шаблону
[../docs/templates/test-case.md](../docs/templates/test-case.md).

Раскладка по областям: `test-cases/<area>/TC-xxx.md`
(`rating`, `visibility`, `tabs`, `library`, `downloads`, `filter-profiles`,
`backup`, `settings`, `browser`, `errors`, `canary`).

Область `browser` — оверлейные контролы поверх экрана Browse: side panel
(`BrowseSidePanel.kt` — тема/шрифт как второй UI-вход в тот же `SettingsViewModel`,
что и Settings) и жесты (двухпальцевый pinch/spread → шрифт, вертикальный драг →
яркость, `BrowserScreen.kt` pointerInput). Физически живут в Browse, не на экране
Settings, хотя пишут в общий с Settings стейт.

Статусная машина (YAML frontmatter `status`): `Draft → Review → Approved → Automated`.
P0/P1 в `Approved` переводит человек. Ведут: test-designer (создание),
test-automator (→ Automated), test-maintainer (правки).
