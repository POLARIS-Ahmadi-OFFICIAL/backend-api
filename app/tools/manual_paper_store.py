"""
Manual paper database adapter for Google Drive-backed metadata.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


class ManualPaperStore:
    def __init__(self, manifest_path: str):
        self.manifest_path = Path(manifest_path)

    def load(self) -> List[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return []
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if isinstance(raw, dict):
            papers = raw.get("papers", [])
        elif isinstance(raw, list):
            papers = raw
        else:
            papers = []

        normalized: List[Dict[str, Any]] = []
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            normalized.append(
                {
                    "title": paper.get("title", ""),
                    "doi": paper.get("doi", ""),
                    "url": paper.get("url", ""),
                    "year": paper.get("year"),
                    "source": "manual_drive",
                    "meta": paper,
                }
            )
        return normalized

    def search(self, query: str, year_min: int | None = None, year_max: int | None = None, max_candidates: int = 25) -> Dict[str, Any]:
        tokens = set(_tokenize(query))
        rows = self.load()
        scored: List[tuple[float, Dict[str, Any]]] = []
        for row in rows:
            year = row.get("year")
            if year_min is not None and isinstance(year, int) and year < year_min:
                continue
            if year_max is not None and isinstance(year, int) and year > year_max:
                continue

            haystack = " ".join(
                [
                    row.get("title", ""),
                    row.get("doi", ""),
                    row.get("url", ""),
                    json.dumps(row.get("meta", {}), ensure_ascii=False),
                ]
            )
            row_tokens = set(_tokenize(haystack))
            overlap = len(tokens.intersection(row_tokens))
            if overlap == 0 and tokens:
                continue
            score = float(overlap)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [row for _, row in scored[:max_candidates]]
        return {
            "ok": True,
            "tool": "manual_search",
            "query": query,
            "source": "manual_drive",
            "count": len(candidates),
            "candidates": candidates,
        }
