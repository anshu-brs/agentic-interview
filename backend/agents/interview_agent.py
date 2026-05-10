import os
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# ── Load .env ─────────────────────────────────────────────────────────────────
_this_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_this_dir / ".env", override=True)
load_dotenv(dotenv_path=_this_dir.parent / ".env", override=False)
load_dotenv(dotenv_path=_this_dir.parent.parent / ".env", override=False)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
print(f"[interview_agent] Groq key loaded: {'YES' if GROQ_API_KEY else 'NO — add GROQ_API_KEY to .env'}")

client = Groq(api_key=GROQ_API_KEY)
MODEL  = "llama-3.3-70b-versatile"   # free, fast, very capable
TOTAL_QUESTIONS = 10


def parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            try:
                return json.loads(p)
            except Exception:
                continue
    return json.loads(text)


async def call_groq(prompt: str) -> str:
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1200,
        )
    )
    return resp.choices[0].message.content


# ── start_interview ───────────────────────────────────────────────────────────
async def start_interview(role: str, resume_summary: str, skills: list, experience_years: int, skill_gaps: list = None) -> dict:
    gaps_section = ""
    if skill_gaps:
        gaps_section = f"\nIdentified skill gaps to probe later: {', '.join(skill_gaps)}"

    prompt = f"""You are a senior interviewer. Return ONLY valid JSON, no markdown, no extra text.

Role: {role}
Candidate background: {resume_summary}
Skills: {', '.join(skills)}
Experience: {experience_years} years{gaps_section}

Generate a warm-up behavioral first question specific to this role.

Return exactly this JSON and nothing else:
{{
  "question": "your question here",
  "question_type": "behavioral",
  "hint": "one sentence tip for the candidate",
  "difficulty": "warm-up",
  "topic": "topic name e.g. motivation"
}}"""

    text = await call_groq(prompt)
    try:
        data = parse_json(text)
    except Exception:
        data = {}

    return {
        "question":        data.get("question", f"Tell me about yourself and why you want to work as a {role}."),
        "question_type":   "behavioral",
        "hint":            data.get("hint", "Use the STAR method — Situation, Task, Action, Result."),
        "difficulty":      "warm-up",
        "topic":           data.get("topic", "introduction"),
        "question_number": 1,
        "total_questions": TOTAL_QUESTIONS,
    }


# ── next_question ─────────────────────────────────────────────────────────────
async def next_question(role: str, resume_summary: str, question: str,
                        answer: str, history: list, question_number: int, skill_gaps: list = None) -> dict:

    history_lines, used_topics = [], []
    for i, h in enumerate(history):
        t = h.get("topic", f"topic_{i}")
        used_topics.append(t)
        history_lines.append(
            f"Q{i+1}[{h.get('question_type','?')}] topic={t}: {h['question']}\n"
            f"  Answer: {h['answer']}\n  Score: {h.get('score','?')}/10"
        )

    recent = [h.get("score", 5) for h in history[-3:]]
    avg    = sum(recent) / len(recent) if recent else 5
    trend  = ("Drop difficulty, ask easier question, candidate is struggling." if avg <= 4
              else "Increase difficulty significantly, candidate is excelling." if avg >= 8
              else "Maintain current difficulty.")

    is_final = question_number >= TOTAL_QUESTIONS

    gaps_hint = ""
    if skill_gaps:
        gaps_hint = f"\nWeak areas to probe (use these topics when progressing to mid/tough questions): {', '.join(skill_gaps)}"

    prompt = f"""You are a senior interviewer for {role} role. Return ONLY valid JSON, no markdown, no extra text.

Candidate background: {resume_summary}{gaps_hint}

Interview history (NEVER repeat these topics: {', '.join(used_topics) or 'none'}):
{chr(10).join(history_lines) or 'No previous questions.'}

Current Q{question_number}/{TOTAL_QUESTIONS}: {question}
Candidate answer: {answer}

Adaptive rule: {trend}
Question progression: Q1-2=warm-up behavioral, Q3-5=mid technical, Q6-8=tough technical, Q9-10=edge cases/leadership.
is_final must be {"true" if is_final else "false"}.
Next question MUST be about {role} and on a completely NEW topic not in the forbidden list.

Return exactly this JSON and nothing else:
{{
  "score": 7,
  "feedback": "2-3 sentence specific coaching feedback",
  "is_final": {"true" if is_final else "false"},
  "next_question": {{
    "question": "next role-specific question on a new topic",
    "question_type": "technical",
    "hint": "one sentence tip",
    "difficulty": "mid",
    "topic": "new unique topic name"
  }}
}}"""

    text = await call_groq(prompt)
    try:
        data = parse_json(text)
    except Exception:
        data = {}

    response = {
        "score":    int(data.get("score", 5)),
        "feedback": data.get("feedback", "Good attempt. Try to use specific examples next time."),
        "is_final": bool(data.get("is_final", is_final)),
    }
    nq = data.get("next_question", {})
    if not response["is_final"] and nq:
        response["next_question"] = {
            "question":        nq.get("question", f"Describe a technical challenge you faced as a {role}."),
            "question_type":   nq.get("question_type", "technical"),
            "hint":            nq.get("hint", "Be specific and use real examples."),
            "difficulty":      nq.get("difficulty", "mid"),
            "topic":           nq.get("topic", f"topic_{question_number}"),
            "question_number": question_number + 1,
            "total_questions": TOTAL_QUESTIONS,
        }
    return response


