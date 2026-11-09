# Phase 1 validation

Validated on 2026-11-09 from Kali Linux WSL2 and Windows PowerShell.

| Check | Result |
| --- | --- |
| Docker Compose configuration | Passed |
| Backend and frontend Docker builds | Passed |
| Python runtime | 3.13.18 |
| Node.js runtime | 24.22.2 |
| PostgreSQL runtime | 17.11 |
| Django system check | No issues |
| Python dependency check | No broken requirements |
| Django tests | 1 health endpoint test passed |
| Framework database migrations | Applied successfully |
| Missing migrations check | No changes detected |
| React production build | Passed, Vite 7.3.7 |
| npm dependency audit | 0 known vulnerabilities at installation |
| Django health endpoint, port 8000 | HTTP 200, status ok |
| Vite API proxy, port 5173 | HTTP 200, status ok |
| Frontend HTML, port 5173 | HTTP 200 |
| Windows localhost access | Django health and frontend HTML passed |
| PostgreSQL host port | None published |
| Existing README and .gitignore | Unchanged |
| Existing Git configuration | SHA-256 unchanged after scaffolding |
| Local .env | Created from example; verified ignored by Git |

Django 5.2.19 and Django REST Framework 3.16.1 were installed.
All three development containers were left running. PostgreSQL uses a persistent
named volume. Only Django framework tables were created; the six application
model modules remain empty. No Excel data was imported. No commit or push was made.

Validation covers scaffold operation and HTTP responses. It does not include
browser automation or production readiness. See development.md for repeatable commands.
