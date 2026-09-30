import hashlib
import os
import sqlite3
import tempfile
from io import BytesIO

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

from fastapi.testclient import TestClient  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app import main  # noqa: E402
from app.db import DATABASE_PATH  # noqa: E402
from app.skills import detect_skills  # noqa: E402

client = TestClient(main.app)
real_inspect_github = main.inspect_github  # the autouse fixture below replaces main.inspect_github


def make_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in text.splitlines():
        pdf.drawString(50, y, line)
        y -= 16
    pdf.save()
    return buffer.getvalue()


def register(name: str, password: str = "secret123") -> dict:
    response = client.post("/api/auth/register", json={"name": name, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def fake_github(username):
        return {"username": username, "url": "", "verified_skills": [], "repositories": []}

    async def fake_jobs(params):
        return [{"id": 1, "jobTitle": "Data Analyst", "companyName": "Acme", "jobGeo": "Remote",
                 "jobDescription": "<p>Python, SQL and Power BI required. Go is a plus.</p>", "url": "https://x"}]

    monkeypatch.setattr(main, "inspect_github", fake_github)
    monkeypatch.setattr(main, "fetch_jobs", fake_jobs)


# ---- skill detection (bug 1) ----

def test_html_does_not_imply_machine_learning():
    skills = detect_skills("Built pages with HTML and CSS. Digital skills, projects and results.")
    assert "HTML" in skills and "CSS" in skills
    assert "Machine Learning" not in skills
    assert "TypeScript" not in skills
    assert "Git" not in skills


def test_real_skills_are_detected():
    skills = detect_skills("Python, SQL, Power BI, React.js, TypeScript, C++ and GitHub. Java != JavaScript")
    for expected in ["Python", "SQL", "Power BI", "React", "TypeScript", "C++", "Git", "Java", "JavaScript"]:
        assert expected in skills
    assert "Java" not in detect_skills("I know JavaScript only")


# ---- auth (bugs: fake token, sha256, no ownership) ----

def test_endpoints_require_token():
    for method, path in [("get", "/api/cvs"), ("get", "/api/jobs/search"), ("get", "/api/auth/me")]:
        assert getattr(client, method)(path).status_code == 401
    assert client.get("/api/cvs", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get("/api/health").status_code == 200


def test_register_login_me_and_bcrypt():
    headers = register("Mohamed Test")
    assert client.get("/api/auth/me", headers=headers).json() == {"name": "Mohamed Test"}
    assert client.post("/api/auth/register", json={"name": "mohamed test", "password": "secret123"}).status_code == 409
    assert client.post("/api/auth/login", json={"name": "Mohamed Test", "password": "wrong-pw"}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "mohamed test", "password": "secret123"}).status_code == 200
    with sqlite3.connect(DATABASE_PATH) as db:
        stored = db.execute("SELECT password_hash FROM users WHERE username='mohamed test'").fetchone()[0]
    assert stored.startswith("$2")


def test_long_password_and_short_password():
    register("longpw", "é" * 200)
    assert client.post("/api/auth/register", json={"name": "shorty", "password": "123"}).status_code == 400


def test_legacy_sha256_hash_is_upgraded_on_login():
    legacy = hashlib.sha256(b"oldpass1").hexdigest()
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("INSERT INTO users VALUES ('legacy', 'Legacy', ?)", (legacy,))
    assert client.post("/api/auth/login", json={"name": "legacy", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "legacy", "password": "oldpass1"}).status_code == 200
    with sqlite3.connect(DATABASE_PATH) as db:
        assert db.execute("SELECT password_hash FROM users WHERE username='legacy'").fetchone()[0].startswith("$2")
    assert client.post("/api/auth/login", json={"name": "legacy", "password": "oldpass1"}).status_code == 200


# ---- CV upload / isolation / ordering ----

def upload(headers, text, name="cv.pdf"):
    return client.post("/api/cvs", headers=headers, files={"file": (name, make_pdf(text), "application/pdf")})


def test_upload_analysis_and_user_isolation():
    alice, bob = register("alice"), register("bob")
    first = upload(alice, "Summary\nExperience\nEducation\nSkills: Python SQL HTML CSS", "first.pdf")
    assert first.status_code == 201, first.text
    body = first.json()
    assert "Python" in body["skills"] and "Machine Learning" not in body["skills"]

    assert client.get("/api/cvs", headers=bob).json() == []
    assert client.get(f"/api/cvs/{body['id']}/analysis", headers=bob).status_code == 404
    assert client.get(f"/api/cvs/{body['id']}/analysis", headers=alice).status_code == 200
    payload = {"cv_id": body["id"], "job_title": "x", "job_description": "python"}
    assert client.post("/api/jobs/match", headers=bob, json=payload).status_code == 404
    assert client.get(f"/api/jobs/matches/{body['id']}", headers=bob).status_code == 404


def test_newest_cv_is_first():
    headers = register("carol")
    upload(headers, "Skills: Python", "old.pdf")
    upload(headers, "Skills: Python SQL", "new.pdf")
    listing = client.get("/api/cvs", headers=headers).json()
    assert [cv["filename"] for cv in listing] == ["new.pdf", "old.pdf"]


def test_upload_validation(monkeypatch):
    headers = register("dave")
    fake = client.post("/api/cvs", headers=headers, files={"file": ("a.pdf", b"not a pdf", "application/pdf")})
    assert fake.status_code == 400
    # Real PDF sent with a wrong content-type is still accepted (signature is what matters).
    ok = client.post("/api/cvs", headers=headers,
                     files={"file": ("a.pdf", make_pdf("Skills: Python"), "application/octet-stream")})
    assert ok.status_code == 201
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 100)
    big = client.post("/api/cvs", headers=headers, files={"file": ("a.pdf", make_pdf("Skills: Python"), "application/pdf")})
    assert big.status_code == 413


# ---- matching + recommendations (KeyError bug) ----

def test_match_persists_and_dedupes():
    headers = register("erin")
    cv = upload(headers, "Skills: Python SQL").json()
    payload = {"cv_id": cv["id"], "job_title": "Analyst", "company": "Acme",
               "job_description": "Need Python, SQL and Tableau experience"}
    result = client.post("/api/jobs/match", headers=headers, json=payload).json()
    assert result["score"] == 67 and result["missing_skills"] == ["Tableau"]
    client.post("/api/jobs/match", headers=headers, json=payload)
    stored = client.get(f"/api/jobs/matches/{cv['id']}", headers=headers).json()
    assert len(stored) == 1 and stored[0]["job_title"] == "Analyst"


def test_recommended_does_not_crash_with_github_only_skills(monkeypatch):
    async def github_with_extras(username):
        return {"username": username, "url": "", "verified_skills": ["Go", "R", "HTML", "C++", "Java"], "repositories": []}

    monkeypatch.setattr(main, "inspect_github", github_with_extras)
    headers = register("frank")
    cv = upload(headers, "Skills: Python SQL\nhttps://github.com/frank").json()
    assert "Go" in cv["skills"]
    response = client.get(f"/api/jobs/recommended/{cv['id']}", headers=headers)
    assert response.status_code == 200, response.text
    job = response.json()[0]
    assert set(job["matched_skills"]) == {"Python", "SQL"}
    assert "Go" not in job["matched_skills"]


# ---- GitHub: reading dependency files ----

from app.skills import skills_from_file  # noqa: E402


def test_skills_from_dependency_files():
    req = "fastapi>=0.115\nuvicorn[standard]\n# comment\npandas==2.0  # inline\nscikit_learn\n-r other.txt\n"
    assert skills_from_file("backend/requirements.txt", req) == {"Python", "FastAPI", "Pandas", "Machine Learning"}
    pkg = '{"dependencies": {"react": "^19", "lucide-react": "1"}, "devDependencies": {"typescript": "7", "vite": "8"}}'
    assert skills_from_file("frontend/package.json", pkg) == {"JavaScript", "React", "TypeScript"}
    toml = '[project]\ndependencies = ["numpy>=1.2", "streamlit"]\n[tool.poetry.dependencies]\ndjango = "^5"\n'
    assert skills_from_file("pyproject.toml", toml) == {"Python", "NumPy", "Streamlit", "Django"}
    assert "Docker" in skills_from_file("README.md", "Run it with Docker. HTML pages inside.")
    # malformed input must never raise
    assert skills_from_file("package.json", "{not json") == set()
    assert skills_from_file("pyproject.toml", "= = =") == set()


def test_inspect_github_reads_monorepo_files():
    import httpx

    main.GITHUB_CACHE.clear()
    repos = [
        {"name": "career-app", "default_branch": "main", "language": "TypeScript", "topics": [],
         "description": None, "html_url": "u1", "fork": False},
        {"name": "forked-stuff", "default_branch": "main", "language": "Java", "topics": [],
         "description": "", "html_url": "u2", "fork": True},
    ]
    tree = {"tree": [
        {"path": "README.md", "type": "blob"},
        {"path": "backend/requirements.txt", "type": "blob"},
        {"path": "frontend/package.json", "type": "blob"},
        {"path": "node_modules/x/package.json", "type": "blob"},
        {"path": "a/b/c/requirements.txt", "type": "blob"},
    ]}
    files = {
        "/octo/career-app/main/README.md": "A tool built with Docker.",
        "/octo/career-app/main/backend/requirements.txt": "fastapi\npandas\n",
        "/octo/career-app/main/frontend/package.json": '{"dependencies": {"react": "1"}}',
    }
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        requested.append(url.path)
        if url.host == "api.github.com":
            if url.path == "/users/octo":
                return httpx.Response(200, json={})
            if url.path == "/users/octo/repos":
                return httpx.Response(200, json=repos)
            if url.path == "/repos/octo/career-app/git/trees/main":
                return httpx.Response(200, json=tree)
        if url.host == "raw.githubusercontent.com" and url.path in files:
            return httpx.Response(200, text=files[url.path])
        return httpx.Response(404)

    import asyncio

    result = asyncio.run(real_inspect_github("octo", transport=httpx.MockTransport(handler)))
    assert {"FastAPI", "Pandas", "React", "Docker", "Python", "JavaScript", "TypeScript"} <= set(result["verified_skills"])
    assert "Java" not in result["verified_skills"]  # fork ignored
    assert [repo["name"] for repo in result["repositories"]] == ["career-app"]
    assert not any("node_modules" in path or "/a/b/c/" in path for path in requested)
    before = len(requested)
    asyncio.run(real_inspect_github("octo", transport=httpx.MockTransport(handler)))
    assert len(requested) == before  # second call served from cache


# ---- career tracks ----

from app.skills import suggest_tracks  # noqa: E402


def test_suggest_tracks_ranks_by_weighted_fit():
    tracks = suggest_tracks(["Python", "SQL", "Pandas", "NumPy", "Excel"])
    assert tracks[0]["name"] == "Data Analyst"
    assert tracks[0]["score"] == 62  # (2+3+2+1+2) / 16
    assert tracks[0]["missing_skills"] == ["Data Visualization", "Power BI", "Tableau"]
    assert tracks[0]["search_term"] == "data analyst"
    assert len(tracks) <= 3 and [t["score"] for t in tracks] == sorted((t["score"] for t in tracks), reverse=True)
    front = suggest_tracks(["JavaScript", "React", "TypeScript", "HTML", "CSS"])
    assert front[0]["name"] == "Frontend Developer" and front[0]["score"] == 80  # 12 / 15


def test_suggest_tracks_ignores_noise():
    assert suggest_tracks([]) == []
    assert suggest_tracks(["Git"]) == []  # 1 weak overlap is not a career path


def test_upload_returns_tracks_and_list_matches():
    headers = register("tracky")
    body = upload(headers, "Skills: Python SQL Excel Pandas").json()
    assert body["tracks"][0]["name"] == "Data Analyst"
    listed = client.get("/api/cvs", headers=headers).json()[0]
    assert listed["tracks"] == body["tracks"]


# ---- wider skill coverage (real CV vocabulary) ----

def test_real_cv_vocabulary_is_detected():
    text = ("Python, Pandas, Matplotlib, Seaborn, Plotly, Power BI, Random Forest, PyTorch, Transfer Learning, "
            "ResNet50, BERT sentiment analysis, Oracle DB, SQL Server, PostgreSQL, Tailwind CSS, Next.js")
    skills = detect_skills(text)
    for expected in ["Data Visualization", "Machine Learning", "Deep Learning", "NLP", "SQL", "Tailwind CSS", "Next.js"]:
        assert expected in skills, expected
    assert "LLM" not in skills  # nothing in this text is an LLM skill
    assert "LLM" in detect_skills("Built a RAG chatbot with LangChain and the Groq API")
    assert "LLM" not in detect_skills("We hit a drag and a storage error")  # 'rag' must be a whole word


def test_ai_engineer_track_needs_llm_and_serving():
    base = ["Python", "Machine Learning", "Deep Learning", "NLP"]
    without = {t["name"]: t for t in suggest_tracks(base)}["AI Engineer (LLM / GenAI)"]
    with_llm = {t["name"]: t for t in suggest_tracks(base + ["LLM", "FastAPI", "Docker"])}["AI Engineer (LLM / GenAI)"]
    assert with_llm["score"] > without["score"] and "LLM" in without["missing_skills"]


def test_unknown_user_and_wrong_password_are_indistinguishable():
    register("grace")
    wrong = client.post("/api/auth/login", json={"name": "grace", "password": "nope-nope"})
    ghost = client.post("/api/auth/login", json={"name": "nobody-here", "password": "nope-nope"})
    assert wrong.status_code == ghost.status_code == 401 and wrong.json() == ghost.json()
