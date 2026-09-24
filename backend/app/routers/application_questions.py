"""
Konbit — Kesyon fòm aplikasyon
Chemen: backend/app/routers/application_questions.py

ENTÈN (HR):
    GET    /api/application-questions             Lis (pa defo + pèsonalize)
    POST   /api/application-questions             Ajoute yon kesyon
    PATCH  /api/application-questions/{id}        Modifye, aktive, dezaktive
    DELETE /api/application-questions/{id}        Efase (sèlman si pa gen repons)

PIBLIK (paj karyè a):
    GET    /api/application-questions/public/{org_slug}/{job_slug}

KESYON PA DEFO: chak biznis resevwa yon seri kesyon pwofesyonèl
(adrès, disponiblite, edikasyon, istwa ak konpayi a...). Yo kreye
otomatikman premye fwa yo bezwen. HR ka chanje tèks yo, fè yo obligatwa
oswa dezaktive yo — men pa efase yo, pou yo pa retounen poukont yo.

KESYON SANSIB: yon repons sou yon kesyon `is_sensitive` parèt sèlman pou
HR ak admin, pa pou manadjè k ap fè antrevi yo.
"""

import logging
import math
from datetime import date
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import DbSession, TenantId, require_hr
from ..models import (
    ApplicationAnswer,
    ApplicationQuestion,
    JobPosting,
    JobStatus,
    Organization,
    QuestionType,
)
from ..schemas import Message, _require_http_url

logger = logging.getLogger("konbit")

router = APIRouter()


# ---------------------------------------------------------------------------
# SEKSYON AK KESYON PA DEFO
# ---------------------------------------------------------------------------

