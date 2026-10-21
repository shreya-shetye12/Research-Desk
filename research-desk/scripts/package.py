"""Package only source and documentation from this edition."""

import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", ".runtime", "dist", "__pycache__", ".pytest_cache", ".git", "mlruns"}
ARCHIVED_DOCS = {"docs/dashboard-verification.json"}
SUFFIX = {
    ".py",
    ".js",
    ".css",
    ".html",
    ".svg",
    ".json",
    ".md",
    ".txt",
    ".sh",
    ".yml",
    ".png",
    ".jpg",
}


def main():
    paths = sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and not (set(p.relative_to(ROOT).parts) & SKIP)
        and (p.suffix in SUFFIX or p.name == ".gitignore")
        and p.name != "CODEX_CONTEXT.md"
        and p.relative_to(ROOT).as_posix() not in ARCHIVED_DOCS
        and not (p.parent == ROOT / "docs" and p.suffix == ".png")
    )
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    target = output / "RESEARCH_DESK_SOURCE.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            info = zipfile.ZipInfo(
                "research-desk/" + path.relative_to(ROOT).as_posix()
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
            bundle.writestr(info, path.read_bytes())
    (output / "SHA256SUMS.txt").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + "  " + target.name + "\n"
    )
    print(f"{target}\n{len(paths)} source files; runtime state excluded")


if __name__ == "__main__":
    main()