# ── get_feedback ──────────────────────────────────────────────────────────────
async def get_feedback(role: str, history: list) -> dict:
    history_text = "\n\n".join(
        [f"Q{i+1}[{h.get('question_type','?')}]: {h['question']}\n"
         f"Answer: {h['answer']}\nScore: {h.get('score','?')}/10\n"
         f"Audio — confidence: {h.get('confidence_score','N/A')}, clarity: {h.get('clarity_score','N/A')}, "
         f"pace: {h.get('pace_wpm','N/A')} wpm, tone: {h.get('tone','N/A')}, hesitations: {h.get('hesitation_count','N/A')}"
         for i, h in enumerate(history)]
    )

    # Aggregate audio signals for the prompt summary
    conf_vals = [h['confidence_score'] for h in history if h.get('confidence_score') is not None]
    clar_vals = [h['clarity_score'] for h in history if h.get('clarity_score') is not None]
    audio_summary = ""
    if conf_vals:
        avg_conf = sum(conf_vals)/len(conf_vals)
        avg_clar = sum(clar_vals)/len(clar_vals) if clar_vals else None
        audio_summary = (f"\nOverall audio analysis: avg confidence={avg_conf:.1f}/10, "
                         f"avg clarity={avg_clar:.1f}/10 over {len(conf_vals)} answers. "
                         "Include communication delivery insights in feedback.")

    prompt = f"""You are a senior hiring manager. Return ONLY valid JSON, no markdown, no extra text.

Role: {role}{audio_summary}
Interview transcript:
{history_text}

Return exactly this JSON and nothing else:
{{
  "overall_score": 72,
  "overall_verdict": "Hire",
  "summary": "2-3 sentence overall summary including communication observations",
  "strengths": ["strength1", "strength2", "strength3"],
  "areas_to_improve": ["area1", "area2", "area3"],
  "communication_insights": "1-2 sentences on vocal delivery, confidence, clarity based on audio data",
  "per_question_scores": [{{"question": "...", "score": 7, "note": "brief note"}}],
  "recommended_resources": ["specific resource 1", "specific resource 2"]
}}
Verdict rules: Strong Hire(85+), Hire(70-84), Borderline(50-69), No Hire(<50)"""

    text = await call_groq(prompt)
    try:
        data = parse_json(text)
    except Exception:
        data = {}

    return {
        "overall_score":         int(data.get("overall_score", 60)),
        "overall_verdict":       data.get("overall_verdict", "Borderline"),
        "summary":               data.get("summary", "Interview completed."),
        "strengths":             data.get("strengths", []),
        "areas_to_improve":      data.get("areas_to_improve", []),
        "communication_insights": data.get("communication_insights", ""),
        "per_question_scores":   data.get("per_question_scores", []),
        "recommended_resources": data.get("recommended_resources", []),
    }