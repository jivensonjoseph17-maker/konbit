"""
Chak lyen notifikasyon backend la voye dwe mennen yon kote nan frontend lan.

Nou li kòd sous router yo (pa baz done a):
  - yon paj "xxx.html" dwe egziste nan frontend/;
  - yon lyen dinamik f"/xxx/{id}" dwe gen yon règ nan safeNotifLink (shell.js).
San sa, notifikasyon an parèt nan klòch la men li pa mennen okenn kote.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"
FRONTEND = ROOT / "frontend"

HTML_RE = re.compile(r"""["']/?([a-z0-9-]+\.html)(?:#[a-z0-9-]+)?["']""")
DYNAMIC_RE = re.compile(r"""f["']/([a-z-]+)/\{""")


def _router_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8-sig") for p in sorted(ROUTERS.glob("*.py"))}


def _safe_notif_link() -> str:
    shell = (FRONTEND / "shell.js").read_text(encoding="utf-8-sig")
    start = shell.index("function safeNotifLink")
    return shell[start:shell.index("\n  }\n", start)]


def test_every_html_link_points_to_an_existing_page():
    missing = sorted({
        f"{name}: {page}"
        for name, src in _router_sources().items()
        for page in HTML_RE.findall(src)
        if not (FRONTEND / page).exists()
    })
    assert not missing, f"Paj ki pa egziste: {missing}"


def test_every_dynamic_link_is_handled_by_the_bell():
    rules = _safe_notif_link()
    unknown = sorted({
        f"{name}: /{prefix}/N"
        for name, src in _router_sources().items()
        for line in src.splitlines() if "link" in line
        for prefix in DYNAMIC_RE.findall(line)
        if f"{prefix}\\/" not in rules
    })
    assert not unknown, f"Lyen safeNotifLink (shell.js) pa konnen: {unknown}"