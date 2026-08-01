from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import FRONTEND_ORIGIN
from app import courses, jobs, submissions, mentor

app = FastAPI(title="Internship Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(courses.router)
app.include_router(jobs.router)
app.include_router(submissions.router)
app.include_router(mentor.router)


@app.get("/health")
def health():
    return {"status": "ok"}
