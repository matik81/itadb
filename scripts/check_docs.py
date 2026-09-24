"""Check repository-local Markdown links and heading anchors, without network access."""

import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

LINK = re.compile(r"!?\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+\"[^\"]*\")?\)")


def prose(text: str) -> str:
    """Exclude fenced examples from both links and headings."""
    lines = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if not fence:
            lines.append(line)
    return "\n".join(lines)


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(text), re.MULTILINE):
        heading = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]*>", "", heading).lower()
        slug = "".join(
            character
            for character in heading
            if character in "_- " or unicodedata.category(character)[0] in "LN"
        ).replace(" ", "-")
        candidate, index = slug, 0
        while candidate in found:
            index += 1
            candidate = f"{slug}-{index}"
        found.add(candidate)
    found.update(re.findall(r'(?:id|name)=["\']([^"\']+)["\']', text))
    return found


def check_links(root: Path, paths: list[Path]) -> list[str]:
    errors = []
    headings: dict[Path, set[str]] = {}
    for path in paths:
        for match in LINK.finditer(prose(path.read_text(encoding="utf-8"))):
            target = match[1]
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            destination = (
                (root / unquote(parts.path).lstrip("/"))
                if parts.path.startswith("/")
                else (path.parent / unquote(parts.path) if parts.path else path)
            ).resolve()
            if not destination.is_relative_to(root):
                errors.append(f"{path.relative_to(root)}: outside repository: {target}")
            elif not destination.exists():
                errors.append(f"{path.relative_to(root)}: missing file: {target}")
            elif parts.fragment and destination.suffix == ".md":
                if destination not in headings:
                    headings[destination] = anchors(destination.read_text(encoding="utf-8"))
                if unquote(parts.fragment) not in headings[destination]:
                    errors.append(f"{path.relative_to(root)}: missing anchor: {target}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    paths = sorted({root / p for p in names if p.endswith(".md") and (root / p).is_file()})
    errors = check_links(root, paths)
    for error in errors:
        print(error)
    print(f"Documenti controllati: {len(paths)}; errori: {len(errors)}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
