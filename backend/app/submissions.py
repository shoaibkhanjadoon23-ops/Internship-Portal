import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db import get_db
from app.auth import get_current_user, require_admin, CurrentUser
from app.ai_providers import generate_text

router = APIRouter(prefix="/submissions", tags=["submissions"])


class SubmissionIn(BaseModel):
    lesson_id: str
    content: str


def _grading_prompt(lesson_title: str, lesson_script: str, submission: str) -> str:
    return f"""You are grading a student's submission for a lesson.

Lesson title: {lesson_title}
Lesson content (for reference): {lesson_script[:2000]}

Student submission:
{submission}

Return ONLY valid JSON, no markdown fences, no preamble, in exactly this shape:
{{"score": <integer 0-100>, "feedback": "<2-4 sentences of specific, constructive feedback>"}}
"""


@router.post("")
def submit_work(payload: SubmissionIn, user: CurrentUser = Depends(get_current_user)):
    db = get_db()

    lesson_res = db.table("lessons").select("title, script").eq("id", payload.lesson_id).single().execute()
    if not lesson_res.data:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson = lesson_res.data

    inserted = db.table("submissions").insert({
        "lesson_id": payload.lesson_id,
        "student_id": user.id,
        "content": payload.content,
        "status": "submitted",
    }).execute()
    submission = inserted.data[0]

    # Real AI grading call — Gemini first, Groq fallback (see ai_providers.py)
    try:
        raw, provider = generate_text(
            _grading_prompt(lesson["title"], lesson["script"], payload.content),
            json_mode=True,
        )
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        score = float(parsed["score"])
        feedback = parsed["feedback"]

        db.table("submissions").update({
            "status": "graded",
            "ai_score": score,
            "ai_feedback": feedback,
            "ai_provider": provider,
            "graded_at": "now()",
        }).eq("id", submission["id"]).execute()

        submission.update({
            "status": "graded", "ai_score": score, "ai_feedback": feedback, "ai_provider": provider
        })
    except Exception as e:
        # Grading failed (both providers down / quota exceeded) — leave as 'submitted'
        # so an admin can grade manually or retry later. Don't fabricate a score.
        db.table("submissions").update({
            "status": "flagged",
        }).eq("id", submission["id"]).execute()
        submission["status"] = "flagged"
        submission["grading_error"] = str(e)

    return submission


@router.get("/me")
def my_submissions(user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    res = db.table("submissions").select("*, lessons(title)").eq("student_id", user.id).order("created_at", desc=True).execute()
    return res.data


@router.get("")
def all_submissions(admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    res = db.table("submissions").select("*, lessons(title), profiles(full_name)").order("created_at", desc=True).execute()
    return res.data
