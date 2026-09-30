import asyncio
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pypdf import PdfReader

from .db import get_db, init_database
from .security import DUMMY_HASH, create_token, decode_token, hash_password, verify_password
from .skills import (
    GITHUB_ONLY_SKILLS,
    SKILL_ALIASES,
    SUGGESTED_SKILLS,
    detect_skills,
    is_readable_file,
    normalize,
    skill_in_text,
    skills_from_file,
    suggest_tracks,
)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
MAX_PDF_PAGES = 30
JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

app = FastAPI(title="AI Career & Resume Platform API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_database()
bearer_scheme = HTTPBearer(auto_error=False)


# ---------- schemas ----------

class TrackFit(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    search_term: str


class CVRecord(BaseModel):
    id: UUID
    filename: str
    uploaded_at: datetime
    status: str = "analyzed"
    score: int = Field(ge=0, le=100)
    skills: list[str] = []
    tracks: list[TrackFit] = []


class MatchRequest(BaseModel):
    cv_id: UUID
    job_title: str = Field(max_length=300)
    company: str = Field(default="", max_length=300)
    job_description: str = Field(max_length=30000)


class MatchResponse(BaseModel):
    job_title: str = ""
    company: str = ""
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    recommendations: list[str]


class AuthRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(max_length=256)


class AuthResponse(BaseModel):
    name: str
    token: str


class MeResponse(BaseModel):
    name: str


class JobRecommendation(BaseModel):
    id: str
    title: str
    company: str
    location: str
    match_score: int
    matched_skills: list[str]
    description: str
    url: str
    source: str = "Jobicy"


# ---------- auth ----------

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict[str, str]:
    unauthorized = HTTPException(
        status_code=401, detail="Please sign in to continue", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        username = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    with get_db() as db:
        row = db.execute("SELECT username, display_name FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise unauthorized
    return {"username": row["username"], "name": row["display_name"]}


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register(request: AuthRequest) -> AuthResponse:
    display_name = request.name.strip()
    if not display_name or len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Name is required and password must be at least 6 characters")
    username = display_name.lower()
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
                (username, display_name, hash_password(request.password)),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="This name is already registered") from None
    return AuthResponse(name=display_name, token=create_token(username))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(request: AuthRequest) -> AuthResponse:
    username = request.name.strip().lower()
    with get_db() as db:
        user = db.execute(
            "SELECT display_name, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        valid, needs_rehash = verify_password(request.password, user["password_hash"] if user else DUMMY_HASH)
        if not user or not valid:
            raise HTTPException(status_code=401, detail="Invalid name or password")
        if needs_rehash:  # transparently upgrade legacy SHA-256 hashes to bcrypt
            db.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(request.password), username)
            )
    return AuthResponse(name=user["display_name"], token=create_token(username))


@app.get("/api/auth/me", response_model=MeResponse)
def me(user: dict = Depends(current_user)) -> MeResponse:
    return MeResponse(name=user["name"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "resume-platform-api"}


# ---------- CV analysis ----------

def extract_github_username(text: str) -> str | None:
    match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]+)(?:/[^\s]*)?", text, re.IGNORECASE)
    if not match:
        return None
    username = match.group(1)
    return None if username.lower() in {"features", "topics", "orgs", "collections", "marketplace"} else username


def analyze_cv_text(text: str) -> dict:
    normalized = normalize(text)
    skills = detect_skills(text)
    sections = sum(1 for section in ("experience", "education", "skills", "projects", "summary") if section in normalized)
    # Conservative MVP score: skills alone cannot produce an excellent score.
    skill_points = min(len(skills) * 4, 32)
    section_points = min(sections * 5, 25)
    content_points = min(len(text.strip()) // 140, 18)
    score = min(95, max(20, 25 + skill_points + section_points + content_points))
    missing = [name for name in SUGGESTED_SKILLS if name not in skills]
    suggestions = []
    if not skills:
        suggestions.append("Add a dedicated skills section with your technical tools.")
    if "experience" not in normalized:
        suggestions.append("Add an Experience section with measurable achievements.")
    if missing:
        suggestions.append(f"Consider adding relevant experience with {missing[0]}.")
    return {
        "skills": skills,
        "missing_skills": missing,
        "suggestions": suggestions[:3],
        "score": score,
        "github_username": extract_github_username(text),
        "github_verified_skills": [],
        "github_repositories": [],
    }


GITHUB_CACHE: dict[str, tuple[float, dict]] = {}
GITHUB_CACHE_TTL_SECONDS = 3600  # also protects the 60 requests/hour anonymous GitHub limit
MAX_REPOS_SCANNED = 6
MAX_FILES_PER_REPO = 4
MAX_FILE_BYTES = 200_000
IGNORED_DIRS = {"node_modules", ".venv", "venv", "env", "dist", "build", "vendor", "site-packages", "__pycache__"}
LANGUAGE_TO_SKILL = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript", "sql": "SQL",
    "jupyter notebook": "Python", "html": "HTML", "css": "CSS", "java": "Java", "c++": "C++",
    "go": "Go", "r": "R",
}


def pick_files_to_read(tree: list[dict]) -> list[str]:
    """Choose dependency files / README at the repo root or one folder down (e.g. backend/, frontend/)."""
    candidates = []
    for entry in tree:
        parts = str(entry.get("path", "")).split("/")
        if entry.get("type") != "blob" or len(parts) > 2:
            continue
        if any(part in IGNORED_DIRS for part in parts[:-1]):
            continue
        if is_readable_file(parts[-1], at_root=len(parts) == 1):
            candidates.append("/".join(parts))
    candidates.sort(key=lambda path: (path.count("/"), path))
    return candidates[:MAX_FILES_PER_REPO]


async def scan_repo(api: httpx.AsyncClient, raw: httpx.AsyncClient, gate: asyncio.Semaphore, username: str, repo: dict) -> set[str]:
    """Skills found in the repo's dependency files and README. Failures just mean 'nothing found'."""
    branch = quote(repo.get("default_branch") or "main", safe="/")
    found: set[str] = set()
    async with gate:
        try:
            tree_response = await api.get(
                f"https://api.github.com/repos/{username}/{repo['name']}/git/trees/{branch}", params={"recursive": "1"}
            )
            if tree_response.status_code != 200:
                return found
            for path in pick_files_to_read(tree_response.json().get("tree", [])):
                file_response = await raw.get(
                    f"https://raw.githubusercontent.com/{username}/{repo['name']}/{branch}/{quote(path)}"
                )
                if file_response.status_code == 200 and len(file_response.content) <= MAX_FILE_BYTES:
                    found |= skills_from_file(path, file_response.text)
        except (httpx.HTTPError, ValueError):
            pass
    return found


async def inspect_github(username: str, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    cache_key = username.lower()
    cached = GITHUB_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < GITHUB_CACHE_TTL_SECONDS:
        return cached[1]

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "CareerAI-resume-analyzer"}
    if os.getenv("GITHUB_TOKEN"):  # optional: lifts the 60 requests/hour anonymous limit
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    # Separate client for raw file downloads so the token is never sent to raw.githubusercontent.com.
    async with httpx.AsyncClient(timeout=10, headers=headers, transport=transport) as api, \
            httpx.AsyncClient(timeout=10, transport=transport) as raw:
        profile_response = await api.get(f"https://api.github.com/users/{username}")
        if profile_response.status_code == 404:
            return {"username": username, "url": f"https://github.com/{username}", "verified_skills": [], "repositories": []}
        profile_response.raise_for_status()
        repositories_response = await api.get(
            f"https://api.github.com/users/{username}/repos", params={"per_page": 100, "sort": "updated"}
        )
        repositories_response.raise_for_status()
        # Forks are other people's code, so they say nothing about the user's own skills.
        own_repos = [repo for repo in repositories_response.json() if not repo.get("fork")]
        targets = [repo for repo in own_repos if not repo.get("archived")][:MAX_REPOS_SCANNED]
        gate = asyncio.Semaphore(4)
        scanned = await asyncio.gather(*(scan_repo(api, raw, gate, username, repo) for repo in targets))
    from_files = {repo["name"]: skills for repo, skills in zip(targets, scanned)}

    verified: set[str] = set()
    public_repositories = []
    for repository in own_repos:
        repo_skills: set[str] = set(from_files.get(repository["name"], set()))
        language = (repository.get("language") or "").lower()
        if language in LANGUAGE_TO_SKILL:
            repo_skills.add(LANGUAGE_TO_SKILL[language])
        for topic in (str(topic).lower() for topic in repository.get("topics", [])):
            for skill, aliases in SKILL_ALIASES.items():
                if topic in aliases:
                    repo_skills.add(skill)
        repo_skills.update(detect_skills(f"{repository.get('name') or ''} {repository.get('description') or ''}"))
        verified |= repo_skills
        public_repositories.append({
            "name": repository.get("name"), "url": repository.get("html_url"),
            "language": repository.get("language"), "description": repository.get("description"),
            "skills": sorted(repo_skills),
        })
    result = {
        "username": username, "url": f"https://github.com/{username}",
        "verified_skills": sorted(verified), "repositories": public_repositories[:10],
    }
    if len(GITHUB_CACHE) > 500:
        GITHUB_CACHE.clear()
    GITHUB_CACHE[cache_key] = (time.monotonic(), result)
    return result


def clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def extract_pdf_text(contents: bytes) -> str:
    reader = PdfReader(BytesIO(contents))
    return "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])


def owned_cv_analysis(db: sqlite3.Connection, cv_id: UUID, username: str) -> dict:
    """Load a CV's analysis only if it belongs to the user; otherwise behave as if it does not exist."""
    row = db.execute("SELECT analysis_json FROM cvs WHERE id = ? AND user_id = ?", (str(cv_id), username)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="CV not found")
    return json.loads(row["analysis_json"])


def cv_record_from_row(row: sqlite3.Row) -> CVRecord:
    analysis = json.loads(row["analysis_json"])
    return CVRecord(
        id=UUID(row["id"]), filename=row["filename"], uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        score=row["score"], skills=analysis.get("skills", []),
        tracks=[TrackFit(**track) for track in suggest_tracks(analysis.get("skills", []))],
    )


@app.post("/api/cvs", response_model=CVRecord, status_code=201)
async def upload_cv(file: UploadFile = File(...), user: dict = Depends(current_user)) -> CVRecord:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"PDF is too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")
    # Trust the file's own signature, not the client-supplied Content-Type.
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    try:
        text = await run_in_threadpool(extract_pdf_text, contents)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this PDF file") from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="No readable text was found in this PDF")

    analysis = analyze_cv_text(text)
    if analysis["github_username"]:
        try:
            github_data = await inspect_github(analysis["github_username"])
            analysis["github_verified_skills"] = github_data["verified_skills"]
            analysis["github_repositories"] = github_data["repositories"]
            all_skills = sorted(set(analysis["skills"]) | set(github_data["verified_skills"]))
            analysis["skills"] = all_skills
            analysis["missing_skills"] = [name for name in SUGGESTED_SKILLS if name not in all_skills]
            analysis["score"] = min(95, analysis["score"] + min(len(github_data["verified_skills"]) * 2, 10))
        except (httpx.HTTPError, ValueError):
            pass  # A GitHub rate limit or unavailable profile must not block CV analysis.

    cv = CVRecord(
        id=uuid4(), filename=Path(file.filename).name, uploaded_at=datetime.now(timezone.utc),
        score=analysis["score"], skills=analysis["skills"],
        tracks=[TrackFit(**track) for track in suggest_tracks(analysis["skills"])],
    )
    with get_db() as db:
        db.execute(
            "INSERT INTO cvs (id, user_id, filename, uploaded_at, score, analysis_json) VALUES (?, ?, ?, ?, ?, ?)",
            (str(cv.id), user["username"], cv.filename, cv.uploaded_at.isoformat(), cv.score,
             json.dumps({"cv_id": str(cv.id), **analysis})),
        )
    return cv


