"""
Gad: pa gen "jodi a" SÈVÈ a nan backend/app/.

Sèvè a (Render, Virginia) an UTC. A 8è diswa an Ayiti, li deja demen:
yon date.today() ta mete yon pwentaj, yon konje oswa yon to bonis sou
move jou a. "Jodi a" dwe soti nan timezone_utils.get_local_today(db, org_id).

Tès la li TOKEN kòd yo, pa tèks la: kòmantè ak docstring ki PALE de
date.today() (egz: portal.py, timezone_utils.py) pa konte.
"""
import io
import tokenize
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# (fichye, sa ki jwenn) ki gen dwa, ak rezon an.
ALLOWED = {
    # schemas.must_be_adult: laj anplwaye a. Yon jou diferans pa chanje yon
    # laj 16 an, e yon validatè Pydantic pa gen aksè ak baz done a.
    ("schemas.py", "date.today()"),
}

# Sekans token → non pou mesaj la. datetime.now(timezone.utc) PASE:
# se sèlman datetime.now() SAN agiman ki entèdi.
FORBIDDEN = {
    ("date", ".", "today", "(", ")"): "date.today()",
    ("datetime", ".", "today", "(", ")"): "datetime.today()",
    ("datetime", ".", "utcnow", "("): "datetime.utcnow()",
    ("datetime", ".", "now", "(", ")"): "datetime.now()",
}


def find_server_today(path: Path) -> list[tuple[str, int]]:
    """[(sa ki jwenn, nimewo liy)] nan KÒD fichye a (pa kòmantè, pa tèks)."""
    source = path.read_text(encoding="utf-8-sig")
    tokens = [
        (tok.string, tok.start[0])
        for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type in (tokenize.NAME, tokenize.OP)
    ]
    words = [w for w, _ in tokens]
    found = []
    for i in range(len(words)):
        for pattern, label in FORBIDDEN.items():
            if tuple(words[i:i + len(pattern)]) == pattern:
                found.append((label, tokens[i][1]))
    return found


def test_no_server_today_in_app():
    problems = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for label, line in find_server_today(path):
            if (path.name, label) in ALLOWED:
                continue
            problems.append(
                f"{path.relative_to(APP_DIR.parent)}:{line}: {label} — "
                "sèvi ak timezone_utils.get_local_today(db, org_id) "
                "oswa datetime.now(timezone.utc)"
            )
    assert not problems, "\n".join(problems)


def test_detector_ignores_comments_and_strings(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "# date.today() nan yon kòmantè\n"
        '"""date.today() nan yon docstring"""\n'
        "from datetime import date, datetime, timezone\n"
        "a = date.today()\n"
        "b = datetime.now(timezone.utc)\n"
        "c = datetime.now()\n",
        encoding="utf-8",
    )
    assert find_server_today(sample) == [("date.today()", 4), ("datetime.now()", 6)]