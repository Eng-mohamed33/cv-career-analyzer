# Phase 1 — MVP Definition

## Primary user

Job seeker who wants to understand CV quality and suitability for a target role.

## MVP user journey

1. User uploads a PDF CV.
2. System extracts and stores the CV metadata.
3. System returns an initial analysis.
4. User reviews score, skills, gaps, and recommendations.
5. User pastes a job description.
6. System calculates a match score and explains the gaps.

## Initial API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service health check |
| POST | `/api/cvs` | Upload a CV |
| GET | `/api/cvs` | List uploaded CVs |
| GET | `/api/cvs/{id}/analysis` | Get CV analysis |
| POST | `/api/jobs/match` | Match a CV against a job description |

## Next milestones

- Add PostgreSQL and SQLAlchemy persistence.
- Add JWT authentication.
- Replace mock analysis with PDF extraction and an LLM provider.
- Add background jobs for long-running analysis.

## Status (v0.2)

- Done: SQLite persistence, JWT authentication (bcrypt), per-user CV ownership, GitHub skill verification (languages, topics, dependency files, README), live job search (Jobicy), automated backend tests.
- Still open: PostgreSQL, rate limiting on auth endpoints, replacing rule-based analysis with an LLM provider, background jobs.
