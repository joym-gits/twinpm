"""Mark every item of one phase in docs/PLAN.md as done: python scripts/plan_check.py 1"""

import re
import sys
from pathlib import Path

phase = sys.argv[1]
path = Path("docs/PLAN.md")
out, inside = [], False
for line in path.read_text().splitlines():
    if line.startswith("## Phase "):
        inside = line.startswith(f"## Phase {phase}:")
    out.append(re.sub(r"^- \[ \]", "- [x]", line) if inside else line)
path.write_text("\n".join(out) + "\n")
