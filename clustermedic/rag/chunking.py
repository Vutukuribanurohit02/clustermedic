"""Split runbooks into one chunk per '## ' section, with front-matter metadata attached."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    id: str            # e.g. "RB-007#diagnose-read-only"
    runbook: str       # e.g. "RB-007"
    title: str
    section: str
    text: str          # what gets embedded: title + section heading + body
    meta: dict


def parse_front_matter(md: str) -> tuple[dict, str]:
    """Minimal YAML-ish front matter: `key: value` and `key: [a, b]`. Returns (meta, body)."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        meta[k.strip()] = v
    return meta, m.group(2)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _is_empty(body: str) -> bool:
    """A section with only bullets/numbers and no words is an unfilled template."""
    return not re.search(r"[A-Za-z0-9]{2,}", re.sub(r"^\s*(?:[-*]|\d+\.)\s*$", "", body, flags=re.M))


def chunk_runbook(path: Path) -> list[Chunk]:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    rb, title = meta.get("id", path.stem), meta.get("title", path.stem)
    chunks = []
    for part in re.split(r"^## ", body, flags=re.M)[1:]:
        heading, _, section_body = part.partition("\n")
        heading, section_body = heading.strip(), section_body.strip()
        if _is_empty(section_body):
            continue  # never index empty template sections
        chunks.append(Chunk(
            id=f"{rb}#{_slug(heading)}", runbook=rb, title=title, section=heading,
            text=f"{title}\nSection: {heading}\n{section_body}",
            meta={"runbook": rb, "title": title, "section": heading,
                  "fault_type": meta.get("fault_type", ""),
                  "components": ",".join(meta.get("components", []))},
        ))
    return chunks


def chunk_dir(directory: Path, pattern: str = "RB-*.md") -> list[Chunk]:
    out = []
    for p in sorted(Path(directory).glob(pattern)):
        out.extend(chunk_runbook(p))
    return out
