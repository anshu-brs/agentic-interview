# MockMaster — Architecture Document

## 1. Problem Summary & User Journey

MockMaster is an agentic AI-powered mock interview platform that takes a candidate's PDF resume, infers realistic target roles, and runs a fully adaptive interview with multimodal scoring (technical content + audio delivery + visual presence). It also crawls live job boards and surfaces match-scored openings.

**User Journey:**
1. **Upload Resume** → System parses PDF, extracts skills/experience, infers 3 likely roles, and identifies skill gaps per role.
2. **Select Role** → Candidate picks the role to be interviewed for.
3. **Live Interview** → 10 dynamically generated, adaptive questions with real-time audio and visual analysis per answer.
4. **Feedback Report** → Multimodal score: technical (LLM-scored), audio (librosa-based), visual (face-api.js), plus coached feedback and resource recommendations.
5. **Job Matches** → Resume-matched live job postings from Remotive, Lever, and Greenhouse APIs ranked by a weighted formula.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                       │
│                                                                   │
│  index.html ──► resume.html ──► interview.html ──► jobs.html     │
│                                                                   │
│  • PDF upload via fetch FormData                                  │
│  • Web Speech API (real-time STT)                                 │
│  • MediaRecorder (audio blob capture)                             │
│  • face-api.js (TinyFaceDetector + FaceLandmark68 + Expressions) │
│    runs entirely in-browser, no server CV call needed             │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / REST (FastAPI)
┌──────────────────────────▼──────────────────────────────────────┐
│                       BACKEND (FastAPI)                           │
│                                                                   │
│  /api/analyse-resume   → resume_agent.py                         │
│  /api/interview/start  → interview_agent.start_interview()       │
│  /api/interview/answer → interview_agent.next_question()         │
│  /api/interview/feedback → interview_agent.get_feedback()        │
│  /api/interview/analyse-audio → audio_analyser.py                │
│  /api/jobs             → job_aggregator.py + job_sources.py      │
└───────┬──────────────────┬──────────────────┬───────────────────┘
        │                  │                  │
   Groq API           librosa / pyin     Job APIs
   (llama-3.3-70b)    (server-side)      (Remotive, Lever,
                                          Greenhouse)
```

### Module Interactions

```
resume_agent.py
  └─ Outputs: skills, inferred_roles, experience_years, skill_gaps{}
       │
       └─► interview_agent.start_interview(skill_gaps=skill_gaps[role])
             └─► interview_agent.next_question(skill_gaps=skill_gaps[role])
                   └─► interview_agent.get_feedback(history with audio scores)
