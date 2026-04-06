import os
import json
import re
import anthropic
from database import (
    get_upcoming_matches,
    get_recent_results,
    get_team_stats,
    get_matches_for_teams,
    save_prediction,
    get_recent_predictions,
    get_prediction_accuracy,
    save_chat_message,
    get_chat_history,
)

def get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


SYSTEM_PROMPT = """You are FootballGPT — a data-driven football prediction engine with live web search capability.

IMPORTANT RULES:
- Always use web search to find current match info, team news, injuries and recent form before predicting
- Search for the specific match first, then search for each team's recent form and news
- You MUST follow the exact output format below for every prediction — no exceptions
- Never fabricate stats or results — if you can't find data, say so clearly

WEB SEARCH USAGE:
- For any match prediction, search: "[Team A] vs [Team B] preview [current year]"
- Search for injuries: "[Team name] injuries suspensions [current month year]"
- Search for form: "[Team name] last 5 results [current year]"
- Always search before answering — never rely solely on provided context

PREDICTION FORMAT (every match prediction must use this exact structure):
---
MATCH: [Home Team] vs [Away Team]
COMPETITION: [Competition name]
PREDICTION: [Home Win / Draw / Away Win]
CONFIDENCE: [High / Medium / Low]
PREDICTED SCORE: [X-X]
REASONING: [3-4 sentences grounded in searched data. Cover: recent form, head-to-head, key injuries/absences, home advantage]
KEY FACTORS:
- [Factor 1]
- [Factor 2]
- [Factor 3]
DATA QUALITY: [Excellent / Good / Limited]
---

For non-prediction questions answer naturally. Always be factual and cite what you found."""


def _build_context() -> str:
    """Build a data context string injected into every request."""
    lines = ["=== LIVE DATA CONTEXT ===\n"]

    upcoming = get_upcoming_matches(20)
    if upcoming:
        lines.append("UPCOMING FIXTURES (next 14 days):")
        for m in upcoming[:20]:
            lines.append(f"  {m['match_date'][:10]} | {m['competition']} | {m['home_team']} vs {m['away_team']}")
        lines.append("")

    results = get_recent_results(20)
    if results:
        lines.append("RECENT RESULTS (last 7 days):")
        for m in results[:20]:
            lines.append(f"  {m['match_date'][:10]} | {m['competition']} | {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}")
        lines.append("")

    accuracy = get_prediction_accuracy()
    if accuracy.get("evaluated", 0) > 0:
        lines.append(f"PREDICTION TRACK RECORD: {accuracy['correct']}/{accuracy['evaluated']} correct ({accuracy['accuracy']}% accuracy)")
        lines.append("")

    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


def _build_team_context(team_a: str, team_b: str = "") -> str:
    """Build rich team-specific context from all stored data sources."""
    lines = ["\n=== TEAM-SPECIFIC DATA ===\n"]

    def format_team(name: str):
        team_lines = [f"--- {name.upper()} ---"]
        stats_rows = get_team_stats(name)

        if not stats_rows:
            team_lines.append("  No stored stats — prediction based on general knowledge only")
            return team_lines

        for row in stats_rows[:3]:
            source = row.get("source", "unknown")
            try:
                s = json.loads(row["stats_json"])
            except Exception:
                continue

            if source == "fbref":
                team_lines.append("  [FBref]")
                if s.get("form"):
                    team_lines.append("  Recent form (last 5):")
                    for f in s["form"][:5]:
                        team_lines.append(f"    {f.get('date','')} | {f.get('result','')} {f.get('score','')} vs {f.get('opponent','')} ({f.get('competition','')})")
                if s.get("shooting"):
                    sh = s["shooting"]
                    parts = []
                    if sh.get("xg"): parts.append(f"xG: {sh['xg']}")
                    if sh.get("goals"): parts.append(f"Goals: {sh['goals']}")
                    if sh.get("shots_on_target"): parts.append(f"SoT: {sh['shots_on_target']}")
                    if parts: team_lines.append(f"  Shooting — {', '.join(parts)}")
                if s.get("possession", {}).get("possession"):
                    team_lines.append(f"  Possession: {s['possession']['possession']}%")

            elif source == "transfermarkt":
                team_lines.append("  [Transfermarkt]")
                if s.get("squad_value"):
                    team_lines.append(f"  Squad value: {s['squad_value']}")
                if s.get("injuries"):
                    injured = ", ".join(p["player"] for p in s["injuries"][:5])
                    team_lines.append(f"  Injured/Suspended: {injured}")
                else:
                    team_lines.append("  No current injuries reported")

            elif source == "sofascore":
                team_lines.append("  [Sofascore]")
                if s.get("recent_matches"):
                    for m in s["recent_matches"][:5]:
                        score = f"{m.get('home_score','?')}-{m.get('away_score','?')}" if m.get("home_score") is not None else "TBD"
                        team_lines.append(f"    {m.get('home_team','')} {score} {m.get('away_team','')} ({m.get('competition','')})")

        return team_lines

    lines.extend(format_team(team_a))

    if team_b:
        lines.append("")
        lines.extend(format_team(team_b))

        # Head to head
        h2h = get_matches_for_teams(team_a, team_b)
        if h2h:
            lines.append(f"\n--- HEAD TO HEAD ---")
            for m in h2h[:5]:
                score = f"{m['home_score']}-{m['away_score']}" if m.get("home_score") is not None else "upcoming"
                lines.append(f"  {m['match_date'][:10]} | {m['home_team']} {score} {m['away_team']} ({m.get('competition','')})")

    lines.append("\n=== END TEAM DATA ===")
    return "\n".join(lines)


