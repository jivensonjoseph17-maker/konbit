"""
Konbit — Ranplase mo "peyòl" pa "pewòl" nan tout pwojè a
Chemen: rename_pewol.py (rasin repo a — konbit\\)

Kle tradiksyon yo SE tèks kreyòl la. Kidonk mo a dwe chanje an MENM TAN
nan kòd la (HTML, JS, Python) ak nan fichye lang yo (JSON). Script sa a
fè tou de ansanm, pou pa gen yon kle ki rete san tradiksyon.

    python rename_pewol.py            → montre sa ki ta chanje (pa touche anyen)
    python rename_pewol.py --apply    → fè chanjman yo

Li jere "ò" nan de fòm Unicode yo (yon sèl karaktè, oswa o + aksan).
Li kenbe fen liy yo (Windows CRLF) ak BOM fichye yo jan yo te ye.
Li pa touche: venv, .git, __pycache__, node_modules, alembic/versions.
Apre --apply: pytest, check_i18n.py, i18n_missing.py, epi efase fichye sa a.
"""

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PAIRS = [("Peyòl", "Pewòl"), ("peyòl", "pewòl"), ("PEYÒL", "PEWÒL")]
# Menm mo yo ak "ò" dekonpoze (o + U+0300)
PAIRS += [(unicodedata.normalize("NFD", a), unicodedata.normalize("NFD", b)) for a, b in PAIRS]

EXTENSIONS = {".html", ".js", ".json", ".py", ".md", ".css", ".yml", ".yaml", ".txt"}
SKIP_DIRS = {"venv", ".venv", ".git", "__pycache__", "node_modules", ".pytest_cache"}
SKIP_PATHS = {Path("backend/alembic/versions")}
SELF = Path(__file__).resolve()


def wanted(path: Path) -> bool:
    if path.resolve() == SELF or path.suffix not in EXTENSIONS:
        return False
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    return not any(rel.is_relative_to(p) for p in SKIP_PATHS)


def no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ValueError(f"kle an doub apre chanjman an: {sorted(dup)}")
    return dict(pairs)


def main() -> int:
    apply = "--apply" in sys.argv
    changed = 0
    total = 0

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not wanted(path):
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue

        count = sum(text.count(old) for old, _ in PAIRS)
        if not count:
            continue

        new = text
        for old, repl in PAIRS:
            new = new.replace(old, repl)

        # Yon fichye lang pa dwe fini ak de kle idantik (egz: "Peyòl" ak "Pewòl").
        if path.suffix == ".json":
            try:
                json.loads(new.lstrip("\ufeff"), object_pairs_hook=no_duplicate_keys)
            except ValueError as err:
                print(f"  ! {path.relative_to(ROOT)}: {err}")
                return 1

        changed += 1
        total += count
        print(f"  {count:>4} × {path.relative_to(ROOT)}")
        if apply:
            path.write_bytes(new.encode("utf-8"))

    verb = "chanje" if apply else "ta chanje (kouri ak --apply pou fè l)"
    print(f"\n{total} fwa nan {changed} fichye {verb}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
