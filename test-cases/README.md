# test-cases/

Тест-кейсы в формате Given-When-Then. Один файл — один кейс, по шаблону
[../docs/templates/test-case.md](../docs/templates/test-case.md).

Раскладка по областям: `test-cases/<area>/TC-xxx.md`
(`rating`, `visibility`, `tabs`, `library`, `downloads`, `filter-profiles`,
`backup`, `settings`, `errors`, `canary`).

Статусная машина (YAML frontmatter `status`): `Draft → Review → Approved → Automated`.
P0/P1 в `Approved` переводит человек. Ведут: test-designer (создание),
test-automator (→ Automated), test-maintainer (правки).
