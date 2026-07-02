# runs/

Отчёты о прогонах. Один файл — один прогон, по шаблону
[../docs/templates/run-report.md](../docs/templates/run-report.md):
`runs/RUN-<timestamp>.md` + рядом каталог артефактов/Allure.

Статусная машина (YAML frontmatter `status`): `NeedsTriage → Triaged → Closed`.
Ведут: test-runner (создание), failure-analyst (вердикты → Triaged),
bug-reporter/test-maintainer (закрытие пунктов → Closed).
