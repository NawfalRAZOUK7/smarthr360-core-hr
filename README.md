# smarthr360-core-hr

**Employee & organization microservice of the SmartHR360 platform.**
System of record for who works here and how they're doing: profiles,
departments, skills, performance reviews, goals, wellbeing surveys.

Part of [SmartHR360](https://github.com/NawfalRAZOUK7/smarthr360) — a
predictive HR platform built as microservices.

## Responsibilities

| App | Owns | Key APIs |
|---|---|---|
| `hr` | Department, EmployeeProfile, Skill, EmployeeSkill, FutureCompetency | `/api/hr/employees/`, `me/`, `my-team/`, `skills/`, `employee-skills/`, `future-competencies/` |
| `reviews` | ReviewCycle, PerformanceReview (Draft→Submitted→Completed), ReviewItem, Goal | `/api/reviews/cycles/`, `reviews/`, `goals/` |
| `wellbeing` | WellbeingSurvey, SurveyQuestion, SurveyResponse (pseudonymous) | `/api/wellbeing/surveys/`, `submit/`, `stats/` |

## Identity model (microservice rules)

- **No ForeignKey to the auth service.** Users exist here only as
  `user_id` values plus denormalized snapshots (`email`, `first_name`,
  `last_name`, `user_role`) refreshed from token claims.
- Authentication = local RS256 verification of `smarthr360-auth` tokens
  via [`smarthr360-jwt-auth`](https://github.com/NawfalRAZOUK7/smarthr360);
  authorization = role/group claims (`EMPLOYEE`/`MANAGER`/`HR`/`ADMIN`).
- `GET /api/hr/employees/me/` lazily creates the caller's profile from
  claims — no cross-service call needed at registration time.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

API docs: `http://localhost:8001/docs/` · Health: `/healthz/`
Tests: `python manage.py test` (13 service smoke tests minting real RS256 tokens)

## Migration notes

Extracted from the legacy monolith backend (`hr`+`reviews`+`wellbeing`).
Legacy monolith tests are kept for reference under `*/tests_legacy/`
(not collected). Fresh initial migrations; data migration from the old
DB is a separate step.