def _extract_and_save_prediction(reply: str, team_a: str, team_b: str) -> bool:
    """
    FIX 1: Reliably extract prediction from structured response and save it.
    Works with or without team inputs.
    """
    try:
        # Extract teams from MATCH line if not provided
        home = team_a
        away = team_b

        match_line = re.search(r"MATCH:\s*(.+?)\s*vs\s*(.+)", reply, re.IGNORECASE)
        if match_line and not home:
            home = match_line.group(1).strip()
        if match_line and not away:
            away = match_line.group(2).strip()

        # Extract prediction
        pred_match = re.search(r"PREDICTION:\s*(.+)", reply, re.IGNORECASE)
        if not pred_match:
            return False
        prediction = pred_match.group(1).strip()

        # Extract confidence
        conf_match = re.search(r"CONFIDENCE:\s*(High|Medium|Low)", reply, re.IGNORECASE)
        confidence = conf_match.group(1).strip() if conf_match else "Medium"

        # Extract predicted score
        score_match = re.search(r"PREDICTED SCORE:\s*(.+)", reply, re.IGNORECASE)
        predicted_score = score_match.group(1).strip() if score_match else ""

        full_reasoning = f"{predicted_score}\n{reply}" if predicted_score else reply

        save_prediction({
            "match_id": None,
            "home_team": home or "Unknown",
            "away_team": away or "Unknown",
            "prediction": prediction,
            "confidence": confidence,
            "reasoning": full_reasoning,
        })
        return True

    except Exception as e:
        print(f"[ai] Could not save prediction: {e}")
        return False


def _is_prediction_request(message: str) -> bool:
    """Detect if the user is asking for a match prediction."""
    keywords = ["predict", "vs", "versus", "win", "who will", "going to win",
                "match", "game", "fixture", "odds", "chance", "preview"]
    message_lower = message.lower()
    return any(k in message_lower for k in keywords)


def chat(user_message: str, team_a: str = "", team_b: str = "") -> dict:
    """
    Send a message to Claude with full data context.
    Returns {"reply": str, "prediction_saved": bool}
    """
    save_chat_message("user", user_message)

    base_context = _build_context()

    # FIX 3: Always include team context if teams provided,
    # also try to extract teams from the message itself
    extracted_a = team_a
    extracted_b = team_b

    if not extracted_a:
        # Try to extract team names from "X vs Y" pattern in message
        vs_match = re.search(r"([A-Z][a-zA-Z\s]+?)\s+vs\.?\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|in|at|,)", user_message)
        if vs_match:
            extracted_a = vs_match.group(1).strip()
            extracted_b = vs_match.group(2).strip()

    team_context = _build_team_context(extracted_a, extracted_b) if extracted_a else ""
    full_context = base_context + team_context

    # Include match teams explicitly in the user message if provided
    team_hint = ""
    if extracted_a:
        team_hint = f"\n[Teams for this prediction: HOME = {extracted_a} | AWAY = {extracted_b or 'TBD'}]"

    # Build messages — exclude system context from history to keep it clean
    history = get_chat_history(limit=6)
    messages = []
    for msg in history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"{full_context}{team_hint}\n\nUser: {user_message}"
    })

    # temperature=0 for consistency + web_search for live real-time data
    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    # Extract text blocks — response may contain tool_use blocks alongside text
    reply = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            reply += block.text
    save_chat_message("assistant", reply)

    # FIX 1: Save prediction reliably using structured extraction
    prediction_saved = False
    if "PREDICTION:" in reply:
        prediction_saved = _extract_and_save_prediction(reply, extracted_a, extracted_b)

    return {"reply": reply, "prediction_saved": prediction_saved}


def summarise_data_for_chat() -> str:
    """Return a plain-text summary of what data is currently stored."""
    upcoming = get_upcoming_matches(5)
    results = get_recent_results(5)
    preds = get_recent_predictions(5)
    accuracy = get_prediction_accuracy()

    lines = ["Here's a summary of the data I currently have:\n"]

    if upcoming:
        lines.append(f"📅 {len(upcoming)} upcoming fixtures stored (showing 5):")
        for m in upcoming[:5]:
            lines.append(f"  • {m['match_date'][:10]} — {m['home_team']} vs {m['away_team']} ({m['competition']})")
    else:
        lines.append("📅 No upcoming fixtures stored yet. Try refreshing fixtures first.")

    if results:
        lines.append(f"\n✅ {len(results)} recent results stored (showing 5):")
        for m in results[:5]:
            lines.append(f"  • {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}")
    else:
        lines.append("\n✅ No results stored yet.")

    if preds:
        lines.append(f"\n🔮 {len(preds)} predictions saved:")
        for p in preds[:5]:
            lines.append(f"  • {p['home_team']} vs {p['away_team']}: {p['prediction']} ({p['confidence']} confidence)")

    if accuracy.get("evaluated", 0) > 0:
        lines.append(f"\n📊 Accuracy: {accuracy['correct']}/{accuracy['evaluated']} ({accuracy['accuracy']}%)")
    else:
        lines.append(f"\n📊 Predictions made: {accuracy.get('total', 0)} (none evaluated yet)")

    return "\n".join(lines)