"""
Konbit — Router Fidbak ak Evalyasyon
Chemen: backend/app/routers/feedback.py

Endpoint yo:
    POST   /api/feedback                     Kite yon fidbak
    GET    /api/feedback/me/sent             Fidbak mwen voye
    GET    /api/feedback/me/received         Fidbak sou mwen
    GET    /api/feedback/inbox               Fidbak pou HR / manadjè
    GET    /api/feedback/{id}                Yon fidbak
    POST   /api/feedback/{id}/respond        Reponn (HR/manadjè)

    POST   /api/feedback/reviews             Kreye yon evalyasyon
    GET    /api/feedback/reviews/me          Evalyasyon sou mwen
    GET    /api/feedback/reviews/team        Evalyasyon ekip mwen
    GET    /api/feedback/reviews/{id}        Yon evalyasyon
    PATCH  /api/feedback/reviews/{id}        Modifye (evalyatè a)
    POST   /api/feedback/reviews/{id}/comment    Kòmantè anplwaye a
    POST   /api/feedback/reviews/{id}/finalize   Fèmen l

ANONIMA SE SERYE. Lè `is_anonymous=True`, `author_id` PA janm parèt nan
okenn repons, pou okenn wòl — SUPER_ADMIN konprann. Si yon anplwaye
dekouvri yon jou ke patwon l ka wè non l, pesonn p ap janm sèvi ak zouti a
ankò. Se sa ki fè yon kanal fidbak itil oswa initil.
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    is_in_management_chain,
    require_hr,
)
from ..models import (
    Employee,
    Feedback,
    FeedbackType,
    Notification,
    PerformanceReview,
    RequestStatus,
    UserRole,
)
from ..schemas import (
    EmployeeBrief,
    FeedbackCreate,
    FeedbackOut,
    FeedbackRespond,
    Message,
    PerformanceReviewCreate,
    PerformanceReviewOut,
)

logger = logging.getLogger("konbit")

router = APIRouter()


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _notify(db: Session, org_id: int, user_id: Optional[int],
            title: str, body: str, link: Optional[str] = None) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id, user_id=user_id,
            title=title, body=body, link_url=link, category="feedback",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _to_out(db: Session, fb: Feedback) -> FeedbackOut:
    """
    Konstwi repons lan. SI FIDBAK LA ANONIM, `author` rete None —
    pa gen okenn eksepsyon, pou okenn wòl.
    """
    author = None
    if not fb.is_anonymous and fb.author_id:
        emp = db.query(Employee).filter(Employee.id == fb.author_id).first()
        if emp:
            author = EmployeeBrief.model_validate(emp)

    return FeedbackOut(
        id=fb.id,
        feedback_type=fb.feedback_type,
        title=fb.title,
        body=fb.body,
        is_anonymous=fb.is_anonymous,
        is_private=fb.is_private,
        subject_employee_id=fb.subject_employee_id,
        author=author,
        acknowledged_at=fb.acknowledged_at,
        response=fb.response,
        created_at=fb.created_at,
    )


def _get_feedback_or_404(db: Session, org_id: int, feedback_id: int) -> Feedback:
    fb = db.query(Feedback).filter(
        Feedback.id == feedback_id,
        Feedback.organization_id == org_id,
    ).first()
    if fb is None:
        raise HTTPException(status_code=404, detail="Fidbak la pa jwenn.")
    return fb


def _get_review_or_404(db: Session, org_id: int, review_id: int) -> PerformanceReview:
    rev = db.query(PerformanceReview).filter(
        PerformanceReview.id == review_id,
        PerformanceReview.organization_id == org_id,
    ).first()
    if rev is None:
        raise HTTPException(status_code=404, detail="Evalyasyon an pa jwenn.")
    return rev


def _can_read_feedback(db: Session, user: CurrentUser, emp: Optional[Employee],
                       fb: Feedback) -> bool:
    if user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR):
        return True
    if emp is None:
        return False
    if fb.author_id == emp.id:                      # pwòp fidbak mwen
        return True
    if fb.subject_employee_id == emp.id and not fb.is_private:
        return True
    if user.role == UserRole.MANAGER and fb.subject_employee_id:
        target = db.query(Employee).filter(
            Employee.id == fb.subject_employee_id
        ).first()
        if target and is_in_management_chain(emp, target):
            return True
    return False


# ---------------------------------------------------------------------------
# FIDBAK
# ---------------------------------------------------------------------------

@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    """
    Kite yon fidbak. Si `subject_employee_id` vid, se sou biznis la an jeneral.

    Nou anrejistre `author_id` menm lè fidbak la anonim — sa nesesè pou
    anplwaye a ka wè pwòp fidbak li, epi pou anpeche spam. Men `_to_out()`
    pa janm ekspoze l lè `is_anonymous=True`.
    """
    if payload.subject_employee_id is not None:
        target = db.query(Employee).filter(
            Employee.id == payload.subject_employee_id,
            Employee.organization_id == org_id,
        ).first()
        if target is None:
            raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
        if target.id == emp.id:
            raise HTTPException(
                status_code=400,
                detail="Ou pa ka kite fidbak sou tèt ou.",
            )

    fb = Feedback(
        organization_id=org_id,
        author_id=emp.id,
        **payload.model_dump(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    # Avèti manadjè moun nan, oswa HR si se sou biznis la
    if fb.subject_employee_id:
        target = db.query(Employee).filter(Employee.id == fb.subject_employee_id).first()
        if target and target.manager_id:
            manager = db.query(Employee).filter(Employee.id == target.manager_id).first()
            if manager and manager.user_id:
                _notify(
                    db, org_id, manager.user_id,
                    title="Nouvo fidbak",
                    body=f"Gen yon nouvo fidbak sou {target.first_name} {target.last_name}.",
                    link=f"/feedback/{fb.id}",
                )

    return _to_out(db, fb)


class FeedbackList(BaseModel):
    total: int
    items: list[FeedbackOut]


@router.get("/me/sent", response_model=FeedbackList)
def my_sent_feedback(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """Fidbak mwen voye, anonim yo konprann."""
    rows = db.query(Feedback).filter(
        Feedback.organization_id == org_id,
        Feedback.author_id == emp.id,
    ).order_by(Feedback.created_at.desc()).all()

    return FeedbackList(total=len(rows), items=[_to_out(db, f) for f in rows])


@router.get("/me/received", response_model=FeedbackList)
def my_received_feedback(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """
    Fidbak sou mwen. Sèlman sa ki PA prive — yon fidbak prive se pou
    HR ak manadjè a, pa pou moun nan dirèkteman.
    """
    rows = db.query(Feedback).filter(
        Feedback.organization_id == org_id,
        Feedback.subject_employee_id == emp.id,
        Feedback.is_private.is_(False),
    ).order_by(Feedback.created_at.desc()).all()

    return FeedbackList(total=len(rows), items=[_to_out(db, f) for f in rows])


@router.get("/inbox", response_model=FeedbackList)
def feedback_inbox(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    feedback_type: Annotated[Optional[FeedbackType], Query(alias="type")] = None,
    unanswered_only: bool = False,
):
    """
    Fidbak pou HR ak manadjè. HR wè tout; yon manadjè wè sa ki sou ekip li
    plis sa ki sou biznis la an jeneral.
    """
    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    if not is_hr and user.role != UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou bwat sa a.")

    q = db.query(Feedback).filter(Feedback.organization_id == org_id)

    if not is_hr:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")

        reports = [
            r[0] for r in db.query(Employee.id).filter(
                Employee.organization_id == org_id,
                Employee.manager_id == viewer.id,
            ).all()
        ]
        q = q.filter(or_(
            Feedback.subject_employee_id.in_(reports),
            Feedback.subject_employee_id.is_(None),
        ))

    if feedback_type:
        q = q.filter(Feedback.feedback_type == feedback_type)
    if unanswered_only:
        q = q.filter(Feedback.acknowledged_at.is_(None))

    rows = q.order_by(Feedback.created_at.desc()).all()
    return FeedbackList(total=len(rows), items=[_to_out(db, f) for f in rows])


@router.get("/{feedback_id}", response_model=FeedbackOut)
def read_feedback(feedback_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    fb = _get_feedback_or_404(db, org_id, feedback_id)
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()

    if not _can_read_feedback(db, user, emp, fb):
        raise HTTPException(status_code=403, detail="Ou pa gen dwa wè fidbak sa a.")
    return _to_out(db, fb)


@router.post("/{feedback_id}/respond", response_model=FeedbackOut)
def respond_feedback(
    feedback_id: int,
    payload: FeedbackRespond,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """
    Reponn yon fidbak. Si li anonim, moun ki te voye l ap wè repons lan
    nan /me/sent — san nou pa revele kilès li ye.
    """
    if user.role not in (
        UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR, UserRole.MANAGER
    ):
        raise HTTPException(status_code=403, detail="Ou pa gen dwa reponn fidbak.")

    fb = _get_feedback_or_404(db, org_id, feedback_id)
    fb.response = payload.response
    fb.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fb)

    if fb.author_id:
        author = db.query(Employee).filter(Employee.id == fb.author_id).first()
        if author and author.user_id:
            _notify(
                db, org_id, author.user_id,
                title="Repons sou fidbak ou",
                body="Gen yon repons sou fidbak ou te kite a.",
                link=f"/feedback/{fb.id}",
            )

    return _to_out(db, fb)


# ---------------------------------------------------------------------------
# EVALYASYON PÈFÒMANS
# ---------------------------------------------------------------------------

@router.post(
    "/reviews",
    response_model=PerformanceReviewOut,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    payload: PerformanceReviewCreate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """
    Kreye yon evalyasyon. HR ka evalye tout moun; yon manadjè sèlman
    moun ki anba l. Pesonn pa ka evalye tèt li.
    """
    target = db.query(Employee).filter(
        Employee.id == payload.employee_id,
        Employee.organization_id == org_id,
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")

    reviewer = db.query(Employee).filter(Employee.user_id == user.id).first()
    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)

    if not is_hr:
        if user.role != UserRole.MANAGER or reviewer is None:
            raise HTTPException(status_code=403, detail="Ou pa gen dwa evalye moun.")
        if not is_in_management_chain(reviewer, target):
            raise HTTPException(
                status_code=403,
                detail="Ou ka evalye sèlman moun ki anba w.",
            )

    if reviewer and reviewer.id == target.id:
        raise HTTPException(status_code=400, detail="Ou pa ka evalye tèt ou.")

    review = PerformanceReview(
        organization_id=org_id,
        reviewer_id=reviewer.id if reviewer else None,
        status=RequestStatus.PENDING,
        **payload.model_dump(),
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    _notify(
        db, org_id, target.user_id,
        title="Nouvo evalyasyon",
        body=f"Gen yon evalyasyon pou peryòd '{review.period_label}'.",
        link=f"/reviews/{review.id}",
    )
    return review


class ReviewList(BaseModel):
    total: int
    items: list[PerformanceReviewOut]


@router.get("/reviews/me", response_model=ReviewList)
def my_reviews(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """
    Evalyasyon sou mwen. Sèlman sa ki FINALIZE — yon bouyon ka gen
    nòt ki poko dakò ant manadjè a ak HR.
    """
    rows = db.query(PerformanceReview).filter(
        PerformanceReview.organization_id == org_id,
        PerformanceReview.employee_id == emp.id,
        PerformanceReview.finalized_at.isnot(None),
    ).order_by(PerformanceReview.period_start.desc()).all()

    return ReviewList(total=len(rows), items=[
        PerformanceReviewOut.model_validate(r) for r in rows
    ])


@router.get("/reviews/team", response_model=ReviewList)
def team_reviews(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    employee_id: Optional[int] = None,
    pending_only: bool = False,
):
    """Evalyasyon ekip mwen (bouyon yo konprann, paske se mwen ki ekri yo)."""
    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    if not is_hr and user.role != UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou lis sa a.")

    q = db.query(PerformanceReview).filter(
        PerformanceReview.organization_id == org_id
    )

    if not is_hr:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        reports = [
            r[0] for r in db.query(Employee.id).filter(
                Employee.organization_id == org_id,
                Employee.manager_id == viewer.id,
            ).all()
        ]
        q = q.filter(PerformanceReview.employee_id.in_(reports))

    if employee_id is not None:
        q = q.filter(PerformanceReview.employee_id == employee_id)
    if pending_only:
        q = q.filter(PerformanceReview.finalized_at.is_(None))

    rows = q.order_by(PerformanceReview.period_start.desc()).all()
    return ReviewList(total=len(rows), items=[
        PerformanceReviewOut.model_validate(r) for r in rows
    ])


@router.get("/reviews/{review_id}", response_model=PerformanceReviewOut)
def read_review(review_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    review = _get_review_or_404(db, org_id, review_id)

    target = db.query(Employee).filter(Employee.id == review.employee_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")

    ensure_can_view_employee(user, target, db)

    # Anplwaye a pa wè pwòp bouyon l
    if review.finalized_at is None and target.user_id == user.id:
        raise HTTPException(
            status_code=403,
            detail="Evalyasyon sa a poko finalize.",
        )
    return review


class ReviewUpdate(BaseModel):
    period_label: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    overall_score: Optional[int] = Field(default=None, ge=1, le=5)
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals: Optional[str] = None


@router.patch("/reviews/{review_id}", response_model=PerformanceReviewOut)
def update_review(
    review_id: int,
    payload: ReviewUpdate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """Sèlman evalyatè a oswa HR, epi sèlman anvan finalizasyon."""
    review = _get_review_or_404(db, org_id, review_id)

    if review.finalized_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Evalyasyon an finalize. Ou pa ka modifye l ankò.",
        )

    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    reviewer = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not is_hr and (reviewer is None or review.reviewer_id != reviewer.id):
        raise HTTPException(status_code=403, detail="Se pa ou ki ekri evalyasyon sa a.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(review, field, value)

    db.commit()
    db.refresh(review)
    return review


class ReviewComment(BaseModel):
    comment: str = Field(min_length=1)


@router.post("/reviews/{review_id}/comment", response_model=PerformanceReviewOut)
def add_employee_comment(
    review_id: int,
    payload: ReviewComment,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    """
    Anplwaye a bay pwòp pwen de vi l. Li ka fè sa apre finalizasyon —
    yon evalyasyon san dwa repons se yon jijman, pa yon konvèsasyon.
    """
    review = _get_review_or_404(db, org_id, review_id)

    if review.employee_id != emp.id:
        raise HTTPException(status_code=403, detail="Se pa evalyasyon w.")
    if review.finalized_at is None:
        raise HTTPException(
            status_code=400,
            detail="Evalyasyon an poko finalize.",
        )

    review.employee_comment = payload.comment
    db.commit()
    db.refresh(review)

    if review.reviewer_id:
        reviewer = db.query(Employee).filter(Employee.id == review.reviewer_id).first()
        if reviewer and reviewer.user_id:
            _notify(
                db, org_id, reviewer.user_id,
                title="Kòmantè sou evalyasyon",
                body=f"{emp.first_name} {emp.last_name} reponn sou evalyasyon an.",
                link=f"/reviews/{review.id}",
            )

    return review


@router.post("/reviews/{review_id}/finalize", response_model=PerformanceReviewOut)
def finalize_review(
    review_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """Fèmen evalyasyon an. Apre sa anplwaye a ka wè l epi reponn."""
    review = _get_review_or_404(db, org_id, review_id)

    if review.finalized_at is not None:
        raise HTTPException(status_code=400, detail="Li deja finalize.")

    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    reviewer = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not is_hr and (reviewer is None or review.reviewer_id != reviewer.id):
        raise HTTPException(status_code=403, detail="Se pa ou ki ekri evalyasyon sa a.")

    if review.overall_score is None:
        raise HTTPException(
            status_code=400,
            detail="Mete yon nòt jeneral (1-5) anvan ou finalize.",
        )

    review.finalized_at = datetime.now(timezone.utc)
    review.status = RequestStatus.APPROVED
    db.commit()
    db.refresh(review)

    target = db.query(Employee).filter(Employee.id == review.employee_id).first()
    if target and target.user_id:
        _notify(
            db, org_id, target.user_id,
            title="Evalyasyon w disponib",
            body=f"Evalyasyon pou '{review.period_label}' pare. Ou ka reponn sou li.",
            link=f"/reviews/{review.id}",
        )

    return review