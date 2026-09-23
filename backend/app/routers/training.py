"""
Konbit — Router Fòmasyon
Chemen: backend/app/routers/training.py

Endpoint yo:
    POST   /api/training/courses                   Kreye yon kou (HR)
    GET    /api/training/courses                   Katalòg kou yo
    GET    /api/training/courses/{id}              Detay ak leson yo
    PATCH  /api/training/courses/{id}              Modifye (HR)
    POST   /api/training/courses/{id}/publish      Pibliye / retire (HR)
    DELETE /api/training/courses/{id}              Efase (si pa gen enskripsyon)

    POST   /api/training/courses/{id}/lessons      Ajoute yon videyo (HR)
    PATCH  /api/training/lessons/{id}              Modifye yon leson (HR)
    DELETE /api/training/lessons/{id}              Retire yon leson (HR)
    POST   /api/training/courses/{id}/reorder      Chanje lòd leson yo (HR)

    POST   /api/training/enrollments               Asiyen kou bay anplwaye (HR)
    GET    /api/training/me/courses                Kou mwen yo
    GET    /api/training/me/courses/{id}           Kou a ak pwogrè mwen
    POST   /api/training/me/progress               Anrejistre pwogrè videyo
    POST   /api/training/me/courses/{id}/complete  Fini yon kou

    GET    /api/training/courses/{id}/report       Kiyès ki fini (HR/manadjè)
    GET    /api/training/overdue                   Fòmasyon an reta (HR)

DESIZYON: pwogrè a anrejistre pa leson, ak pozisyon an segonn. Konsa
anplwaye a ka kanpe yon videyo epi kontinye kote l te ye a demen.
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    require_hr,
)
from ..models import (
    Course,
    Employee,
    Enrollment,
    Lesson,
    LessonProgress,
    Notification,
    UserRole,
)
from ..schemas import (
    CourseCreate,
    CourseDetail,
    CourseOut,
    EnrollmentCreate,
    EnrollmentOut,
    LessonCreate,
    LessonOut,
    Message,
    ProgressUpdate,
)

from ..timezone_utils import get_local_today

logger = logging.getLogger("konbit")

router = APIRouter()

# Yon leson konte kòm "fini" lè moun nan gade omwen sa a nan li.
WATCH_THRESHOLD = 0.90


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
            title=title, body=body, link_url=link, category="training",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _visible_courses_query(db: Session, org_id: int):
    """
    Kou biznis la fè, plis kou Konbit bay tout moun (organization_id NULL).
    """
    return db.query(Course).filter(
        (Course.organization_id == org_id) | (Course.organization_id.is_(None))
    )


def _get_course_or_404(db: Session, org_id: int, course_id: int,
                       editable: bool = False) -> Course:
    course = _visible_courses_query(db, org_id).filter(Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Kou a pa jwenn.")
    if editable and course.organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Sa se yon kou Konbit bay. Ou pa ka modifye l.",
        )
    return course


def _get_lesson_or_404(db: Session, org_id: int, lesson_id: int) -> Lesson:
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Leson an pa jwenn.")
    _get_course_or_404(db, org_id, lesson.course_id)
    return lesson


def _course_out(db: Session, course: Course) -> CourseOut:
    count, duration = db.query(
        func.count(Lesson.id), func.coalesce(func.sum(Lesson.duration_seconds), 0)
    ).filter(Lesson.course_id == course.id).first()

    out = CourseOut.model_validate(course)
    out.lesson_count = count or 0
    out.total_duration_seconds = int(duration or 0)
    return out


def _recompute_progress(db: Session, enrollment: Enrollment) -> None:
    """
    Rekalkile pousantaj la sou leson OBLIGATWA yo sèlman.
    Yon leson opsyonèl pa dwe anpeche yon kou konte kòm fini.
    """
    required_ids = [
        r[0] for r in db.query(Lesson.id).filter(
            Lesson.course_id == enrollment.course_id,
            Lesson.is_required.is_(True),
        ).all()
    ]

    if not required_ids:
        enrollment.progress_percent = 100 if enrollment.completed_at else 0
        return

    done = db.query(func.count(LessonProgress.id)).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.lesson_id.in_(required_ids),
        LessonProgress.completed.is_(True),
    ).scalar() or 0

    enrollment.progress_percent = int(done * 100 / len(required_ids))

    if enrollment.progress_percent >= 100 and enrollment.completed_at is None:
        enrollment.completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# KOU
# ---------------------------------------------------------------------------

@router.post(
    "/courses",
    response_model=CourseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_course(
    payload: CourseCreate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    course = Course(
        organization_id=org_id,
        created_by_id=user.id,
        is_published=False,
        **payload.model_dump(),
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return _course_out(db, course)


class CourseListResponse(BaseModel):
    total: int
    items: list[CourseOut]


@router.get("/courses", response_model=CourseListResponse)
def list_courses(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    category: Optional[str] = None,
    language: Optional[str] = None,
    mandatory_only: bool = False,
    include_unpublished: bool = False,
):
    """
    Katalòg la. Anplwaye regilye wè sèlman kou ki pibliye.
    HR ka mande `include_unpublished=true` pou wè bouyon l yo.
    """
    q = _visible_courses_query(db, org_id)

    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    if not (include_unpublished and is_hr):
        q = q.filter(Course.is_published.is_(True))

    if category:
        q = q.filter(Course.category == category)
    if language:
        q = q.filter(Course.language == language)
    if mandatory_only:
        q = q.filter(Course.is_mandatory.is_(True))

    items = q.order_by(Course.is_mandatory.desc(), Course.title).all()
    return CourseListResponse(
        total=len(items), items=[_course_out(db, c) for c in items]
    )


@router.get("/courses/{course_id}", response_model=CourseDetail)
def read_course(course_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    course = _get_course_or_404(db, org_id, course_id)

    is_hr = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
    if not course.is_published and not is_hr:
        raise HTTPException(status_code=403, detail="Kou a poko pibliye.")

    lessons = db.query(Lesson).filter(
        Lesson.course_id == course.id
    ).order_by(Lesson.order_index).all()

    base = _course_out(db, course)
    return CourseDetail(
        **base.model_dump(),
        lessons=[LessonOut.model_validate(l) for l in lessons],
    )


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: Optional[str] = None
    is_mandatory: Optional[bool] = None
    target_department_id: Optional[int] = None
    passing_score: Optional[int] = Field(default=None, ge=0, le=100)


@router.patch("/courses/{course_id}", response_model=CourseOut, dependencies=[Depends(require_hr)])
def update_course(course_id: int, payload: CourseUpdate, org_id: TenantId, db: DbSession):
    course = _get_course_or_404(db, org_id, course_id, editable=True)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return _course_out(db, course)


class PublishRequest(BaseModel):
    publish: bool = True


@router.post(
    "/courses/{course_id}/publish",
    response_model=CourseOut,
    dependencies=[Depends(require_hr)],
)
def publish_course(
    course_id: int,
    payload: PublishRequest,
    org_id: TenantId,
    db: DbSession,
):
    """Yon kou san leson pa ka pibliye — anplwaye a t ap louvri yon paj vid."""
    course = _get_course_or_404(db, org_id, course_id, editable=True)

    if payload.publish:
        count = db.query(func.count(Lesson.id)).filter(
            Lesson.course_id == course.id
        ).scalar() or 0
        if count == 0:
            raise HTTPException(
                status_code=400,
                detail="Kou a pa gen okenn leson. Ajoute omwen youn anvan.",
            )

    course.is_published = payload.publish
    db.commit()
    db.refresh(course)
    return _course_out(db, course)


@router.delete("/courses/{course_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_course(course_id: int, org_id: TenantId, db: DbSession):
    """
    Nou refize efase yon kou ki gen enskripsyon — pwogrè anplwaye yo se yon
    dosye fòmasyon. Retire l nan piblikasyon pito.
    """
    course = _get_course_or_404(db, org_id, course_id, editable=True)

    enrolled = db.query(func.count(Enrollment.id)).filter(
        Enrollment.course_id == course.id
    ).scalar() or 0
    if enrolled:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{enrolled} anplwaye enskri nan kou sa a. "
                "Retire l nan piblikasyon olye ou efase l."
            ),
        )

    db.query(Lesson).filter(Lesson.course_id == course.id).delete()
    db.delete(course)
    db.commit()
    return Message(detail="Kou a efase.")


# ---------------------------------------------------------------------------
# LESON (VIDEYO)
# ---------------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/lessons",
    response_model=LessonOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def add_lesson(course_id: int, payload: LessonCreate, org_id: TenantId, db: DbSession):
    course = _get_course_or_404(db, org_id, course_id, editable=True)

    data = payload.model_dump()
    if not data.get("order_index"):
        last = db.query(func.max(Lesson.order_index)).filter(
            Lesson.course_id == course.id
        ).scalar()
        data["order_index"] = (last or 0) + 1

    lesson = Lesson(course_id=course.id, **data)
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


class LessonUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    video_url: Optional[str] = None
    attachment_url: Optional[str] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    order_index: Optional[int] = None
    is_required: Optional[bool] = None


@router.patch("/lessons/{lesson_id}", response_model=LessonOut, dependencies=[Depends(require_hr)])
def update_lesson(lesson_id: int, payload: LessonUpdate, org_id: TenantId, db: DbSession):
    lesson = _get_lesson_or_404(db, org_id, lesson_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lesson, field, value)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.delete("/lessons/{lesson_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_lesson(lesson_id: int, org_id: TenantId, db: DbSession):
    lesson = _get_lesson_or_404(db, org_id, lesson_id)
    course_id = lesson.course_id

    db.query(LessonProgress).filter(LessonProgress.lesson_id == lesson.id).delete()
    db.delete(lesson)
    db.flush()

    # Pousantaj yo chanje paske denominatè a chanje
    for enr in db.query(Enrollment).filter(Enrollment.course_id == course_id).all():
        _recompute_progress(db, enr)
    db.commit()

    return Message(detail="Leson an retire.")


class ReorderRequest(BaseModel):
    lesson_ids: list[int] = Field(min_length=1, description="Nan nouvo lòd la")


@router.post(
    "/courses/{course_id}/reorder",
    response_model=list[LessonOut],
    dependencies=[Depends(require_hr)],
)
def reorder_lessons(
    course_id: int,
    payload: ReorderRequest,
    org_id: TenantId,
    db: DbSession,
):
    course = _get_course_or_404(db, org_id, course_id, editable=True)

    lessons = db.query(Lesson).filter(Lesson.course_id == course.id).all()
    by_id = {l.id: l for l in lessons}

    if set(payload.lesson_ids) != set(by_id):
        raise HTTPException(
            status_code=400,
            detail="Lis la dwe gen egzakteman tout leson kou a, yon sèl fwa chak.",
        )

    for index, lesson_id in enumerate(payload.lesson_ids, start=1):
        by_id[lesson_id].order_index = index

    db.commit()
    return db.query(Lesson).filter(
        Lesson.course_id == course.id
    ).order_by(Lesson.order_index).all()


# ---------------------------------------------------------------------------
# ENSKRIPSYON
# ---------------------------------------------------------------------------

class EnrollResult(BaseModel):
    course_id: int
    enrolled: int
    already_enrolled: int
    not_found: list[int] = []


@router.post(
    "/enrollments",
    response_model=EnrollResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def enroll_employees(
    payload: EnrollmentCreate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """Asiyen yon kou bay yon oswa plizyè anplwaye."""
    course = _get_course_or_404(db, org_id, payload.course_id)

    if not course.is_published:
        raise HTTPException(
            status_code=400,
            detail="Pibliye kou a anvan ou asiyen l.",
        )

    enrolled = already = 0
    not_found: list[int] = []

    for emp_id in payload.employee_ids:
        emp = db.query(Employee).filter(
            Employee.id == emp_id,
            Employee.organization_id == org_id,
            Employee.is_active.is_(True),
        ).first()
        if emp is None:
            not_found.append(emp_id)
            continue

        exists = db.query(Enrollment).filter(
            Enrollment.course_id == course.id,
            Enrollment.employee_id == emp.id,
        ).first()
        if exists:
            already += 1
            continue

        db.add(Enrollment(
            organization_id=org_id,
            course_id=course.id,
            employee_id=emp.id,
            assigned_by_id=user.id,
            due_date=payload.due_date,
            progress_percent=0,
        ))
        enrolled += 1

        _notify(
            db, org_id, emp.user_id,
            title="Nouvo fòmasyon",
            body=(
                f"Ou gen yon nouvo kou: {course.title}."
                + (f" Delè: {payload.due_date}." if payload.due_date else "")
            ),
            link=f"/training/{course.id}",
        )

    db.commit()
    return EnrollResult(
        course_id=course.id,
        enrolled=enrolled,
        already_enrolled=already,
        not_found=not_found,
    )


# ---------------------------------------------------------------------------
# KOU MWEN YO
# ---------------------------------------------------------------------------

class MyCourseItem(BaseModel):
    enrollment_id: int
    course: CourseOut
    due_date: Optional[date] = None
    progress_percent: int
    completed_at: Optional[datetime] = None
    is_overdue: bool


class MyCoursesResponse(BaseModel):
    total: int
    pending: int
    completed: int
    overdue: int
    items: list[MyCourseItem]


@router.get("/me/courses", response_model=MyCoursesResponse)
def my_courses(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    rows = (
        db.query(Enrollment, Course)
        .join(Course, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.organization_id == org_id,
            Enrollment.employee_id == emp.id,
        )
        .order_by(Enrollment.due_date.is_(None), Enrollment.due_date)
        .all()
    )

    today = get_local_today(db, org_id)
    items = []
    for enr, course in rows:
        overdue = bool(
            enr.due_date and enr.due_date < today and enr.completed_at is None
        )
        items.append(MyCourseItem(
            enrollment_id=enr.id,
            course=_course_out(db, course),
            due_date=enr.due_date,
            progress_percent=enr.progress_percent,
            completed_at=enr.completed_at,
            is_overdue=overdue,
        ))

    return MyCoursesResponse(
        total=len(items),
        pending=sum(1 for i in items if i.completed_at is None),
        completed=sum(1 for i in items if i.completed_at is not None),
        overdue=sum(1 for i in items if i.is_overdue),
        items=items,
    )


class LessonWithProgress(BaseModel):
    lesson: LessonOut
    completed: bool
    last_position_seconds: int
    seconds_watched: int


class MyCourseDetail(BaseModel):
    enrollment: EnrollmentOut
    course: CourseOut
    lessons: list[LessonWithProgress]
    next_lesson_id: Optional[int] = None


@router.get("/me/courses/{course_id}", response_model=MyCourseDetail)
def my_course_detail(
    course_id: int,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    """Kou a ak kote mwen rive nan chak videyo."""
    course = _get_course_or_404(db, org_id, course_id)

    enr = db.query(Enrollment).filter(
        Enrollment.organization_id == org_id,
        Enrollment.course_id == course.id,
        Enrollment.employee_id == emp.id,
    ).first()
    if enr is None:
        raise HTTPException(status_code=404, detail="Ou pa enskri nan kou sa a.")

    lessons = db.query(Lesson).filter(
        Lesson.course_id == course.id
    ).order_by(Lesson.order_index).all()

    progress = {
        p.lesson_id: p
        for p in db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enr.id
        ).all()
    }

    items = []
    next_id = None
    for lesson in lessons:
        p = progress.get(lesson.id)
        done = bool(p and p.completed)
        if next_id is None and not done:
            next_id = lesson.id
        items.append(LessonWithProgress(
            lesson=LessonOut.model_validate(lesson),
            completed=done,
            last_position_seconds=p.last_position_seconds if p else 0,
            seconds_watched=p.seconds_watched if p else 0,
        ))

    return MyCourseDetail(
        enrollment=EnrollmentOut.model_validate(enr),
        course=_course_out(db, course),
        lessons=items,
        next_lesson_id=next_id,
    )


class ProgressResult(BaseModel):
    lesson_id: int
    completed: bool
    course_progress_percent: int
    course_completed: bool
    message: str


@router.post("/me/progress", response_model=ProgressResult)
def save_progress(
    payload: ProgressUpdate,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    """
    Frontend lan rele sa a chak 15-30 segonn pandan videyo a ap jwe.
    Yon leson konte fini lè moun nan gade 90% nan li, oswa lè frontend lan
    di eksplisitman `completed: true`.
    """
    lesson = _get_lesson_or_404(db, org_id, payload.lesson_id)

    enr = db.query(Enrollment).filter(
        Enrollment.organization_id == org_id,
        Enrollment.course_id == lesson.course_id,
        Enrollment.employee_id == emp.id,
    ).first()
    if enr is None:
        raise HTTPException(status_code=404, detail="Ou pa enskri nan kou sa a.")

    p = db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enr.id,
        LessonProgress.lesson_id == lesson.id,
    ).first()
    if p is None:
        p = LessonProgress(enrollment_id=enr.id, lesson_id=lesson.id)
        db.add(p)
        db.flush()

    # `seconds_watched` monte sèlman — konsa si moun nan rekile nan videyo a,
    # nou pa pèdi tan li te deja gade a.
    p.seconds_watched = max(p.seconds_watched or 0, payload.seconds_watched)
    p.last_position_seconds = payload.last_position_seconds

    should_complete = payload.completed
    if not should_complete and lesson.duration_seconds:
        should_complete = p.seconds_watched >= lesson.duration_seconds * WATCH_THRESHOLD

    if should_complete and not p.completed:
        p.completed = True
        p.completed_at = datetime.now(timezone.utc)

    was_complete = enr.completed_at is not None

    # OBLIGATWA: sesyon an gen autoflush=False, donk chanjman sou `p` la
    # rete nan memwa. San flush sa a, COUNT nan _recompute_progress pa
    # wè leson nou fèk make a epi pousantaj la rete 0.
    db.flush()
    _recompute_progress(db, enr)
    db.commit()
    db.refresh(enr)

    just_finished = enr.completed_at is not None and not was_complete
    if just_finished:
        course = db.query(Course).filter(Course.id == enr.course_id).first()
        _notify(
            db, org_id, emp.user_id,
            title="Fòmasyon fini",
            body=f"Ou fini kou '{course.title if course else ''}'. Bravo!",
            link=f"/training/{enr.course_id}",
        )

    return ProgressResult(
        lesson_id=lesson.id,
        completed=bool(p.completed),
        course_progress_percent=enr.progress_percent,
        course_completed=enr.completed_at is not None,
        message="Ou fini kou a!" if just_finished else "Pwogrè anrejistre.",
    )


class CompleteRequest(BaseModel):
    score: Optional[int] = Field(default=None, ge=0, le=100)


@router.post("/me/courses/{course_id}/complete", response_model=EnrollmentOut)
def complete_course(
    course_id: int,
    payload: CompleteRequest,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    """
    Make yon kou fini, ak yon nòt si kou a gen yon tès.
    Nou refize si leson obligatwa yo poko fini.
    """
    course = _get_course_or_404(db, org_id, course_id)

    enr = db.query(Enrollment).filter(
        Enrollment.organization_id == org_id,
        Enrollment.course_id == course.id,
        Enrollment.employee_id == emp.id,
    ).first()
    if enr is None:
        raise HTTPException(status_code=404, detail="Ou pa enskri nan kou sa a.")

    db.flush()
    _recompute_progress(db, enr)
    if enr.progress_percent < 100:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ou fini {enr.progress_percent}% nan kou a. "
                "Gade tout leson obligatwa yo anvan."
            ),
        )

    if payload.score is not None:
        enr.score = payload.score
        if payload.score < (course.passing_score or 0):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nòt ou a se {payload.score}%. "
                    f"Ou bezwen omwen {course.passing_score}% pou pase."
                ),
            )

    if enr.completed_at is None:
        enr.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(enr)
    return enr


# ---------------------------------------------------------------------------
# RAPÒ
# ---------------------------------------------------------------------------

class ReportRow(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    due_date: Optional[date] = None
    progress_percent: int
    completed_at: Optional[datetime] = None
    score: Optional[int] = None
    is_overdue: bool


class CourseReport(BaseModel):
    course_id: int
    course_title: str
    total_enrolled: int
    completed: int
    in_progress: int
    not_started: int
    overdue: int
    completion_rate: float
    rows: list[ReportRow]


@router.get("/courses/{course_id}/report", response_model=CourseReport)
def course_report(
    course_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """
    Kiyès ki fini kou a. HR wè tout moun; yon manadjè wè ekip dirèk li.
    """
    course = _get_course_or_404(db, org_id, course_id)

    q = (
        db.query(Enrollment, Employee)
        .join(Employee, Enrollment.employee_id == Employee.id)
        .filter(
            Enrollment.organization_id == org_id,
            Enrollment.course_id == course.id,
        )
    )

    if user.role == UserRole.MANAGER:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        # Manadjè a wè ekip li A PLIS pwòp enskripsyon pa l. San dezyèm
        # kondisyon an, yon manadjè pa wè kou obligatwa li menm dwe swiv.
        q = q.filter(or_(
            Employee.manager_id == viewer.id,
            Employee.id == viewer.id,
        ))
    elif user.role not in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR):
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou rapò sa a.")

    today = get_local_today(db, org_id)
    rows = []
    for enr, emp in q.order_by(Employee.last_name).all():
        rows.append(ReportRow(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
            due_date=enr.due_date,
            progress_percent=enr.progress_percent,
            completed_at=enr.completed_at,
            score=enr.score,
            is_overdue=bool(
                enr.due_date and enr.due_date < today and enr.completed_at is None
            ),
        ))

    completed = sum(1 for r in rows if r.completed_at is not None)
    return CourseReport(
        course_id=course.id,
        course_title=course.title,
        total_enrolled=len(rows),
        completed=completed,
        in_progress=sum(
            1 for r in rows if r.completed_at is None and r.progress_percent > 0
        ),
        not_started=sum(
            1 for r in rows if r.completed_at is None and r.progress_percent == 0
        ),
        overdue=sum(1 for r in rows if r.is_overdue),
        completion_rate=round(completed * 100 / len(rows), 1) if rows else 0.0,
        rows=rows,
    )


class OverdueItem(BaseModel):
    employee_id: int
    employee_name: str
    course_id: int
    course_title: str
    due_date: date
    days_late: int
    progress_percent: int


class OverdueResponse(BaseModel):
    total: int
    items: list[OverdueItem]


@router.get("/overdue", response_model=OverdueResponse, dependencies=[Depends(require_hr)])
def overdue_training(org_id: TenantId, db: DbSession):
    """Tout fòmasyon ki depase delè yo epi ki poko fini."""
    today = get_local_today(db, org_id)

    rows = (
        db.query(Enrollment, Employee, Course)
        .join(Employee, Enrollment.employee_id == Employee.id)
        .join(Course, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.organization_id == org_id,
            Enrollment.completed_at.is_(None),
            Enrollment.due_date.isnot(None),
            Enrollment.due_date < today,
        )
        .order_by(Enrollment.due_date)
        .all()
    )

    items = [
        OverdueItem(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            course_id=course.id,
            course_title=course.title,
            due_date=enr.due_date,
            days_late=(today - enr.due_date).days,
            progress_percent=enr.progress_percent,
        )
        for enr, emp, course in rows
    ]
    return OverdueResponse(total=len(items), items=items)