@app.get("/api/cvs", response_model=list[CVRecord])
def list_cvs(user: dict = Depends(current_user)) -> list[CVRecord]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, filename, uploaded_at, score, analysis_json FROM cvs WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user["username"],),
        ).fetchall()
    return [cv_record_from_row(row) for row in rows]


@app.get("/api/cvs/{cv_id}/analysis")
def get_analysis(cv_id: UUID, user: dict = Depends(current_user)) -> dict:
    with get_db() as db:
        return owned_cv_analysis(db, cv_id, user["username"])


# ---------- jobs ----------

@app.post("/api/jobs/match", response_model=MatchResponse)
def match_job(request: MatchRequest, user: dict = Depends(current_user)) -> MatchResponse:
    with get_db() as db:
        cv_skills = owned_cv_analysis(db, request.cv_id, user["username"])["skills"]
        description = normalize(request.job_description)
        job_skills = detect_skills(description)
        matched = [skill for skill in job_skills if skill in cv_skills]
        missing = [skill for skill in job_skills if skill not in cv_skills]
        score = round(len(matched) / len(job_skills) * 100) if job_skills else 0
        result = MatchResponse(
            job_title=request.job_title, company=request.company, score=score,
            matched_skills=matched, missing_skills=missing,
            recommendations=[f"Build evidence for {missing[0]} in a project or experience section."]
            if missing else (["Your CV covers the detected skills for this role."] if job_skills
                             else ["No known skills were detected in this job description."]),
        )
        db.execute(
            "INSERT INTO job_matches (cv_id, user_id, result_json, created_at) VALUES (?, ?, ?, ?)",
            (str(request.cv_id), user["username"], result.model_dump_json(), datetime.now(timezone.utc).isoformat()),
        )
    return result


