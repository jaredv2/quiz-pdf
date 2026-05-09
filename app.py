import os
import json
import base64
import re
import random
import io
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    Groq = None
    GROQ_AVAILABLE = False

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

app = Flask(__name__, static_folder="static")
CORS(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def extract_pdf_text(b64: str) -> str:
    if not PDF_AVAILABLE:
        return ""
    pdf_bytes = base64.b64decode(b64)
    text = ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    except Exception as e:
        print(f"PyPDF2 error: {e}")
    if not text.strip() and OCR_AVAILABLE:
        try:
            images = convert_from_bytes(pdf_bytes)
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
        except Exception as e:
            print(f"OCR error: {e}")
    return text.strip()[:18000]


def call_ai(messages: list, system: str = None) -> dict:
    if not GROQ_AVAILABLE:
        raise RuntimeError("The groq package is not installed. Run: pip install -r requirements.txt")
    if not GROQ_API_KEY:
        raise RuntimeError("Missing GROQ_API_KEY environment variable")

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    client = Groq(api_key=GROQ_API_KEY, timeout=180.0)
    response = client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        temperature=0.35,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"^```\s*", "", content)
    content = re.sub(r"```\s*$", "", content).strip()
    match = re.search(r'(\{[\s\S]*\})', content)
    if match:
        content = match.group(1)
    return json.loads(content)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    body = request.get_json()
    if not body:
        return jsonify({"error": "Empty request"}), 400

    difficulty = body.get("difficulty", "medium")
    num_questions = int(body.get("num_questions", 10))
    input_type = body.get("input_type", "pdf")
    randomize_seed = body.get("seed", random.randint(1000, 9999))

    if input_type == "pdf":
        if "pdf_base64" not in body:
            return jsonify({"error": "Missing pdf_base64"}), 400
        content_text = extract_pdf_text(body["pdf_base64"])
        if not content_text:
            return jsonify({"error": "Could not extract text. The PDF may be image-only (needs OCR) or empty."}), 400
    elif input_type == "text":
        content_text = body.get("raw_text", "").strip()[:18000]
        if not content_text:
            return jsonify({"error": "No text provided"}), 400
    elif input_type == "image":
        content_text = body.get("image_description", "").strip()
        if not content_text:
            return jsonify({"error": "No image description provided"}), 400
    else:
        return jsonify({"error": "Invalid input_type"}), 400

    diff_profiles = {
        "beginner": "Very basic recall. Who/what/when. First-time learners.",
        "easy":     "Simple comprehension. Direct facts from the text.",
        "medium":   "Application. Connecting ideas from the document.",
        "hard":     "Analysis and synthesis. Deep understanding required.",
        "expert":   "Evaluation and critical thinking. Inference and nuance.",
        "mixed":    "Mix all levels. Set each question's 'difficulty' field individually.",
    }
    type_distribution = {
        "beginner": "50% truefalse, 30% mcq, 20% open_ended",
        "easy":     "40% truefalse, 40% mcq, 20% open_ended",
        "medium":   "15% truefalse, 45% mcq, 25% open_ended, 15% fill_blank",
        "hard":     "10% truefalse, 35% mcq, 40% open_ended, 15% mcq_multi",
        "expert":   "5% truefalse, 25% mcq, 50% open_ended, 20% mcq_multi",
        "mixed":    "20% truefalse, 35% mcq, 30% open_ended, 10% fill_blank, 5% mcq_multi",
    }

    system = f"""You are an expert assessment designer. Return exactly one valid JSON object and no markdown.

Quality requirements:
- Use only facts, relationships, and implications supported by the provided document.
- Prefer precise, unambiguous wording over broad trivia.
- Cover the document's core ideas, definitions, causes/effects, processes, evidence, and important contrasts.
- Avoid duplicate questions, vague phrasing, trick wording, and answers that depend on outside knowledge.
- Distractors must be plausible, mutually exclusive, and clearly wrong for a specific reason.
- Explanations must justify the correct answer with document-grounded reasoning.
- Preserve the document's detected language for every user-facing string.

Strict question type definitions:
1. "truefalse": write a declarative statement, not a question. options must be ["True","False"]. correct_answer must be "True" or "False".
2. "mcq": exactly four options labelled "A. ...", "B. ...", "C. ...", "D. ...". correct_answer is one letter.
3. "mcq_multi": exactly five options labelled A-E. correct_answer is comma-separated letters, with at least two correct answers.
4. "fill_blank": a single sentence with one "___" blank. options = []. correct_answer is the shortest exact phrase that fills the blank.
5. "open_ended": a focused explain/compare/analyze question. options = []. correct_answer is a complete model answer of 2-4 sentences.

Seed {randomize_seed}: generate fresh questions by varying topic coverage, angle, and phrasing."""
    prompt = f"""Analyze and generate a quiz. Reply ONLY with this JSON:

{{
  "document": {{
    "title": "title",
    "subject": "subject",
    "theme": "one-sentence theme",
    "level": "audience level",
    "summary": "2-3 sentence summary",
    "language": "en"
  }},
  "questions": [
    {{
      "id": 1,
      "type": "mcq",
      "difficulty": "{difficulty}",
      "points": 2,
      "question": "What is X?",
      "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
      "correct_answer": "B",
      "explanation": "B is correct because..."
    }},
    {{
      "id": 2,
      "type": "truefalse",
      "difficulty": "{difficulty}",
      "points": 1,
      "question": "Write a declarative statement here.",
      "options": ["True", "False"],
      "correct_answer": "True",
      "explanation": "..."
    }},
    {{
      "id": 3,
      "type": "open_ended",
      "difficulty": "{difficulty}",
      "points": 4,
      "question": "Explain the concept of...",
      "options": [],
      "correct_answer": "Full model answer in complete sentences.",
      "explanation": "Key concepts: concept1, concept2"
    }}
  ]
}}

GENERATE {num_questions} questions. IDs must be 1 through {num_questions} sequentially, with no gaps.
Difficulty: {difficulty.upper()} — {diff_profiles.get(difficulty, '')}
Type distribution: {type_distribution.get(difficulty, type_distribution['medium'])}
Cover at least {min(3, num_questions)} distinct topics/sections from the document.
Points: truefalse=1, fill_blank=2, mcq=2-3, mcq_multi=3-4, open_ended=3-6 (harder=more points).
For each question, include a concise explanation that names the key evidence or reasoning from the document.
If the document is short, generate fewer question angles but keep each question answerable from the text.

DOCUMENT CONTENT:
{content_text}"""

    try:
        result = call_ai([{"role": "user", "content": prompt}], system=system)

        questions = result.get("questions", [])
        valid_types = {"mcq", "truefalse", "open_ended", "mcq_multi", "fill_blank", "ordering"}
        cleaned = []
        for i, q in enumerate(questions):
            q["id"] = i + 1
            qtype = q.get("type", "open_ended")
            if qtype not in valid_types:
                qtype = "open_ended"
            opts = q.get("options", [])
            ca = str(q.get("correct_answer", ""))
            # Auto-fix type based on options
            if isinstance(opts, list):
                opts_set = {str(o).strip() for o in opts}
                if opts_set == {"True", "False"}:
                    qtype = "truefalse"
                elif len(opts) >= 4 and all(re.match(r'^[A-E]\.', str(o)) for o in opts[:4]):
                    if ca.upper() in ("A", "B", "C", "D", "E"):
                        qtype = "mcq" if "," not in ca else "mcq_multi"
            # Fix: open_ended with empty answer
            if qtype == "open_ended" and not ca.strip():
                q["correct_answer"] = q.get("explanation", "Refer to the document content.")
            # Fix: truefalse correct_answer must be exactly True or False
            if qtype == "truefalse":
                q["options"] = ["True", "False"]
                if ca.lower() in ("true", "vrai", "oui", "yes", "1"):
                    q["correct_answer"] = "True"
                elif ca.lower() in ("false", "faux", "non", "no", "0"):
                    q["correct_answer"] = "False"
            # Ensure points
            if not q.get("points"):
                q["points"] = {"truefalse": 1, "fill_blank": 2, "mcq": 2, "mcq_multi": 3, "ordering": 3, "open_ended": 4}.get(qtype, 2)
            q["type"] = qtype
            cleaned.append(q)

        result["questions"] = cleaned
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/grade", methods=["POST"])
def grade():
    body = request.get_json()
    if not body:
        return jsonify({"error": "Empty body"}), 400

    questions = body.get("questions", [])
    user_answers = body.get("user_answers", {})
    document_info = body.get("document_info", {})
    time_taken = body.get("time_taken", 0)
    doc_lang = document_info.get("language", "en")
    max_points = sum(q.get("points", 2) for q in questions)

    qa_pairs = []
    for q in questions:
        qid = str(q["id"])
        qa_pairs.append({
            "id": q["id"],
            "type": q["type"],
            "difficulty": q.get("difficulty", "medium"),
            "max_points": q.get("points", 2),
            "question": q["question"],
            "correct_answer": q["correct_answer"],
            "user_answer": user_answers.get(qid, ""),
            "explanation": q.get("explanation", ""),
        })

    system = f"""You are a fair examiner and learning coach. Return exactly one valid JSON object and no markdown. All user-facing text must be in language: {doc_lang}.

Grading rules:
- Grade against the provided correct_answer and explanation, not outside knowledge.
- truefalse and mcq: exact letter/value match after trimming and case folding. Full points or 0.
- mcq_multi: award credit for correct selections and subtract credit for incorrect selections; never below 0; round to the nearest 0.5.
- fill_blank: accept equivalent wording, inflection, accents, punctuation differences, and article differences if the key concept is present.
- open_ended: evaluate concept coverage, precision, and reasoning. Full credit requires the central idea plus key supporting detail. Partial credit should be proportional and defensible.
- Mark partial=true whenever points_awarded is greater than 0 and less than points_max.
- Feedback must be specific: state what was correct, what was missing or incorrect, and how to improve.
- Explanations should teach the underlying idea, not merely repeat the answer.
- Be encouraging, but do not inflate scores."""
    prompt = f"""Grade this quiz for document: {document_info.get('title','Unknown')} (language: {doc_lang})
Max points: {max_points}

Data: {json.dumps(qa_pairs)}

Return:
{{
  "score": {{
    "points_earned": <number>,
    "points_max": {max_points},
    "percentage": <0-100>,
    "grade": "A/B/C/D/F",
    "grade_label": "label in {doc_lang}"
  }},
  "overall_remark": "2 specific, useful sentences in {doc_lang}",
  "time_taken_seconds": {time_taken},
  "question_reviews": [
    {{
      "id": <id>,
      "correct": <true/false>,
      "partial": <true/false>,
      "points_awarded": <float>,
      "points_max": <int>,
      "user_answer": "...",
      "correct_answer": "...",
      "remark": "specific feedback in {doc_lang}",
      "explanation": "clear teaching explanation in {doc_lang}"
    }}
  ],
  "missed_topics": ["..."],
  "strengths": ["..."],
  "study_tips": ["..."]
}}

Include a review entry for EVERY question id from 1 to {len(questions)}. Ensure points_earned equals the sum of points_awarded and percentage is rounded to the nearest integer."""

    try:
        result = call_ai([{"role": "user", "content": prompt}], system=system)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
