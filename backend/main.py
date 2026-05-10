import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from backend.agents.resume_agent import analyse_resume
from backend.agents.interview_agent import start_interview, next_question, get_feedback
from backend.agents.job_agent import get_job_recommendations

app = FastAPI(title="MockMaster API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_query_profile(data):
    return {
        "skills": set(data.skills),
        "roles": [r.lower() for r in data.roles],
        "exp": data.experience_years,
    }

# ── Request / Response Models ────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    role: str
    resume_summary: str
    skills: list[str]
    experience_years: int
    skill_gaps: list[str] = []

class InterviewAnswerRequest(BaseModel):
    role: str
    resume_summary: str
    question: str
    answer: str
    history: list[dict]          # [{question, answer, score}, ...]
    question_number: int
    skill_gaps: list[str] = []

class FeedbackRequest(BaseModel):
    role: str
    history: list[dict]

class JobsRequest(BaseModel):
    skills: list[str]
    roles: list[str]
    experience_years: int
    resume_summary: str

# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/analyse-resume")
async def analyse_resume_endpoint(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        print("Received non-PDF file:", file.filename)
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    pdf_bytes = await file.read()
    try:
        result = await analyse_resume(pdf_bytes)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/start")
async def interview_start(req: InterviewStartRequest):
    try:
        result = await start_interview(req.role, req.resume_summary, req.skills, req.experience_years, req.skill_gaps)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/answer")
async def interview_answer(req: InterviewAnswerRequest):
    try:
        result = await next_question(
            role=req.role,
            resume_summary=req.resume_summary,
            question=req.question,
            answer=req.answer,
            history=req.history,
            question_number=req.question_number,
            skill_gaps=req.skill_gaps,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/feedback")
async def interview_feedback(req: FeedbackRequest):
    try:
        result = await get_feedback(req.role, req.history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/api/jobs")
# async def jobs_endpoint(req: JobsRequest):
#     try:
#         result = await get_job_recommendations(
#             skills=req.skills,
#             roles=req.roles,
#             experience_years=req.experience_years,
#             resume_summary=req.resume_summary,
#         )
#         return result
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

from backend.services.job_aggregator import get_all_jobs
@app.post("/api/jobs")
async def get_jobs(data: JobsRequest):

    jobs = get_all_jobs()

    profile = build_query_profile(data)

    skill_set = profile["skills"]
    roles = profile["roles"]
    exp = profile["exp"]

    scored_jobs = []

    for job in jobs:

        job_skills = set(job.get("required_skills", []))
        job_title = job.get("title", "").lower()

        # 1. skill match
        skill_match = len(skill_set & job_skills)

        # 2. role relevance
        role_match = any(r in job_title for r in roles)

        # 3. experience alignment (VERY IMPORTANT)
        job_level = job.get("experience_required", "").lower()

        exp_score = 0

        if "intern" in job_level and exp == 0:
            exp_score = 30
        elif "0-1" in job_level and exp <= 1:
            exp_score = 30
        elif "1-2" in job_level and 1 <= exp <= 2:
            exp_score = 30
        elif exp > 2:
            exp_score = 20

        # FINAL SCORE (weighted)
        score = (
            skill_match * 12 +
            (20 if role_match else 0) +
            exp_score
        )

        job["match_score"] = min(100, score)

        job["missing_skills"] = list(job_skills - skill_set)

        job["match_reason"] = (
            f"{skill_match} skill matches, "
            f"{'role aligned' if role_match else 'role mismatch'}, "
            f"{'experience fit' if exp_score > 0 else 'experience gap'}"
        )

        scored_jobs.append(job)

    # sort best matches
    scored_jobs.sort(key=lambda x: x["match_score"], reverse=True)

    return {"jobs": scored_jobs[:10]}


# ── Audio Analysis Route ─────────────────────────────────────────────────────
# ADD THIS IMPORT at the top of main.py:
#   from backend.services.audio_analyser import analyse_audio

from backend.services.audio_analyser import analyse_audio

@app.post("/api/interview/analyse-audio")
async def analyse_audio_endpoint(
    audio: UploadFile = File(...),
    transcript: str = ""
):
    """
    Receives a raw audio blob (webm/wav) from the browser MediaRecorder.
    Returns confidence_score, clarity_score, pace_wpm, hesitation_count,
    pitch_variation, tone, and plain-English coaching notes.
    """
    audio_bytes = await audio.read()
    try:
        result = analyse_audio(audio_bytes, transcript=transcript)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Serve frontend ───────────────────────────────────────────────────────────

# app.mount("/static", StaticFiles(directory="frontend/"), name="static")

# @app.get("/")
# async def root():
#     return FileResponse("frontend/index.html")

# @app.get("/{page}.html")
# async def serve_page(page: str):
#     path = f"frontend/{page}.html"
#     if os.path.exists(path):
#         return FileResponse(path)
#     raise HTTPException(status_code=404, detail="Page not found")


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "frontend")),
    name="static"
)

@app.get("/")
def home():
    return FileResponse(os.path.join(BASE_DIR, "frontend", "index.html"))

@app.get("/{page}.html")
def pages(page: str):
    return FileResponse(os.path.join(BASE_DIR, "frontend", f"{page}.html"))