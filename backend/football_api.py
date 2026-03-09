import os
import requests
from datetime import datetime, timedelta
from database import upsert_match

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
BASE_URL = "https://api.football-data.org/v4"

# Competitions we care about
COMPETITIONS = {
    "PL":  "Premier League",
    "CL":  "Champions League",
    "PD":  "La Liga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
}

def _headers():
    return {"X-Auth-Token": FOOTBALL_API_KEY}


def _parse_match(m: dict, competition_name: str) -> dict:
    score = m.get("score", {})
    full = score.get("fullTime", {})
    return {
        "id": str(m["id"]),
        "home_team": m["homeTeam"]["name"],
        "away_team": m["awayTeam"]["name"],
        "competition": competition_name,
        "match_date": m.get("utcDate", ""),
        "status": m.get("status", "SCHEDULED"),
        "home_score": full.get("home"),
        "away_score": full.get("away"),
        "raw_data": str(m),
    }


def fetch_upcoming_matches() -> list:
    """Fetch upcoming matches for all tracked competitions and store in DB."""
    today = datetime.utcnow().date()
    date_to = today + timedelta(days=14)
    results = []

    for code, name in COMPETITIONS.items():
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = {
                "dateFrom": str(today),
                "dateTo": str(date_to),
                "status": "SCHEDULED,TIMED",
            }
            resp = requests.get(url, headers=_headers(), params=params, timeout=10)
            if resp.status_code != 200:
                print(f"[football_api] {code} returned {resp.status_code}: {resp.text[:200]}")
                continue

            matches = resp.json().get("matches", [])
            for m in matches:
                parsed = _parse_match(m, name)
                upsert_match(parsed)
                results.append(parsed)

        except Exception as e:
            print(f"[football_api] Error fetching {code}: {e}")

    return results


def fetch_recent_results() -> list:
    """Fetch finished matches from the last 7 days."""
    today = datetime.utcnow().date()
    date_from = today - timedelta(days=7)
    results = []

    for code, name in COMPETITIONS.items():
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = {
                "dateFrom": str(date_from),
                "dateTo": str(today),
                "status": "FINISHED",
            }
            resp = requests.get(url, headers=_headers(), params=params, timeout=10)
            if resp.status_code != 200:
                continue

            matches = resp.json().get("matches", [])
            for m in matches:
                parsed = _parse_match(m, name)
                upsert_match(parsed)
                results.append(parsed)

        except Exception as e:
            print(f"[football_api] Error fetching results for {code}: {e}")

    return results


def fetch_team_matches(team_name: str) -> list:
    """Search for a team and fetch their recent + upcoming matches."""
    try:
        # Search for team
        resp = requests.get(
            f"{BASE_URL}/teams",
            headers=_headers(),
            params={"name": team_name},
            timeout=10
        )
        if resp.status_code != 200:
            return []

        teams = resp.json().get("teams", [])
        if not teams:
            return []

        team_id = teams[0]["id"]
        today = datetime.utcnow().date()
        date_from = today - timedelta(days=30)
        date_to = today + timedelta(days=14)

        resp2 = requests.get(
            f"{BASE_URL}/teams/{team_id}/matches",
            headers=_headers(),
            params={"dateFrom": str(date_from), "dateTo": str(date_to)},
            timeout=10
        )
        if resp2.status_code != 200:
            return []

        matches = resp2.json().get("matches", [])
        results = []
        for m in matches:
            comp_name = m.get("competition", {}).get("name", "Unknown")
            parsed = _parse_match(m, comp_name)
            upsert_match(parsed)
            results.append(parsed)

        return results

    except Exception as e:
        print(f"[football_api] Error fetching team matches for {team_name}: {e}")
        return []


def fetch_standings(competition_code: str = "PL") -> dict:
    """Fetch current standings for a competition."""
    try:
        resp = requests.get(
            f"{BASE_URL}/competitions/{competition_code}/standings",
            headers=_headers(),
            timeout=10
        )
        if resp.status_code != 200:
            return {}

        data = resp.json()
        standings = data.get("standings", [])
        total_table = next((s for s in standings if s.get("type") == "TOTAL"), None)
        if not total_table:
            return {}

        return {
            "competition": data.get("competition", {}).get("name", competition_code),
            "season": data.get("season", {}).get("startDate", ""),
            "table": [
                {
                    "position": row["position"],
                    "team": row["team"]["name"],
                    "played": row["playedGames"],
                    "won": row["won"],
                    "draw": row["draw"],
                    "lost": row["lost"],
                    "goals_for": row["goalsFor"],
                    "goals_against": row["goalsAgainst"],
                    "goal_diff": row["goalDifference"],
                    "points": row["points"],
                }
                for row in total_table.get("table", [])
            ]
        }
    except Exception as e:
        print(f"[football_api] Error fetching standings: {e}")
        return {}