```

---

## 3. Module Design & Key Choices

### Module 1 — Context Understanding (resume_agent.py)
- **PDF parsing**: PyMuPDF (`fitz`) extracts raw text; works on text-based PDFs (not scanned images).
- **LLM analysis**: Single Groq `llama-3.3-70b-versatile` call returns structured JSON: name, skills, inferred_roles (up to 3), experience_years, skill_gaps keyed by role, strengths.
- **Trade-off**: Single prompt vs multi-stage parsing. Single prompt is faster and sufficient for well-formatted resumes. Scanned PDFs would need OCR (future work).

### Module 2 — Interview Orchestrator Agent (interview_agent.py)
- **Dynamic generation**: Every question is LLM-generated, never from a static list.
- **Adaptive difficulty**: Tracks rolling average score of last 3 answers. avg ≤ 4 → easier; avg ≥ 8 → harder. Warm-up (Q1-2) → mid (Q3-5) → tough (Q6-8) → edge cases (Q9-10).
- **Weak-area probing**: `skill_gaps[role]` from resume_agent is injected into the orchestrator prompt so gaps are probed in mid/tough rounds.
- **Topic deduplication**: `used_topics` list is injected as a forbidden list — prevents topic repetition.
- **Trade-off**: All intelligence in LLM prompts rather than hard-coded state machine → more natural but dependent on Groq API latency (~1-3s/call).

### Module 3 — Audio Intelligence (audio_analyser.py)
- **Pipeline**: Browser MediaRecorder captures `.webm` blob → sent to `/api/interview/analyse-audio` → `pydub` converts to WAV → `librosa` extracts features.
- **Pitch (F0)**: `librosa.pyin` (probabilistic YIN) — pitch_mean, pitch_std computed over voiced frames.
- **Hesitation/pauses**: RMS-based silence detection, counts pauses > 0.5s.
- **Speaking pace**: word count from browser transcript / voiced duration → WPM.
- **Scoring**: Weighted formula — `confidence = pitch_score × 0.35 + energy_score × 0.35 + hesitation_penalty × 0.3`. Scores 0-10.
- **Tone classification**: pitch_std < 20 Hz → flat; 20-50 Hz → moderate; > 50 Hz → expressive.
- **Integration with feedback**: All audio metrics are stored in the interview history and sent to `get_feedback()`, which includes them in the LLM coaching prompt.

### Module 4 — Visual Intelligence (interview.html, face-api.js)
- **Library**: `face-api.js v0.22.2` (browser-side, CDN). No backend CV call needed — runs on `<canvas>` from `<video>` element.
- **Models loaded**: TinyFaceDetector (fast), FaceLandmark68Tiny, FaceExpressionNet.
- **Metrics computed**:
  - **Eye contact**: face centre deviation from frame centre (normalised).
  - **Posture proxy**: face bounding box height as fraction of frame height — too small = leaning back; ideal 12-45%.
  - **Engagement**: 1 - neutral_expression_weight × detection_confidence.
  - **Nervousness**: fearful + disgusted × 0.5 + sad × 0.3 expression weights.
- **Smoothing**: Rolling buffer of last 5 detections averaged per answer to reduce jitter.
- **Sampling**: 2-second interval timer while camera is live; results captured at answer submission time.
- **Trade-off**: Browser-side runs at ~30ms/inference on modern laptops; no GPU needed. Less accurate than MediaPipe on low-light or angled faces — acceptable per PS heuristics-allowed clause.

### Module 5 — Technical Evaluation Engine
- **Scoring**: Groq `llama-3.3-70b-versatile` scores each answer 0-10 with 2-3 sentence coaching feedback.
- **Keyword/intent matching**: Handled implicitly by the LLM (no separate layer) — acceptable trade-off for hackathon scope.
- **Per-question breakdown**: `get_feedback()` returns `per_question_scores[]` with note per question.

### Module 6 — Feedback & Coaching Agent (interview_agent.get_feedback)
- **Inputs**: Full 10-question history including LLM scores, audio metrics (confidence, clarity, pace, tone, hesitation_count), and visual scores.
- **Output**: overall_score (0-100), verdict (Strong Hire / Hire / Borderline / No Hire), summary, strengths[], areas_to_improve[], communication_insights, recommended_resources[].
- **Verdict thresholds**: Strong Hire ≥ 85, Hire 70-84, Borderline 50-69, No Hire < 50.

### Job Recommendations (job_aggregator.py + job_sources.py)
- **Sources**: Remotive public API (remote jobs), Lever (Swiggy postings), Greenhouse (Microsoft postings).
- **Matching**: `skill_match × 12 + role_match × 20 + experience_score × 30`, capped at 100.
- **Output**: Top 10 jobs with match_score, match_reason, missing_skills.

---

## 4. Scoring Aggregation

| Signal | Source | Weight in Report |
|--------|--------|-----------------|
| Technical score (0-100) | LLM per-answer avg | Primary |
| Audio confidence (0-10) | librosa/pyin formula | Secondary |
| Audio clarity (0-10) | Hesitation + energy | Secondary |
| Eye contact (0-100) | face-api.js deviation | Informational |
| Posture (0-100) | face-api.js bounding box | Informational |
| Engagement (0-100) | face-api.js expressions | Informational |
| Nervousness (0-100) | face-api.js fear/sad expressions | Informational |

Audio and visual scores are reported separately in the feedback UI; the overall LLM verdict is based primarily on technical content with audio signals surfaced as coaching notes via `communication_insights`.

---

## 5. Limitations, Assumptions & Next Steps

**Limitations**
- Face-api.js posture is a proxy (face size vs frame), not a full body landmark model — accurate for seated laptop/desktop use.
- Audio analysis requires browser audio permission and a noise-controlled environment for reliable pitch extraction.
- Job sources are limited to 3 companies; more can be added as Lever/Greenhouse source configs.
- Scanned/image PDFs will fail text extraction (OCR not included).

**Assumptions**
- Candidates have a text-based PDF resume and a webcam.
- Groq API free tier is sufficient for demo (rate limits may apply under heavy load).

**Next Steps**
- Add MediaPipe Pose for full upper-body posture detection.
- Add coding round simulation with Judge0 code execution.
- Add historical performance tracking across sessions (localStorage or backend DB).
- Add PDF generation for feedback report download.
- Implement retry with exponential backoff on Groq rate limits.
