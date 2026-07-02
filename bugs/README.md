# bugs/

Реестр дефектов приложения. Один файл — один баг, по шаблону
[../docs/templates/bug-report.md](../docs/templates/bug-report.md).

Статусная машина (YAML frontmatter `status`):
`Open → Fixed → Verified` (закрыт); `Fixed → Reopened`; `Open → Rejected/Intended/Blocked`.

**Переход `Open → Fixed` делает только человек** (разработчик приложения). Агенты
находят и верифицируют баги, но НИКОГДА не правят код приложения. Ведут:
bug-reporter (создание), fix-verifier (Verified/Reopened), человек (Fixed/Rejected).
