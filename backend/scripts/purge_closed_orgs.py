r"""
Konbit — Efase nèt biznis ki fèmen depi plis pase 30 jou
Chemen: backend/scripts/purge_closed_orgs.py

    backend\venv\Scripts\python.exe backend\scripts\purge_closed_orgs.py           # montre sa ki ta efase
    backend\venv\Scripts\python.exe backend\scripts\purge_closed_orgs.py --apply   # efase vre

Sou Render: yon "Cron Job" chak jou ak --apply (apre premye vrè tès la).
FÈ YON BACKUP AVAN PREMYE --apply AN.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal          # noqa: E402
from app.org_data import purge_closed_organizations  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        report = purge_closed_organizations(db, apply=apply)
    if not report:
        print("Pa gen biznis pou efase.")
        return 0
    for item in report:
        total = sum(item["rows"].values())
        print(f"- #{item['organization_id']} {item['name']}: {total} ranje")
        for table, n in sorted(item["rows"].items()):
            print(f"    {table}: {n}")
    print("\nFINI: efase." if apply else "\nMÒD TÈS: anyen pa efase. Lanse ak --apply pou efase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
