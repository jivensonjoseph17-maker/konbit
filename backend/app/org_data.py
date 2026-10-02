"""
Konbit — Done yon biznis: ekspòtasyon konplè ak efasman nèt
Chemen: backend/app/org_data.py

KIJAN NOU JWENN DONE YON BIZNIS (org_scope):
  1. Tout tab ki gen yon kolòn `organization_id` (+ ranje `organizations` la).
  2. Tab ki PA gen `organization_id` men ki depann de youn nan tab sa yo
     pa yon ForeignKey (egz: lessons → courses). Nou swiv yo otomatikman.
  Konsa yon NOUVO tab antre nan ekspòtasyon an ak nan efasman an pou kont li.

SA KI PA JANM SOTI (ekspòtasyon):
  - Tab sekirite: auth_attempts, email_tokens, recovery_codes.
  - Kolòn ki gen password / hash / secret / token / pin / lookup nan non yo.
  - Kolòn binè (foto, logo).
  Kolòn chifre yo (kont labank, NIF…) soti AN KLÈ: se done biznis la.

CSV: UTF-8 ak BOM, separatè ";" (Excel an franse). Yon selil ki kòmanse
pa = + - @ jwenn yon "'" devan l: yon kandida pa ka mete yon fòmil Excel
ki ta egzekite lè HR louvri fichye a.

EFASMAN (purge_organization): nou kalkile ID pou efase yo AVAN, nou mete
ForeignKey ki ka vid yo a NULL (pou kase sik tankou depatman ↔ anplwaye),
epi nou efase tab yo nan lòd envès depandans yo.
"""

import csv
import enum
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import LargeBinary, delete, func, select, update
from sqlalchemy.orm import Session

from .database import Base

SKIP_TABLES = {"auth_attempts", "email_tokens", "recovery_codes", "alembic_version"}
HIDDEN_WORDS = ("password", "hash", "secret", "token", "pin", "lookup")
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
CLOSURE_GRACE_DAYS = 30

README = """KONMBIT — Ekspòtasyon done biznis la / Export des données de l'entreprise

KREYÒL
- Yon fichye CSV pa kalite done. Louvri yo nan Excel (separatè: point-virgule).
- Tout montan lajan yo an SANTIM: 4500000 = 45 000,00 HTG.
- Dat ak lè yo an UTC (fòma ISO).
- Modpas, sekrè 2FA, kòd tablèt ak foto PA ladan l, pou sekirite.
- Nimewo kont labank ak NIF yo an klè: sere fichye sa a yon kote ki an sekirite.

FRANÇAIS
- Un fichier CSV par type de données (séparateur : point-virgule).
- Tous les montants sont en CENTIMES : 4500000 = 45 000,00 HTG.
- Les dates et heures sont en UTC (format ISO).
- Mots de passe, secrets 2FA, codes des tablettes et photos ne sont PAS inclus.
- Les numéros de compte et NIF sont en clair : conservez ce fichier en lieu sûr.
"""


def _hidden(column) -> bool:
    name = column.name.lower()
    impl = getattr(column.type, "impl", column.type)
    return any(word in name for word in HIDDEN_WORDS) or isinstance(impl, LargeBinary)


