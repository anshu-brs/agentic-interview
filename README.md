# MockMaster — Intelligent Mock Interview Agent

An agentic AI-powered mock interview platform. Upload your resume → get adaptive role-specific interview questions → receive multimodal feedback (technical + audio + visual) + live job recommendations.

---

## Features

### 🧠 Context Understanding
- PyMuPDF PDF parsing + Groq LLM analysis
- Extracts skills, experience, work history, education
- Infers up to 3 realistic job roles from resume evidence
- Generates **skill gaps per role** — injected into the interview orchestrator to probe weak areas

### 🎙️ Interview Orchestrator Agent
- 10 fully **dynamic LLM-generated questions** (no static list)
- **Adaptive difficulty** based on rolling score of last 3 answers
- Question progression: Q1-2 warm-up → Q3-5 mid → Q6-8 tough → Q9-10 edge cases
- **Topic deduplication** — never repeats a topic

### 🎤 Audio Intelligence
- `librosa` + `pyin` for pitch/F0 analysis
- RMS-based hesitation/pause detection
- Speaking pace (WPM), confidence score, clarity score
- All audio metrics included in the final LLM feedback prompt

### 👁️ Visual Intelligence — face-api.js (real CV)
- **face-api.js v0.22.2** — TinyFaceDetector + FaceLandmark68Tiny + FaceExpressionNet
- Eye contact, posture, engagement, nervousness — all computed from real face data
- Rolling 5-frame buffer per answer for smooth scores

### 📊 Feedback & Coaching
- Overall score + verdict: Strong Hire / Hire / Borderline / No Hire
- Audio scores from all answers passed to LLM for communication insights

### 💼 Job Recommendations
- Live crawling: Remotive, Lever (Swiggy), Greenhouse (Microsoft)
- Weighted match scoring with match reason + missing skills per job

---

## Tech Stack
| Layer | Tech |
|-------|------|
| Backend | Python 3.11+, FastAPI |
| LLM | Groq API (llama-3.3-70b-versatile) |
| PDF parsing | PyMuPDF (fitz) |
| Audio | librosa, pydub, ffmpeg |
| Visual | face-api.js (browser-side CDN) |
| STT | Web Speech API (browser) |
| Frontend | Vanilla HTML/CSS/JS |

---

## Setup

### Prerequisites
- Python 3.11+
- ffmpeg: `brew install ffmpeg` (Mac) / `sudo apt install ffmpeg` (Linux) / `winget install ffmpeg` (Windows)
- Free Groq API key from https://console.groq.com

### 1. Configure

```bash
cp backend/agents/.env.example backend/agents/.env
# Add your key: GROQ_API_KEY=your_key_here
```

### 2. Run

**Windows:** `cd backend && run_app.bat`

**Mac/Linux:**
```bash
cd backend
chmod +x run_app.sh && ./run_app.sh
```

### 3. Open http://127.0.0.1:8000 in Chrome or Edge

---

## Project Structure

```
agentic-interviewer/
├── backend/
│   ├── main.py                  # FastAPI routes
│   ├── agents/
│   │   ├── resume_agent.py      # PDF parse + skill_gaps
│   │   ├── interview_agent.py   # Adaptive orchestrator
│   │   └── .env.example
│   ├── services/
│   │   ├── audio_analyser.py    # librosa pipeline
│   │   ├── job_aggregator.py
│   │   └── job_sources.py
│   └── requirements.txt
├── frontend/
│   └── interview.html           # face-api.js integrated
├── samples/
│   ├── sample_resume.txt        # Example resume
│   └── expected_output.json     # Expected API output
└── ARCHITECTURE.md              # Full design document
```

---

## API Endpoints
| Endpoint | Description |
|----------|-------------|
| POST /api/analyse-resume | Upload PDF → profile + skill_gaps |
| POST /api/interview/start | Begin interview |
| POST /api/interview/answer | Submit answer → score + next Q |
| POST /api/interview/feedback | Final multimodal report |
| POST /api/interview/analyse-audio | Audio → confidence/clarity metrics |
| POST /api/jobs | Resume → matched live jobs |

---

## Quick Evaluation
1. Upload `samples/sample_resume.txt` (as PDF) to `/api/analyse-resume`
2. Compare response to `samples/expected_output.json`

## Browser Requirements
Chrome or Edge required for Web Speech API + MediaRecorder.
