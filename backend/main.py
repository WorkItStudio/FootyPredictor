from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

from database import init_db, get_upcoming_matches, get_recent_results, get_recent_predictions, get_prediction_accuracy
from football_api import fetch_upcoming_matches, fetch_recent_results, fetch_standings, fetch_team_matches
from scraper import scrape_team_stats
from ai import chat, summarise_data_for_chat

app = FastAPI(title="Football Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    print("[startup] Database initialised.")


# ── Request Models ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    team_a: str = ""
    team_b: str = ""

class ScrapeRequest(BaseModel):
    team: str


# ── Routes ──────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "Football Predictor API is running."}


@app.get("/matches/upcoming")
def upcoming_matches():
    """Return upcoming matches from DB. Fetches fresh data if DB is empty."""
    matches = get_upcoming_matches(20)
    if not matches:
        fetch_upcoming_matches()
        matches = get_upcoming_matches(20)
    return {"matches": matches, "count": len(matches)}


@app.get("/matches/results")
def recent_results():
    """Return recent finished matches from DB."""
    results = get_recent_results(20)
    if not results:
        fetch_recent_results()
        results = get_recent_results(20)
    return {"results": results, "count": len(results)}


@app.post("/matches/refresh")
def refresh_matches():
    """Force-fetch latest matches and results from football-data.org."""
    upcoming = fetch_upcoming_matches()
    results = fetch_recent_results()
    return {
        "message": "Data refreshed successfully.",
        "upcoming_fetched": len(upcoming),
        "results_fetched": len(results),
    }


@app.get("/standings/{competition_code}")
def standings(competition_code: str = "PL"):
    """Get current standings for a competition (PL, CL, PD, SA, BL1, FL1)."""
    data = fetch_standings(competition_code.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"Could not fetch standings for {competition_code}")
    return data


@app.get("/team/{team_name}/matches")
def team_matches(team_name: str):
    """Fetch and return all recent + upcoming matches for a specific team."""
    matches = fetch_team_matches(team_name)
    return {"team": team_name, "matches": matches, "count": len(matches)}


@app.post("/scrape")
def scrape(req: ScrapeRequest):
    """Scrape detailed stats for a team from FBref and store in DB."""
    if not req.team.strip():
        raise HTTPException(status_code=400, detail="Team name is required.")
    stats = scrape_team_stats(req.team)
    if not stats:
        return {"success": False, "message": f"Could not scrape stats for '{req.team}'. Team may not be found on FBref."}
    return {"success": True, "team": req.team, "stats": stats}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    """Send a message to the AI analyst. Optionally include team names for richer context."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        result = chat(req.message, team_a=req.team_a, team_b=req.team_b)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/summary")
def data_summary():
    """Ask the AI to summarise what data is currently stored."""
    summary = summarise_data_for_chat()
    return {"summary": summary}


@app.get("/predictions")
def predictions():
    """Return recent predictions and overall accuracy stats."""
    preds = get_recent_predictions(20)
    accuracy = get_prediction_accuracy()
    return {"predictions": preds, "accuracy": accuracy}


@app.get("/health")
def health():
    football_key = bool(os.getenv("FOOTBALL_API_KEY"))
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "status": "ok",
        "football_api_key_set": football_key,
        "anthropic_api_key_set": anthropic_key,
    }