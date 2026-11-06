"""Build a portable source bundle without credentials, raw data or runtime files."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    output = root.parent / "data-analysis-agent-source.zip"
    files = [
        "README.md",
        "PROJECT_STATE.md",
        "AGENTS.md",
        "pyproject.toml",
        "requirements-lock.txt",
        ".env.example",
        ".gitignore",
        "start.ps1",
        "stop.ps1",
        ".streamlit/config.toml",
        "reports/evaluation_demo.json",
        "reports/public_validation.json",
        "reports/ui-preview.jpg",
        "reports/examples/index.html",
        "reports/examples/index.json",
    ]
    paths = [root / name for name in files]
    for folder in [
        "src",
        "tests",
        "scripts",
        "docs",
        "reports/examples/synthetic-gift-coverage",
        "reports/examples/synthetic-viewer-activity",
        "reports/examples/synthetic-gift-value",
    ]:
        paths.extend(
            path
            for path in (root / folder).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not any(part.endswith(".egg-info") for part in path.parts)
        )
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, Path(root.name) / path.relative_to(root))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(
            not {".env", ".venv", "data", "work", "runs", "__pycache__"}.intersection(
                Path(name).parts
            )
            for name in archive.namelist()
        )
        print(f"Created {output} ({len(archive.namelist())} files)")


if __name__ == "__main__":
    main()
