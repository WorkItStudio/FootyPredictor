# ⚽ Football Predictor — AI Match Analysis & Prediction

A chat-based AI football analyst that fetches real fixtures, scrapes stats, and predicts match outcomes using Claude.

---

## Project Structure

```
football-predictor/
├── backend/
│   ├── main.py          ← FastAPI app (all routes)
│   ├── database.py      ← SQLite (matches, stats, predictions, chat)
│   ├── football_api.py  ← football-data.org fetcher
│   ├── scraper.py       ← FBref stats scraper
│   ├── ai.py            ← Claude AI chat + prediction logic
│   ├── requirements.txt
│   └── .env.example     ← Copy to .env and fill in your keys
└── frontend/
    └── index.html       ← Open this in your browser
```

---

## Setup

### 1. Get API Keys

- **football-data.org** (free): https://www.football-data.org/client/register
- **Anthropic** (pay-as-you-go): https://console.anthropic.com → API Keys → Create Key

### 2. Configure Environment

```bash
cd backend
cp .env.example .env
# Edit .env and paste your two API keys
```

### 3. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Start the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 5. Open the Frontend

Just open `frontend/index.html` in your browser. No build step needed.

---

## Using the App

**Chat naturally:**
- "Predict Arsenal vs Chelsea this weekend"
- "What's Man City's form in the last 5 games?"
- "Who are the top scorers in the Premier League?"
- "Champions League predictions for this week"

**Set teams for richer predictions:**
- Type team names in the "Home team" / "Away team" boxes at the top
- The AI will include head-to-head data and team-specific stats

**Sidebar actions:**
- **Refresh Fixtures** — pulls latest upcoming matches from football-data.org
- **Data Summary** — shows what's stored in the database
- **Competition pills** — quick-ask about a specific league

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/matches/upcoming` | Upcoming fixtures |
| GET  | `/matches/results` | Recent results |
| POST | `/matches/refresh` | Force-fetch latest data |
| GET  | `/standings/{code}` | League table (PL, CL, PD, SA, BL1, FL1) |
| POST | `/scrape` | Scrape team stats from FBref |
| POST | `/chat` | Send message to AI analyst |
| GET  | `/predictions` | All saved predictions + accuracy |
| GET  | `/health` | Check API key status |

---

## Notes

- Data is stored locally in `football.db` (SQLite) — no cloud needed
- Predictions are auto-saved when the AI makes one
- Chat history persists across refreshes
- FBref scraping may be slow (3-5s) — only use for specific team deep-dives
