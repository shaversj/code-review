from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class DiffIndex:
    right_lines_by_path: Mapping[str, frozenset[int]]

    @classmethod
    def from_unified_diff(cls, diff: str) -> "DiffIndex":
        lines_by_path: dict[str, set[int]] = {}
        current_path: str | None = None
        right_line: int | None = None

        for line in diff.splitlines():
            if line.startswith("diff --git "):
                current_path = None
                right_line = None
                continue

            if line.startswith("+++ "):
                current_path = cls._normalize_path(line[4:])
                right_line = None
                if current_path != "/dev/null":
                    lines_by_path.setdefault(current_path, set())
                continue

            if line.startswith("@@ "):
                match = HUNK_RE.match(line)
                if match and current_path and current_path != "/dev/null":
                    right_line = int(match.group(1))
                else:
                    right_line = None
                continue

            if current_path is None or current_path == "/dev/null" or right_line is None:
                continue

            if line.startswith("\\"):
                continue
            if line.startswith("-"):
                continue
            if line.startswith("+"):
                lines_by_path.setdefault(current_path, set()).add(right_line)
                right_line += 1
                continue

            lines_by_path.setdefault(current_path, set()).add(right_line)
            right_line += 1

        return cls(
            MappingProxyType(
                {path: frozenset(lines) for path, lines in lines_by_path.items()}
            )
        )

    def has_right_line(self, path: str, line: int) -> bool:
        return line in self.right_lines_by_path.get(path, frozenset())

    @property
    def file_count(self) -> int:
        return len(self.right_lines_by_path)

    @property
    def line_count(self) -> int:
        return sum(len(lines) for lines in self.right_lines_by_path.values())

    @staticmethod
    def _normalize_path(raw_path: str) -> str:
        path = raw_path.strip()
        if path.startswith("a/") or path.startswith("b/"):
            return path[2:]
        return path
