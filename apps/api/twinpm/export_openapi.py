"""Write the OpenAPI document to a file: `python -m twinpm.export_openapi out.json`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from twinpm.main import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
