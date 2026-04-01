"""File-based persistent memory with YAML frontmatter + Markdown content.

Mirrors Claude Code's memory system: each memory is a .md file with
YAML frontmatter (name, description, type) and Markdown body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    name: str
    path: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from a markdown file."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    frontmatter_str = match.group(1)
    body = match.group(2)

    metadata: dict[str, Any] = {}
    for line in frontmatter_str.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


def _build_frontmatter(metadata: dict[str, Any]) -> str:
    """Build YAML frontmatter string."""
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


class FileMemoryStore:
    """File-based persistent memory using Markdown + YAML frontmatter.

    Usage:
        store = FileMemoryStore(".agent_memory")
        store.write("user_role", "User is a senior Python developer", {
            "name": "user_role",
            "description": "User's role and expertise",
            "type": "user",
        })
        entry = store.read("user_role")
        all_entries = store.list()
    """

    def __init__(self, base_dir: str = ".agent_memory"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe_name = re.sub(r"[^\w\-.]", "_", name)
        return self.base_dir / f"{safe_name}.md"

    def read(self, name: str) -> MemoryEntry | None:
        path = self._path_for(name)
        if not path.exists():
            return None

        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(text)

        return MemoryEntry(
            name=name,
            path=str(path),
            content=body.strip(),
            metadata=metadata,
        )

    def write(
        self,
        name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        path = self._path_for(name)
        meta = metadata or {}
        meta.setdefault("name", name)

        text = _build_frontmatter(meta) + content
        path.write_text(text, encoding="utf-8")

        return MemoryEntry(
            name=name,
            path=str(path),
            content=content,
            metadata=meta,
        )

    def list(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for path in sorted(self.base_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            metadata, body = _parse_frontmatter(text)
            name = metadata.get("name", path.stem)
            entries.append(MemoryEntry(
                name=name,
                path=str(path),
                content=body.strip(),
                metadata=metadata,
            ))
        return entries

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def search(self, query: str) -> list[MemoryEntry]:
        """Simple case-insensitive substring search across all entries."""
        query_lower = query.lower()
        results: list[MemoryEntry] = []
        for entry in self.list():
            if (
                query_lower in entry.content.lower()
                or query_lower in entry.name.lower()
                or any(query_lower in str(v).lower() for v in entry.metadata.values())
            ):
                results.append(entry)
        return results
