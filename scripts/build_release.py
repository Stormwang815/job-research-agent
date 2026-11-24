"""Build a source-only archive using an explicit allowlist (no local runtime data)."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = {"README.md", "README.en.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "pyproject.toml", "uv.lock", ".python-version", ".env.example", ".gitignore", ".dockerignore", "Dockerfile", "docker-compose.yml"}
DIRECTORIES = {"app", "static", "tests", "scripts", ".github", "docs"}


def release_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part.startswith("__pycache__") for part in relative.parts):
            continue
        if relative.parts[0] in DIRECTORIES and path.suffix != ".pyc":
            yield path, relative
        elif str(relative) in FILES or str(relative) in {"evals/__init__.py", "evals/run_eval.py", "evals/cases.jsonl", "data/.gitkeep", "reports/.gitkeep", "var/.gitkeep"}:
            yield path, relative


if __name__ == "__main__":
    output = ROOT / "dist" / "job-research-agent-source.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, relative in release_files():
            archive.write(path, Path("job-research-agent") / relative)
    print(output)