SECTIONS: list[tuple[str, str]] = [
    ("personal", "Enfòmasyon pèsonèl"),
    ("availability", "Disponiblite"),
    ("education", "Edikasyon ak lang"),
    ("experience", "Eksperyans"),
    ("history", "Istwa ak konpayi a"),
    ("references", "Referans"),
    ("other", "Lòt kesyon"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]
SECTION_ORDER = {k: i for i, k in enumerate(SECTION_KEYS)}

CHOICE_TYPES = {QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE}

T = QuestionType
DEFAULT_QUESTIONS: list[dict] = [
    # --- Enfòmasyon pèsonèl ---
    dict(key="address", section="personal", type=T.SHORT_TEXT,
         label="Adrès kote w rete", required=False),
    dict(key="city", section="personal", type=T.SHORT_TEXT,
         label="Vil oswa komin", required=True),
    # --- Disponiblite ---
    dict(key="available_from", section="availability", type=T.DATE,
         label="Ki lè ou ka kòmanse?", required=False),
    dict(key="work_schedule", section="availability", type=T.SINGLE_CHOICE,
         label="Ki kalite orè w ap chèche?", required=False,
         options=["Tan plen", "Tan pasyèl", "Nenpòt"]),
    dict(key="expected_salary", section="availability", type=T.NUMBER,
         label="Salè w espere pa mwa (HTG)", required=False,
         help="Opsyonèl. Sa ede n konnen si pòs la koresponn ak atant ou."),
    # --- Edikasyon ak lang ---
    dict(key="education_level", section="education", type=T.SINGLE_CHOICE,
         label="Pi wo nivo etid ou", required=False,
         options=["Lekòl primè", "Segondè (rive nan Filo)", "Lekòl pwofesyonèl",
                  "Inivèsite — lisans", "Metriz oswa plis"]),
    dict(key="languages", section="education", type=T.MULTI_CHOICE,
         label="Ki lang ou pale?", required=False,
         options=["Kreyòl", "Franse", "Angle", "Panyòl"]),
    # --- Eksperyans ---
    dict(key="years_experience", section="experience", type=T.NUMBER,
         label="Konbyen ane eksperyans travay ou genyen?", required=False),
    dict(key="last_job", section="experience", type=T.SHORT_TEXT,
         label="Dènye travay ou (pòs ak konpayi)", required=False),
    # --- Istwa ak konpayi a ---
    dict(key="worked_here_before", section="history", type=T.YES_NO,
         label="Èske w te deja travay pou nou?", required=True),
    dict(key="worked_here_when", section="history", type=T.SHORT_TEXT,
         label="Ki lè w te travay isit, e nan ki pòs?", required=False,
         condition=("worked_here_before", "true")),
    dict(key="worked_here_left_reason", section="history", type=T.LONG_TEXT,
         label="Poukisa w te kite?", required=True,
         condition=("worked_here_before", "true")),
    # --- Referans ---
    dict(key="references", section="references", type=T.LONG_TEXT,
         label="Referans: non ak telefòn 1 oswa 2 moun ki konnen travay ou",
         required=False),
    # --- Lòt ---
    dict(key="heard_about", section="other", type=T.SINGLE_CHOICE,
         label="Kijan w tande pale de pòs la?", required=False,
         options=["Facebook", "WhatsApp", "Instagram", "Yon zanmi oswa fanmi",
                  "Radyo oswa televizyon", "Sit entènèt nou", "Lòt"]),
]


def ensure_default_questions(db: Session, org_id: int) -> None:
    """
    Kreye kesyon pa defo ki manke pou yon biznis. Pa fè anyen si yo tout la.
    Nou pa JANM re-kreye yon kesyon HR te dezaktive: li toujou egziste.
    """
    rows = db.query(ApplicationQuestion).filter(
        ApplicationQuestion.organization_id == org_id,
        ApplicationQuestion.system_key.isnot(None),
    ).all()
    by_key = {q.system_key: q for q in rows}
    if all(d["key"] in by_key for d in DEFAULT_QUESTIONS):
        return

    for order, d in enumerate(DEFAULT_QUESTIONS):
        if d["key"] in by_key:
            continue
        q = ApplicationQuestion(
            organization_id=org_id,
            system_key=d["key"],
            section=d["section"],
            label=d["label"],
            help_text=d.get("help"),
            question_type=d["type"],
            options=d.get("options"),
            is_required=d["required"],
            is_sensitive=False,
            is_active=True,
            order_index=(order + 1) * 10,
        )
        cond = d.get("condition")
        if cond and cond[0] in by_key:
            q.condition_question = by_key[cond[0]]
            q.condition_value = cond[1]
        db.add(q)
        by_key[d["key"]] = q

    try:
        db.commit()
    except IntegrityError:
        # De rekèt an menm tan: lòt la deja kreye yo. Pa gen pwoblèm.
        db.rollback()


def _sort_key(q: ApplicationQuestion):
    return (SECTION_ORDER.get(q.section, len(SECTION_ORDER)), q.order_index, q.id)


def applicable_questions(db: Session, org_id: int, job_id: int) -> list[ApplicationQuestion]:
    """Kesyon aktif pou yon òf: sa ki pou tout biznis la + sa ki pou òf sa a."""
    rows = db.query(ApplicationQuestion).filter(
        ApplicationQuestion.organization_id == org_id,
        ApplicationQuestion.is_active.is_(True),
        or_(
            ApplicationQuestion.job_posting_id.is_(None),
            ApplicationQuestion.job_posting_id == job_id,
        ),
    ).all()
    return sorted(rows, key=_sort_key)


# ---------------------------------------------------------------------------
# VALIDASYON REPONS YO
# ---------------------------------------------------------------------------

def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, dict)) and not v:
        return True
    return False


