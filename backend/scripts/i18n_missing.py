"""
Konbit — Mesaj backend ki poko tradui
Chemen: backend/scripts/i18n_missing.py

Kouri l nan backend\\:
    python scripts/i18n_missing.py

Li li tout fichye .py nan app/, jwenn chak HTTPException(detail=...) ak
ValueError(...), epi li montre sa app/i18n.py pa kouvri:
  - mesaj fiks ki pa nan _ROWS (sòti a pare pou kole nan _ROWS);
  - f-string ki pa gen okenn liy nan PATTERNS.

Kòd sòti: 0 si tout bagay tradui, 1 si gen sa ki manke (bon pou CI pita).
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.i18n import MESSAGES, PATTERNS  # noqa: E402

APP_DIR = BACKEND / "app"

# Fichye ki pa voye mesaj bay itilizatè yo (erè demaraj sèvè a).
SKIP_FILES = {"i18n.py", "config.py"}

# f-string ki parèt sèlman nan devlopman (detay yon erè 500).
DEV_ONLY = {"{type(exc).__name__}: {exc}"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _sample(node: ast.JoinedStr) -> str:
    """f"Nòt ou a se {x}%." → "Nòt ou a se 1%." pou nou teste PATTERNS."""
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        else:
            parts.append("1")
    return "".join(parts)


def _messages_in_call(node: ast.Call):
    """Retounen (tèks pou montre, tèks pou teste, se_fstring)."""
    name = _call_name(node)
    candidates = []
    if name == "HTTPException":
        candidates += [kw.value for kw in node.keywords if kw.arg == "detail"]
    elif name == "ValueError" and node.args:
        candidates.append(node.args[0])

    for value in candidates:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            yield value.value, value.value, False
        elif isinstance(value, ast.JoinedStr):
            shown = ast.unparse(value)[2:-1]      # retire f' ... '
            yield shown, _sample(value), True


def _is_translated(message: str) -> bool:
    if message in MESSAGES:
        return True
    return any(pattern.match(message) for pattern, _ in PATTERNS)


def main() -> int:
    missing: dict[str, list[str]] = {}
    dynamic: dict[str, list[str]] = {}

    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name in SKIP_FILES:
            continue
        # utf-8-sig: kèk fichye gen yon BOM (karaktè envizib) nan kòmansman yo.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        where = path.relative_to(BACKEND).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for shown, probe, is_fstring in _messages_in_call(node):
                if is_fstring and shown in DEV_ONLY:
                    continue
                if _is_translated(probe):
                    continue
                place = f"{where}:{node.lineno}"
                target = dynamic if is_fstring else missing
                target.setdefault(shown, []).append(place)

    if missing:
        print(f"# {len(missing)} mesaj poko tradui — kole yo nan _ROWS (app/i18n.py):\n")
        for message, places in missing.items():
            print(f"    # {', '.join(places)}")
            print(f"    ({message!r},")
            print('     "",')
            print('     ""),')
        print()

    if dynamic:
        print(f"# {len(dynamic)} f-string san liy nan PATTERNS:\n")
        for message, places in dynamic.items():
            print(f"    # {', '.join(places)}")
            print(f"    {message}")
        print()

    if not missing and not dynamic:
        print("Tout mesaj yo tradui.")
    return 1 if missing or dynamic else 0


if __name__ == "__main__":
    raise SystemExit(main())