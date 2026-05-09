# QuizForge — PDF to AI Quiz Engine

> Drop a PDF. Get a quiz. Instantly.

Brutalist sepia UI · Flask backend · Pollinations AI · Zero database · 2 API calls per session

---

## Stack

| Layer    | Tech                        | Why                              |
|----------|-----------------------------|----------------------------------|
| Frontend | HTML + Vanilla JS           | Zero build step, instant deploy  |
| Backend  | Python + Flask              | Lightweight, easy to ship        |
| AI       | Pollinations AI (openai-large) | Simple hosted inference |
| HTTP     | httpx                       | Async-capable, clean API         |
| CORS     | flask-cors                  | Dev convenience                  |

---

## Local Setup (Windows)

### Prerequisites
- Python 3.10+ → https://python.org/downloads
- pip (comes with Python)

### 1. Clone / unzip the project
```
quizforge/
├── app.py
├── requirements.txt
├── README.md
└── static/
    └── index.html
```

### 2. Create virtual environment
```cmd
cd quizforge
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```cmd
pip install -r requirements.txt
```

### 4. Run
```cmd
python app.py
```

Open browser → http://localhost:5000

---

## How to Iterate

### Change the AI model
In `app.py`, line `MODEL = "openai-large"` — try:
- `"openai"` (faster, cheaper)
- `"openai-large"` (best quality, default)
- `"mistral"` (alternative)

### Change question count defaults
In `static/index.html`, edit the `<select id="num-questions">` options.

### Change number of questions sent to AI
The PDF text slice in `app.py` controls how much extracted text is sent.
- Increase to `[:15000]` for longer docs (slower, costs more tokens)
- Decrease to `[:4000]` for faster generation on short docs

### Add more question types
In `app.py` `/api/analyze` prompt, add to the JSON schema example a new type like `"fill_blank"`.

### Change the UI theme
CSS variables are at the top of `static/index.html` under `:root {}`.
- `--parch` = background color
- `--ink` = primary text/dark color
- `--amber` = accent color

---

## Architecture — 2 API Calls Only

```
User uploads PDF
       ↓
POST /api/analyze  ← Call #1
  → Extract content + generate ALL questions in one shot
  → Returns: document metadata + N questions with answers
       ↓
User answers quiz (all client-side, zero API calls)
       ↓
POST /api/grade    ← Call #2
  → Grade all answers + generate full review in one shot
  → Returns: score, per-question feedback, study tips
```

No streaming. No chat history. No database. Fully stateless.

---

## Production Shipping

### Option A — Render.com Starter Deployment
- Deploy Flask as a web service
- Starter services may spin down after inactivity
- Check current RAM and runtime constraints before launch
- How: push to GitHub → connect Render → set start command `python app.py`

### Option B — Recommended: Railway.app
- **Cost: ~$5/month** (hobby plan, always on)
- No cold starts, easy env vars, automatic deploys from GitHub
- Add `Procfile`: `web: python app.py`

### Option C — VPS: Hetzner CX11
- **Cost: €4.15/month** (~$4.50)
- Full control, no vendor lock-in
- Run with gunicorn: `pip install gunicorn && gunicorn app:app -w 2 -b 0.0.0.0:5000`
- Add nginx reverse proxy + certbot for HTTPS

### Option D — Serverless: Vercel (with adapter)
- Requires refactoring Flask to use `vercel-wsgi` adapter
- **Cost: $0** on hobby tier
- Not recommended unless you want the complexity

---

## Production Challenges

### 1. Large PDFs
- Large PDFs (50+ pages) can exceed model context windows
- **Fix**: Add server-side PDF text extraction with `pypdf2` or `pdfplumber`
  and truncate intelligently (first N pages, or key sections)

### 2. API Throughput
- Pollinations throughput can vary by provider conditions
- **Fix**: Add request queuing + retry logic with exponential backoff
- Or: switch to OpenAI API (~$0.002 per quiz session)

### 3. Scanned PDFs
- Base64 of a scanned PDF = images, not text → AI can't read it
- **Fix**: Add OCR preprocessing with `pytesseract` before sending

### 4. Cold Starts
- First request after idle = 20-30s wait
- **Fix**: Add a `/api/ping` health check + frontend warming call on load

### 5. No Auth / Abuse Protection
- Anyone can hit your API endpoints without authentication
- **Fix**: Add request throttling (`flask-limiter`), or simple API key in header

### 6. Cost Estimate (if switching to OpenAI GPT-4o)
- Average quiz session ≈ 3000 tokens in + 1500 out = ~$0.015/session
- 1000 sessions/month ≈ $15/month AI costs
- Pollinations cost depends on the provider terms in effect when deployed

---

## File Structure for Production

```
quizforge/
├── app.py              ← Flask app + all API logic
├── requirements.txt    ← Python deps
├── Procfile            ← For Railway/Heroku: web: gunicorn app:app
├── .env                ← API keys (never commit)
├── .gitignore          ← include: venv/, __pycache__/, .env
├── README.md
└── static/
    └── index.html      ← Full frontend (self-contained)
```

---

## .gitignore
```
venv/
__pycache__/
*.pyc
.env
*.pdf
```

---

## Quick Test Checklist
- [ ] `python app.py` starts without errors
- [ ] http://localhost:5000 loads the UI
- [ ] Upload a small PDF (1-3 pages) first
- [ ] Difficulty buttons visually change color
- [ ] Timer toggle shows/hides minutes input
- [ ] Loading overlay appears during generation
- [ ] Questions render correctly (MCQ, T/F, Open)
- [ ] Answers save on click (selected state)
- [ ] Submit → results screen shows score + reviews
- [ ] Retry and New Document buttons work