def _normalize(q: ApplicationQuestion, v: Any) -> Any:
    """Konvèti yon repons nan bon fòma a, oswa voye ValueError."""
    t = q.question_type

    if t in (T.SHORT_TEXT, T.LONG_TEXT):
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            raise ValueError("repons lan dwe yon tèks.")
        text = str(v).strip()
        limit = 300 if t == T.SHORT_TEXT else 5000
        if len(text) > limit:
            raise ValueError(f"repons lan twò long ({limit} karaktè maksimòm).")
        return text

    if t == T.YES_NO:
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "wi", "yes"):
            return True
        if isinstance(v, str) and v.strip().lower() in ("false", "non", "no"):
            return False
        raise ValueError("reponn wi oswa non.")

    if t == T.SINGLE_CHOICE:
        if not isinstance(v, str) or v not in (q.options or []):
            raise ValueError("chwazi youn nan opsyon yo.")
        return v

    if t == T.MULTI_CHOICE:
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError("chwazi nan opsyon yo.")
        allowed = q.options or []
        picked = []
        for x in v:
            if x not in allowed:
                raise ValueError(f"'{x}' pa youn nan opsyon yo.")
            if x not in picked:
                picked.append(x)
        return picked

    if t == T.NUMBER:
        if isinstance(v, bool):
            raise ValueError("mete yon chif.")
        try:
            n = float(str(v).replace(" ", "").replace(",", "."))
        except ValueError:
            raise ValueError("mete yon chif.") from None
        if not math.isfinite(n) or n < 0 or n > 1_000_000_000:
            raise ValueError("chif la pa valab.")
        return int(n) if n.is_integer() else n

    if t == T.DATE:
        try:
            return date.fromisoformat(str(v).strip()).isoformat()
        except ValueError:
            raise ValueError("dat la pa valab (AAAA-MM-JJ).") from None

    if t == T.URL:
        url = _require_http_url(str(v))
        if url is None:
            raise ValueError("mete yon lyen.")
        return url

    raise ValueError("kalite kesyon an pa konnen.")


def _condition_met(parent_value: Any, expected: Optional[str]) -> bool:
    if parent_value is None or expected is None:
        return False
    if isinstance(parent_value, bool):
        return ("true" if parent_value else "false") == expected
    return str(parent_value) == expected


def validate_answers(
    questions: list[ApplicationQuestion],
    raw: Optional[dict[str, Any]],
) -> list[tuple[ApplicationQuestion, Any]]:
    """
    Verifye repons yo kont kesyon ki aktif yo. Retounen (kesyon, valè)
    pou chak repons pou sere. Kesyon kache (kondisyon an pa satisfè)
    pa sere ditou — menm si navigatè a te voye yon repons.
    """
    by_id = {q.id: q for q in questions}
    given: dict[int, Any] = {}
    for key, value in (raw or {}).items():
        try:
            qid = int(key)
        except (TypeError, ValueError):
            continue
        if qid in by_id:            # kesyon ki pa egziste oswa dezaktive: inyore
            given[qid] = value

    problems: list[str] = []
    clean: dict[int, Any] = {}
    for q in questions:
        v = given.get(q.id)
        if _is_empty(v):
            clean[q.id] = None
            continue
        try:
            clean[q.id] = _normalize(q, v)
        except ValueError as exc:
            problems.append(f"«{q.label}»: {exc}")
            clean[q.id] = None

    result = []
    missing = []
    for q in questions:
        if q.condition_question_id is not None:
            if q.condition_question_id not in by_id:
                continue            # kesyon paran an dezaktive: sa a kache tou
            if not _condition_met(clean.get(q.condition_question_id), q.condition_value):
                continue
        value = clean.get(q.id)
        if value is None:
            if q.is_required:
                missing.append(f"«{q.label}»")
            continue
        result.append((q, value))

    if missing:
        problems.insert(0, "Kesyon obligatwa ki manke: " + ", ".join(missing) + ".")
    if problems:
        raise HTTPException(
            status_code=422,
            detail=" ".join(problems),
        )
    return result


def save_answers(db: Session, org_id: int, application_id: int,
                 pairs: list[tuple[ApplicationQuestion, Any]]) -> None:
    """Ranplase repons yon aplikasyon. Pa fè commit: se moun ki rele a ki fè l."""
    db.query(ApplicationAnswer).filter(
        ApplicationAnswer.application_id == application_id,
    ).delete(synchronize_session=False)
    for q, value in pairs:
        db.add(ApplicationAnswer(
            organization_id=org_id,
            application_id=application_id,
            question_id=q.id,
            question_label=q.label,
            question_type=q.question_type,
            section=q.section,
            is_sensitive=bool(q.is_sensitive),
            value=value,
        ))
        # ---------------------------------------------------------------------------
