from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from app.db import get_db
from app.auth import require_admin, CurrentUser
from app.config import WORKER_API_KEY

router = APIRouter(prefix="/jobs", tags=["video-jobs"])


def verify_worker(x_worker_key: str = Header(default="")):
    """
    Separate auth path from the student/admin JWT flow — the Colab
    notebook isn't a logged-in user, it's a trusted batch worker.
    """
    if not WORKER_API_KEY or x_worker_key != WORKER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing worker key")
    return True


class CompleteJobIn(BaseModel):
    result_video_url: str


class FailJobIn(BaseModel):
    error_message: str


@router.get("/next")
def get_next_job(worker_id: str = "colab-worker-1", _=Depends(verify_worker)):
    """
    Called by the Colab/Kaggle notebook once per loop iteration during a
    batch-render run. Atomically claims the oldest queued job so two
    accidental concurrent runs don't render the same lesson twice.
    """
    db = get_db()
    queued = (
        db.table("video_jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not queued.data:
        return {"job": None, "message": "No queued jobs right now"}

    job = queued.data[0]
    claimed = (
        db.table("video_jobs")
        .update({"status": "in_progress", "claimed_at": "now()", "claimed_by": worker_id})
        .eq("id", job["id"])
        .eq("status", "queued")  # guards against a race with another worker
        .execute()
    )
    if not claimed.data:
        # Someone else claimed it between our select and update — tell the worker to retry
        return {"job": None, "message": "Job was claimed by another worker, retry"}

    db.table("lessons").update({"status": "rendering"}).eq("id", job["lesson_id"]).execute()
    return {"job": claimed.data[0]}


@router.post("/{job_id}/complete")
def complete_job(job_id: str, payload: CompleteJobIn, _=Depends(verify_worker)):
    db = get_db()
    job_res = db.table("video_jobs").select("*").eq("id", job_id).single().execute()
    if not job_res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    job = job_res.data

    db.table("video_jobs").update({
        "status": "done",
        "result_video_url": payload.result_video_url,
        "completed_at": "now()",
    }).eq("id", job_id).execute()

    db.table("lessons").update({
        "status": "ready",
        "video_url": payload.result_video_url,
    }).eq("id", job["lesson_id"]).execute()

    return {"status": "done"}


@router.post("/{job_id}/fail")
def fail_job(job_id: str, payload: FailJobIn, _=Depends(verify_worker)):
    db = get_db()
    job_res = db.table("video_jobs").select("*").eq("id", job_id).single().execute()
    if not job_res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    job = job_res.data

    db.table("video_jobs").update({
        "status": "failed",
        "error_message": payload.error_message,
    }).eq("id", job_id).execute()

    db.table("lessons").update({"status": "failed"}).eq("id", job["lesson_id"]).execute()
    return {"status": "failed"}


@router.get("")
def list_jobs(admin: CurrentUser = Depends(require_admin)):
    """Admin dashboard view of the render queue — real-time, no caching."""
    db = get_db()
    res = db.table("video_jobs").select("*, lessons(title)").order("created_at", desc=True).execute()
    return res.data
