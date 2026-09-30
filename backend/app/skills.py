"""Skill detection with strict word boundaries.

The old implementation used ``alias in text``, so "ml" matched inside "html",
"ts" matched inside "skills", and "git" matched inside "digital".
"""
import json
import re
import tomllib
from functools import lru_cache
from typing import Iterator

SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python", "python3"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "sqlite", "oracle db", "sql server", "pl/sql"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Excel": ["excel", "microsoft excel"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Machine Learning": ["machine learning", "ml", "scikit-learn", "sklearn", "random forest", "xgboost", "lightgbm", "supervised learning"],
    "Deep Learning": ["deep learning", "tensorflow", "pytorch", "keras", "transfer learning", "neural network", "neural networks", "resnet", "resnet50", "efficientnet", "computer vision"],
    "NLP": ["nlp", "natural language processing", "sentiment analysis", "bert", "nltk", "spacy"],
    "LLM": ["llm", "llms", "large language model", "large language models", "rag", "langchain", "openai", "groq"],
    "Data Visualization": ["data visualization", "data visualisation", "matplotlib", "seaborn", "plotly"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"],
    "React": ["react", "react.js", "reactjs"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Java": ["java"],
    "C++": ["c++"],
    "Git": ["git", "github"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Django": ["django"],
    "Node.js": ["node.js", "nodejs"],
    "Next.js": ["next.js", "nextjs"],
    "Tailwind CSS": ["tailwind css", "tailwindcss", "tailwind"],
    "Streamlit": ["streamlit"],
    "Docker": ["docker"],
}

# Skills that can be verified through GitHub languages but are too ambiguous
# ("go", "r") to be detected reliably in free text.
GITHUB_ONLY_SKILLS = {"Go", "R"}

# Suggested "gap" skills for a data-oriented profile.
SUGGESTED_SKILLS = ("Excel", "Power BI", "Tableau")


@lru_cache(maxsize=None)
def _pattern(alias: str) -> re.Pattern[str]:
    # \w covers letters/digits/underscore; + and # keep "c++" / "c#" intact.
    return re.compile(rf"(?<![\w+#]){re.escape(alias)}(?![\w+#])", re.IGNORECASE)


def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def skill_in_text(skill: str, text: str) -> bool:
    aliases = SKILL_ALIASES.get(skill)
    if not aliases:
        return False
    return any(_pattern(alias).search(text) for alias in aliases)


def detect_skills(text: str) -> list[str]:
    normalized = normalize(text)
    return [skill for skill in SKILL_ALIASES if skill_in_text(skill, normalized)]


# ---------- dependency files ----------

# Package name (as written in requirements.txt / package.json) -> skill.
PACKAGE_SKILLS: dict[str, str] = {
    "pandas": "Pandas", "numpy": "NumPy",
    "scikit-learn": "Machine Learning", "sklearn": "Machine Learning", "xgboost": "Machine Learning",
    "lightgbm": "Machine Learning",
    "tensorflow": "Deep Learning", "torch": "Deep Learning", "pytorch": "Deep Learning", "keras": "Deep Learning",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "streamlit": "Streamlit",
    "sqlalchemy": "SQL", "psycopg2": "SQL", "psycopg2-binary": "SQL", "psycopg": "SQL", "pymysql": "SQL",
    "react": "React", "react-dom": "React", "next": "Next.js", "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS", "express": "Node.js",
    "matplotlib": "Data Visualization", "seaborn": "Data Visualization", "plotly": "Data Visualization", "dash": "Data Visualization",
    "transformers": "NLP", "nltk": "NLP", "spacy": "NLP",
    "openai": "LLM", "langchain": "LLM", "groq": "LLM", "llama-index": "LLM",
}

MANIFEST_FILES = {"requirements.txt", "package.json", "pyproject.toml"}
README_NAMES = {"readme.md", "readme.rst", "readme.txt", "readme"}


def is_readable_file(name: str, at_root: bool) -> bool:
    lowered = name.lower()
    return lowered in MANIFEST_FILES or (at_root and lowered in README_NAMES)


def _requirement_names(lines: list[str]) -> Iterator[str]:
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)
        if match:
            yield match.group(0).lower().replace("_", "-")


def _map_packages(names: Iterator[str] | list[str]) -> set[str]:
    return {PACKAGE_SKILLS[name] for name in names if name in PACKAGE_SKILLS}


def skills_from_file(path: str, text: str) -> set[str]:
    """Skills implied by one repository file. Never raises on malformed input."""
    name = path.rsplit("/", 1)[-1].lower()
    skills: set[str] = set()
    try:
        if name == "requirements.txt":
            skills |= {"Python"} | _map_packages(_requirement_names(text.splitlines()))
        elif name == "package.json":
            data = json.loads(text)
            names = [
                package.lower()
                for section in ("dependencies", "devDependencies", "peerDependencies")
                for package in (data.get(section) or {})
            ]
            skills |= {"JavaScript"} | _map_packages(names)
        elif name == "pyproject.toml":
            data = tomllib.loads(text)
            project = data.get("project", {})
            dependencies = list(project.get("dependencies", []))
            for group in (project.get("optional-dependencies") or {}).values():
                dependencies.extend(group)
            dependencies.extend((data.get("tool", {}).get("poetry", {}).get("dependencies") or {}).keys())
            skills |= {"Python"} | _map_packages(_requirement_names(dependencies))
        elif name in README_NAMES:
            skills |= set(detect_skills(text[:8000]))
    except (ValueError, AttributeError, TypeError):  # bad JSON/TOML or unexpected structure
        pass
    return skills


# ---------- career tracks ----------

# skill -> weight (how central it is to the track). `search_term` feeds the job search.
TRACKS: dict[str, dict] = {
    "Data Analyst": {
        "search_term": "data analyst",
        "skills": {"SQL": 3, "Python": 2, "Excel": 2, "Power BI": 2, "Tableau": 2, "Pandas": 2, "Data Visualization": 2, "NumPy": 1},
    },
    "Machine Learning Engineer": {
        "search_term": "machine learning",
        "skills": {"Python": 3, "Machine Learning": 3, "Deep Learning": 3, "Pandas": 1, "NumPy": 1, "NLP": 1, "Docker": 1, "FastAPI": 1},
    },
    "AI Engineer (LLM / GenAI)": {
        "search_term": "ai engineer",
        "skills": {"Python": 3, "LLM": 3, "Machine Learning": 2, "Deep Learning": 2, "NLP": 2, "FastAPI": 2, "Docker": 1, "Git": 1},
    },
    "Frontend Developer": {
        "search_term": "frontend",
        "skills": {"JavaScript": 3, "React": 3, "TypeScript": 2, "HTML": 2, "CSS": 2, "Tailwind CSS": 1, "Next.js": 1, "Git": 1},
    },
    "Backend Developer": {
        "search_term": "backend",
        "skills": {"SQL": 3, "Python": 2, "FastAPI": 2, "Django": 2, "Flask": 2, "Node.js": 2, "Docker": 1, "Java": 1, "Git": 1},
    },
    "Full-Stack Developer": {
        "search_term": "full stack",
        "skills": {"React": 2, "JavaScript": 2, "TypeScript": 1, "Node.js": 1, "Python": 1, "SQL": 2, "FastAPI": 1, "Django": 1, "Docker": 1, "Git": 1},
    },
}
MIN_TRACK_SCORE = 15  # below this a track is noise, not a real fit


def suggest_tracks(skills: list[str], limit: int = 3) -> list[dict]:
    """Rank career tracks by how much of each track's weighted skill list the person already has."""
    owned = set(skills)
    results = []
    for name, track in TRACKS.items():
        weights: dict[str, int] = track["skills"]
        score = round(sum(weight for skill, weight in weights.items() if skill in owned) / sum(weights.values()) * 100)
        if score < MIN_TRACK_SCORE:
            continue
        by_weight = sorted(weights, key=lambda skill: (-weights[skill], skill))
        results.append({
            "name": name,
            "score": score,
            "matched_skills": [skill for skill in by_weight if skill in owned],
            "missing_skills": [skill for skill in by_weight if skill not in owned][:3],
            "search_term": track["search_term"],
        })
    results.sort(key=lambda track: (-track["score"], track["name"]))
    return results[:limit]