# REPONS POU PAJ KANDIDA A (HR / MANADJÈ)
# ---------------------------------------------------------------------------

class AnswerOut(BaseModel):
    question_id: int
    section: str
    section_label: str
    label: str
    question_type: QuestionType
    value: Any = None
    is_sensitive: bool


def answers_for(db: Session, org_id: int, application_id: int,
                include_sensitive: bool) -> list[AnswerOut]:
    """
    Repons yon aplikasyon, nan lòd seksyon yo. Yon repons sansib si
    kesyon an te sansib LÈ KANDIDA A TE REPONN, oswa si l sansib kounye a.
    """
    labels = dict(SECTIONS)
    rows = (
        db.query(ApplicationAnswer, ApplicationQuestion.is_sensitive)
        .join(ApplicationQuestion, ApplicationAnswer.question_id == ApplicationQuestion.id)
        .filter(
            ApplicationAnswer.organization_id == org_id,
            ApplicationAnswer.application_id == application_id,
        )
        .order_by(ApplicationAnswer.id)
        .all()
    )
    out = []
    for ans, now_sensitive in rows:
        sensitive = bool(ans.is_sensitive or now_sensitive)
        if sensitive and not include_sensitive:
            continue
        out.append(AnswerOut(
            question_id=ans.question_id,
            section=ans.section,
            section_label=labels.get(ans.section, ans.section),
            label=ans.question_label,
            question_type=ans.question_type,
            value=ans.value,
            is_sensitive=sensitive,
        ))
    out.sort(key=lambda a: SECTION_ORDER.get(a.section, len(SECTION_ORDER)))
    return out


# ---------------------------------------------------------------------------
# SCHEMA YO
# ---------------------------------------------------------------------------

class SectionOut(BaseModel):
    key: str
    label: str


class PublicQuestionOut(BaseModel):
    id: int
    key: Optional[str] = None
    section: str
    label: str
    help_text: Optional[str] = None
    question_type: QuestionType
    options: Optional[list[str]] = None
    is_required: bool
    condition_question_id: Optional[int] = None
    condition_value: Optional[str] = None


class PublicQuestionList(BaseModel):
    sections: list[SectionOut]
    items: list[PublicQuestionOut]


class QuestionOut(PublicQuestionOut):
    job_posting_id: Optional[int] = None
    is_sensitive: bool
    is_active: bool
    is_default: bool
    order_index: int
    answer_count: int = 0


class QuestionList(BaseModel):
    sections: list[SectionOut]
    items: list[QuestionOut]


def _clean_options(question_type: Optional[QuestionType],
                   options: Optional[list[str]]) -> Optional[list[str]]:
    if question_type not in CHOICE_TYPES:
        return None
    cleaned, seen = [], set()
    for opt in options or []:
        text = (opt or "").strip()
        if not text:
            continue
        if len(text) > 100:
            raise ValueError("Chak opsyon dwe gen 100 karaktè maksimòm.")
        if text.lower() in seen:
            raise ValueError(f"Opsyon '{text}' la repete.")
        seen.add(text.lower())
        cleaned.append(text)
    if not 2 <= len(cleaned) <= 30:
        raise ValueError("Yon kesyon chwa bezwen ant 2 ak 30 opsyon.")
    return cleaned


class QuestionCreate(BaseModel):
    label: str = Field(min_length=3, max_length=300)
    help_text: Optional[str] = Field(default=None, max_length=500)
    section: str = "other"
    question_type: QuestionType
    options: Optional[list[str]] = None
    is_required: bool = False
    is_sensitive: bool = False
    job_posting_id: Optional[int] = None
    condition_question_id: Optional[int] = None
    condition_value: Optional[str] = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _check(self):
        if self.section not in SECTION_KEYS:
            raise ValueError(f"Seksyon an dwe youn nan: {', '.join(SECTION_KEYS)}.")
        self.label = self.label.strip()
        self.options = _clean_options(self.question_type, self.options)
        if (self.condition_question_id is None) != (self.condition_value is None):
            raise ValueError("Yon kondisyon bezwen kesyon an AK repons lan.")
        return self


class QuestionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=3, max_length=300)
    help_text: Optional[str] = Field(default=None, max_length=500)
    section: Optional[str] = None
    options: Optional[list[str]] = None
    is_required: Optional[bool] = None
    is_sensitive: Optional[bool] = None
    is_active: Optional[bool] = None
    order_index: Optional[int] = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def _check(self):
        if self.section is not None and self.section not in SECTION_KEYS:
            raise ValueError(f"Seksyon an dwe youn nan: {', '.join(SECTION_KEYS)}.")
        if self.label is not None:
            self.label = self.label.strip()
        return self


def _to_out(q: ApplicationQuestion, answer_count: int = 0) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        key=q.system_key,
        section=q.section,
        label=q.label,
        help_text=q.help_text,
        question_type=q.question_type,
        options=q.options,
        is_required=q.is_required,
        condition_question_id=q.condition_question_id,
        condition_value=q.condition_value,
        job_posting_id=q.job_posting_id,
        is_sensitive=q.is_sensitive,
        is_active=q.is_active,
        is_default=q.system_key is not None,
        order_index=q.order_index,
        answer_count=answer_count,
    )


def _sections() -> list[SectionOut]:
    return [SectionOut(key=k, label=v) for k, v in SECTIONS]


def _get_question_or_404(db: Session, org_id: int, question_id: int) -> ApplicationQuestion:
    q = db.query(ApplicationQuestion).filter(
        ApplicationQuestion.id == question_id,
        ApplicationQuestion.organization_id == org_id,
    ).first()
    if q is None:
        raise HTTPException(status_code=404, detail="Kesyon an pa jwenn.")
    return q


def _answer_count(db: Session, question_id: int) -> int:
    return db.query(func.count(ApplicationAnswer.id)).filter(
        ApplicationAnswer.question_id == question_id,
    ).scalar() or 0


# ---------------------------------------------------------------------------
# PIBLIK — PAJ KARYÈ A
# ---------------------------------------------------------------------------

