from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db import get_db
from app.auth import get_current_user, require_admin, CurrentUser

router = APIRouter(prefix="/courses", tags=["courses"])


class CourseIn(BaseModel):
    title: str
    description: str = ""


class LessonIn(BaseModel):
    title: str
    script: str
    avatar_photo_url: str | None = None
    order_index: int = 0


@router.get("")
def list_courses(user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    res = db.table("courses").select("*").eq("is_published", True).order("created_at").execute()
    return res.data


@router.post("")
def create_course(payload: CourseIn, admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    res = db.table("courses").insert({
        "title": payload.title,
        "description": payload.description,
        "created_by": admin.id,
        "is_published": True,
    }).execute()
    return res.data[0]


@router.get("/{course_id}/lessons")
def list_lessons(course_id: str, user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    query = db.table("lessons").select("*").eq("course_id", course_id).order("order_index")
    # Admins can see every lesson (including drafts); students only see approved/ready ones
    if user.role != "admin":
        query = query.in_("status", ["approved", "ready"])
    res = query.execute()
    return res.data


@router.post("/{course_id}/lessons")
def create_lesson(course_id: str, payload: LessonIn, admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    res = db.table("lessons").insert({
        "course_id": course_id,
        "title": payload.title,
        "script": payload.script,
        "avatar_photo_url": payload.avatar_photo_url,
        "order_index": payload.order_index,
        "status": "draft",
        "created_by": admin.id,
    }).execute()
    return res.data[0]


@router.patch("/lessons/{lesson_id}/approve")
def approve_lesson(lesson_id: str, admin: CurrentUser = Depends(require_admin)):
    """
    Approving a lesson does two things in one step:
    1. Marks the lesson 'approved'
    2. Drops a new row into video_jobs so it's picked up by the
       next batch run of your Colab/Kaggle SadTalker worker.
    """
    db = get_db()
    lesson_res = db.table("lessons").select("*").eq("id", lesson_id).single().execute()
    if not lesson_res.data:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson = lesson_res.data

    db.table("lessons").update({
        "status": "queued",
        "approved_at": "now()",
    }).eq("id", lesson_id).execute()

    job = db.table("video_jobs").insert({
        "lesson_id": lesson_id,
        "script_text": lesson["script"],
        "avatar_photo_url": lesson.get("avatar_photo_url"),
        "status": "queued",
    }).execute()

    return {"lesson_id": lesson_id, "status": "queued", "video_job": job.data[0]}


@router.post("/{course_id}/enroll")
def enroll(course_id: str, user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    existing = db.table("enrollments").select("id").eq("student_id", user.id).eq("course_id", course_id).execute()
    if existing.data:
        return existing.data[0]
    res = db.table("enrollments").insert({"student_id": user.id, "course_id": course_id}).execute()
    return res.data[0]
