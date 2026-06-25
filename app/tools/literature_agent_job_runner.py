"""Small durable subprocess runner used by the POLARIS LiteratureAgent service."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    return_code = subprocess.call(payload["command"])
    Path(payload["job_dir"], f"{payload['job_id']}.returncode").write_text(str(return_code), encoding="utf-8")
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