@router.get(
    "/public/{org_slug}/{job_slug}",
    response_model=PublicQuestionList,
    tags=["Piblik"],
)
def public_questions(org_slug: str, job_slug: str, db: DbSession):
    """Kesyon fòm aplikasyon an pou yon òf. Pa gen otantifikasyon."""
    org = db.query(Organization).filter(
        Organization.slug == org_slug.lower().strip(),
        Organization.is_active.is_(True),
    ).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Biznis la pa jwenn.")

    job = db.query(JobPosting).filter(
        JobPosting.organization_id == org.id,
        JobPosting.slug == job_slug.lower().strip(),
        JobPosting.status == JobStatus.PUBLISHED,
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Òf travay la pa disponib.")

    ensure_default_questions(db, org.id)
    questions = applicable_questions(db, org.id, job.id)
    return PublicQuestionList(
        sections=_sections(),
        items=[PublicQuestionOut(
            id=q.id, key=q.system_key, section=q.section, label=q.label,
            help_text=q.help_text, question_type=q.question_type, options=q.options,
            is_required=q.is_required, condition_question_id=q.condition_question_id,
            condition_value=q.condition_value,
        ) for q in questions],
    )


# ---------------------------------------------------------------------------
# HR — JERE KESYON YO
# ---------------------------------------------------------------------------

@router.get("", response_model=QuestionList, dependencies=[Depends(require_hr)])
def list_questions(
    org_id: TenantId,
    db: DbSession,
    job_posting_id: Annotated[Optional[int], Query(description="Sèlman sa ki aplike pou òf sa a")] = None,
    include_inactive: bool = True,
):
    ensure_default_questions(db, org_id)

    q = db.query(ApplicationQuestion).filter(ApplicationQuestion.organization_id == org_id)
    if job_posting_id is not None:
        q = q.filter(or_(
            ApplicationQuestion.job_posting_id.is_(None),
            ApplicationQuestion.job_posting_id == job_posting_id,
        ))
    if not include_inactive:
        q = q.filter(ApplicationQuestion.is_active.is_(True))
    rows = sorted(q.all(), key=_sort_key)

    counts = dict(
        db.query(ApplicationAnswer.question_id, func.count(ApplicationAnswer.id))
        .filter(ApplicationAnswer.organization_id == org_id)
        .group_by(ApplicationAnswer.question_id)
        .all()
    )
    return QuestionList(sections=_sections(), items=[_to_out(r, counts.get(r.id, 0)) for r in rows])


@router.post(
    "",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_question(payload: QuestionCreate, org_id: TenantId, db: DbSession):
    if payload.job_posting_id is not None:
        job = db.query(JobPosting).filter(
            JobPosting.id == payload.job_posting_id,
            JobPosting.organization_id == org_id,
        ).first()
        if job is None:
            raise HTTPException(status_code=400, detail="Òf travay la pa jwenn.")

    if payload.condition_question_id is not None:
        parent = _get_question_or_404(db, org_id, payload.condition_question_id)
        if parent.question_type == T.YES_NO:
            if payload.condition_value not in ("true", "false"):
                raise HTTPException(status_code=400, detail="Kondisyon an dwe 'true' oswa 'false'.")
        elif parent.question_type == T.SINGLE_CHOICE:
            if payload.condition_value not in (parent.options or []):
                raise HTTPException(status_code=400, detail="Kondisyon an dwe youn nan opsyon kesyon an.")
        else:
            raise HTTPException(
                status_code=400,
                detail="Yon kondisyon ka depann sèlman de yon kesyon wi/non oswa yon sèl chwa.",
            )

    last = db.query(func.max(ApplicationQuestion.order_index)).filter(
        ApplicationQuestion.organization_id == org_id,
        ApplicationQuestion.section == payload.section,
    ).scalar() or 0

    q = ApplicationQuestion(
        organization_id=org_id,
        order_index=last + 10,
        is_active=True,
        **payload.model_dump(),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _to_out(q)


@router.patch("/{question_id}", response_model=QuestionOut, dependencies=[Depends(require_hr)])
def update_question(question_id: int, payload: QuestionUpdate, org_id: TenantId, db: DbSession):
    q = _get_question_or_404(db, org_id, question_id)
    data = payload.model_dump(exclude_unset=True)

    if "options" in data:
        if q.question_type not in CHOICE_TYPES:
            raise HTTPException(status_code=400, detail="Kesyon sa a pa gen opsyon.")
        try:
            data["options"] = _clean_options(q.question_type, data["options"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    for field, value in data.items():
        if field in ("label", "section", "is_required", "is_sensitive", "is_active", "order_index") and value is None:
            continue
        setattr(q, field, value)

    db.commit()
    db.refresh(q)
    return _to_out(q, _answer_count(db, q.id))


@router.delete("/{question_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_question(question_id: int, org_id: TenantId, db: DbSession):
    q = _get_question_or_404(db, org_id, question_id)

    if q.system_key is not None:
        raise HTTPException(
            status_code=400,
            detail="Yon kesyon pa defo pa ka efase. Dezaktive l pito.",
        )
    if _answer_count(db, q.id):
        raise HTTPException(
            status_code=400,
            detail="Kandida deja reponn kesyon sa a. Dezaktive l pito, pou repons yo pa pèdi.",
        )
    child = db.query(ApplicationQuestion).filter(
        ApplicationQuestion.condition_question_id == q.id,
    ).first()
    if child is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Kesyon «{child.label}» depann de kesyon sa a. Chanje l anvan.",
        )

    db.delete(q)
    db.commit()
    return Message(detail="Kesyon an efase.")