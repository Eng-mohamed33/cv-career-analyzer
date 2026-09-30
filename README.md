# AI Career & Resume Platform

منصة ويب لتحليل السيرة الذاتية ومطابقتها مع الوظائف.

## Structure

- `frontend/` — React + TypeScript + Vite
- `backend/` — FastAPI REST API (SQLite, JWT auth)
- `docs/` — project planning and architecture

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

On macOS/Linux activate with `source .venv/bin/activate`.

Optional environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | Secret used to sign login tokens. **Set this in production.** | random, saved to `backend/.jwt_secret` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:5173,http://127.0.0.1:5173` |
| `GITHUB_TOKEN` | Raises the GitHub API rate limit for skill verification | none |
| `MAX_UPLOAD_MB` | Max CV size | `5` |
| `TOKEN_TTL_SECONDS` | Login token lifetime | 7 days |
| `DATABASE_PATH` | SQLite file location | `backend/careerai.db` |

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend calls `http://localhost:8000/api` by default. To change it, copy `.env.example` to `.env.local` and edit `VITE_API_URL`.

### Tests

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Notes

- Every endpoint except `/api/health`, `/api/auth/register` and `/api/auth/login` requires a `Bearer` token, and each user only sees their own CVs.
- **GitHub verification:** if the CV contains a `github.com/username` link, the backend reads your public non-fork repos (up to 6 most recently updated). For each one it reads the language, topics, description, and the dependency files `requirements.txt`, `package.json`, `pyproject.toml` plus the root `README` (at the repo root or one folder down, e.g. `backend/` and `frontend/`). It never reads source code and cannot see private repos. Results are cached for an hour. Unauthenticated GitHub allows 60 API requests/hour, and each scan uses about 8, so set `GITHUB_TOKEN` if several people will use the app.
- **Career paths:** the dashboard ranks 6 tracks (Data Analyst, Machine Learning Engineer, AI Engineer (LLM / GenAI), Frontend, Backend, Full-Stack) by a weighted overlap between your skills and each track's core skills (see `TRACKS` in `backend/app/skills.py`, easy to edit). Only tracks with a fit of 15% or more are shown, with the skills that would strengthen each one and a button that searches jobs for it. It is a guide, not a prediction of hiring.
- CV analysis and job matching are rule-based (skill detection with word boundaries). There is no LLM yet; see `docs/PHASE-1.md`.
- Databases created before login existed are migrated automatically. Old CVs have no owner, so they are no longer listed. Old SHA-256 passwords are upgraded to bcrypt on the user's next sign-in.

## Known limitations (fine for a portfolio/local app, fix before a public launch)

- Accounts are identified by the display name only (no email), so two people cannot share a name, and there is no password reset.
- No rate limiting on `register`/`login`.
- The login token lives in `localStorage`; moving it to an `HttpOnly` cookie is safer against XSS.
- The "CV score" is a keyword-based estimate, not a real quality measure. Skill detection only knows the skills listed in `backend/app/skills.py`; add new ones to `SKILL_ALIASES` (and `PACKAGE_SKILLS` for libraries).