def org_scope(org_id: int) -> list[tuple]:
    """[(tab, kondisyon)] pou tout done yon biznis, nan lòd depandans (paran anvan)."""
    scoped: dict[str, tuple] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in SKIP_TABLES:
            continue
        if table.name == "organizations":
            scoped[table.name] = (table, table.c.id == org_id)
        elif "organization_id" in table.c:
            scoped[table.name] = (table, table.c.organization_id == org_id)

    # Tab san organization_id: nou swiv ForeignKey yo (sorted_tables: paran an deja la).
    for table in Base.metadata.sorted_tables:
        if table.name in scoped or table.name in SKIP_TABLES:
            continue
        for fk in table.foreign_keys:
            parent = fk.column.table
            if parent.name in scoped and parent.name != table.name:
                _, parent_where = scoped[parent.name]
                scoped[table.name] = (table, fk.parent.in_(select(fk.column).where(parent_where)))
                break

    return [scoped[t.name] for t in Base.metadata.sorted_tables if t.name in scoped]


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def build_export_zip(db: Session, org_id: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("LI-M.txt", README)
        for table, where in org_scope(org_id):
            columns = [c for c in table.columns if not _hidden(c)]
            rows = db.execute(select(*columns).where(where)).all()
            out = io.StringIO()
            writer = csv.writer(out, delimiter=";")
            writer.writerow([c.name for c in columns])
            for row in rows:
                writer.writerow([_cell(v) for v in row])
            zf.writestr(f"{table.name}.csv", "\ufeff" + out.getvalue())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# EFASMAN NÈT (backend/scripts/purge_closed_orgs.py)
# ---------------------------------------------------------------------------

def _chunks(ids: list, size: int = 500):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def purge_organization(db: Session, org_id: int, apply: bool = False) -> dict[str, int]:
    """Konbyen ranje chak tab genyen pou biznis la; si apply=True, efase yo. PA komite."""
    plan = []
    for table, where in org_scope(org_id):
        pk = list(table.primary_key.columns)
        if len(pk) == 1:
            ids = [r[0] for r in db.execute(select(pk[0]).where(where)).all()]
            plan.append((table, pk[0], ids, where))
        else:
            count = db.execute(select(func.count()).select_from(table).where(where)).scalar() or 0
            plan.append((table, None, [None] * count, where))

    counts = {table.name: len(ids) for table, _, ids, _ in plan if ids}
    if not apply:
        return counts

    # 1. Kase sik yo: ForeignKey ki ka vid → NULL (pa sa ki mennen nan organizations).
    for table, pk, ids, _ in plan:
        if pk is None or not ids:
            continue
        nullable = {fk.parent.name: None for fk in table.foreign_keys
                    if fk.parent.nullable and fk.column.table.name != "organizations"}
        if nullable:
            for chunk in _chunks(ids):
                db.execute(update(table).where(pk.in_(chunk)).values(nullable))

    # 2. Tab sekirite yo (lyen imel, kòd sekou…) ki pwente sou ranje n ap efase
    #    (egz: itilizatè biznis la): yo pa nan ekspòtasyon an, men yo dwe ale tou.
    planned = {table.name: (pk, ids) for table, pk, ids, _ in plan}
    for table in Base.metadata.sorted_tables:
        if table.name not in SKIP_TABLES:
            continue
        for fk in table.foreign_keys:
            ref_pk, ref_ids = planned.get(fk.column.table.name, (None, []))
            if ref_pk is not None and ref_ids:
                for chunk in _chunks(ref_ids):
                    db.execute(delete(table).where(fk.parent.in_(chunk)))

    # 3. Efase: pitit yo anvan paran yo.
    for table, pk, ids, where in reversed(plan):
        if not ids:
            continue
        if pk is None:
            db.execute(delete(table).where(where))
        else:
            for chunk in _chunks(ids):
                db.execute(delete(table).where(pk.in_(chunk)))
    return counts


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def purge_closed_organizations(db: Session, now: Optional[datetime] = None,
                               apply: bool = False) -> list[dict]:
    """Biznis fèmen depi plis pase CLOSURE_GRACE_DAYS jou. Si apply=True, efase yo epi komite."""
    from .models import Organization

    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(days=CLOSURE_GRACE_DAYS)
    due = [
        org for org in db.query(Organization).filter(
            Organization.is_active.is_(False),
            Organization.closure_requested_at.isnot(None),
        ).all()
        if _aware(org.closure_requested_at) <= limit
    ]
    report = []
    for org in due:
        org_id, name = org.id, org.name
        counts = purge_organization(db, org_id, apply=apply)
        report.append({"organization_id": org_id, "name": name, "rows": counts})
    if apply:
        db.commit()
    return report
