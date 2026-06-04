from __future__ import annotations

import json

from app.tools.manual_paper_store import ManualPaperStore


def test_manual_store_search(tmp_path):
    manifest = tmp_path / "papers.json"
    manifest.write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Perovskite stability with additive A",
                        "doi": "10.1000/example1",
                        "year": 2024,
                        "url": "https://example.org/p1",
                    },
                    {
                        "title": "Unrelated biology paper",
                        "doi": "10.1000/example2",
                        "year": 2023,
                        "url": "https://example.org/p2",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    store = ManualPaperStore(str(manifest))
    result = store.search("perovskite additive", year_min=2020, year_max=2026, max_candidates=10)
    assert result["ok"] is True
    assert result["count"] == 1
    assert "Perovskite" in result["candidates"][0]["title"]
