"""Let the tests run from a public clone, where the private reference files are absent.

When `references/context.json` is missing, point the coach at a temporary copy of
the sample fixtures plus the tracked first lesson. With the private files present
(the installed coach) this module does nothing.
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import coach  # noqa: E402

if not (coach.SKILL / "references/context.json").exists():
    _root = Path(tempfile.mkdtemp(prefix="coach-refs-"))
    (_root / "references").mkdir()
    for _source in (
        *(HERE / "fixtures").glob("*.json"),
        coach.SKILL / "references/first.json",
    ):
        shutil.copy2(_source, _root / "references" / _source.name)
    coach.SKILL = _root
    atexit.register(shutil.rmtree, _root, ignore_errors=True)