@app.get("/api/jobs/matches/{cv_id}", response_model=list[MatchResponse])
def list_job_matches(cv_id: UUID, user: dict = Depends(current_user)) -> list[MatchResponse]:
    with get_db() as db:
        owned_cv_analysis(db, cv_id, user["username"])
        rows = db.execute(
            "SELECT result_json FROM job_matches WHERE cv_id = ? AND user_id = ? ORDER BY id DESC",
            (str(cv_id), user["username"]),
        ).fetchall()
    seen: set[tuple[str, str]] = set()
    results = []
    for row in rows:  # newest first; keep only the latest analysis per job
        match = MatchResponse(**json.loads(row["result_json"]))
        key = (match.job_title, match.company)
        if key not in seen:
            seen.add(key)
            results.append(match)
    return results


async def fetch_jobs(params: dict) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(JOBICY_URL, params=params)
            response.raise_for_status()
            return response.json().get("jobs", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The free jobs source is temporarily unavailable") from exc


def to_recommendation(job: dict, match_score: int = 0, matched: list[str] | None = None) -> JobRecommendation:
    return JobRecommendation(
        id=str(job.get("id", "")), title=job.get("jobTitle", "Unknown role"),
        company=job.get("companyName", "Unknown company"), location=job.get("jobGeo", "Remote"),
        match_score=match_score, matched_skills=matched or [],
        description=clean_html(job.get("jobDescription", "")), url=job.get("url", "https://jobicy.com/jobs"),
    )


@app.get("/api/jobs/recommended/{cv_id}", response_model=list[JobRecommendation])
async def recommended_jobs(cv_id: UUID, user: dict = Depends(current_user)) -> list[JobRecommendation]:
    with get_db() as db:
        cv_skills = owned_cv_analysis(db, cv_id, user["username"])["skills"]
    # Skills like "Go"/"R" come from GitHub only and cannot be detected reliably in job text.
    detectable = [skill for skill in cv_skills if skill in SKILL_ALIASES and skill not in GITHUB_ONLY_SKILLS]
    jobs = await fetch_jobs({"count": 20, "tag": detectable[0] if detectable else "software"})
    recommendations = []
    for job in jobs:
        content = normalize(f"{job.get('jobTitle', '')} {clean_html(job.get('jobDescription', ''))}")
        matched = [skill for skill in detectable if skill_in_text(skill, content)]
        score = round(len(matched) / len(detectable) * 100) if detectable else 0
        recommendations.append(to_recommendation(job, score, matched))
    return sorted(recommendations, key=lambda item: item.match_score, reverse=True)[:5]


@app.get("/api/jobs/search", response_model=list[JobRecommendation])
async def search_jobs(query: str = "", user: dict = Depends(current_user)) -> list[JobRecommendation]:
    params: dict = {"count": 100}
    if query.strip():
        params["tag"] = query.strip()
    return [to_recommendation(job) for job in await fetch_jobs(params)]
