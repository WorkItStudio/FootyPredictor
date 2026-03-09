import os
import json
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

SYSTEM_PROMPT = """You are FootballGPT — an expert football analyst and prediction engine specialising in European football (Premier League, Champions League, La Liga, Serie A, Bundesliga, Ligue 1).

You have access to real-time data including upcoming fixtures, recent results, team form, standings, and scraped statistics. This data will be injected into each message as context.

Your capabilities:
- Predict match outcomes with reasoned analysis (home win / draw / away win)
- Analyse team form, head-to-head records, and recent performances
- Discuss player impacts, tactical matchups, and competition context
- Answer general football questions with depth and confidence

Prediction format (use this when predicting a specific match):
- Start with a clear prediction: "PREDICTION: [Home Win / Draw / Away Win]"
- Confidence level: High / Medium / Low
- 3-4 sentences of reasoning grounded in the data provided

Always be honest about data limitations. If you don't have enough data for a confident prediction, say so clearly.
Keep responses concise but insightful. No fluff."""


def _build_context() -> str:
    """Build a data context string to inject into each AI request."""
    lines = ["=== LIVE DATA CONTEXT ===\n"]

    upcoming = get_upcoming_matches(10)
    if upcoming:
        lines.append("UPCOMING FIXTURES (next 14 days):")
        for m in upcoming[:10]:
            lines.append(f"  {m['match_date'][:10]} | {m['competition']} | {m['home_team']} vs {m['away_team']}")
        lines.append("")

    results = get_recent_results(10)
    if results:
        lines.append("RECENT RESULTS (last 7 days):")
        for m in results[:10]:
            lines.append(f"  {m['match_date'][:10]} | {m['competition']} | {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}")
        lines.append("")

    accuracy = get_prediction_accuracy()
    if accuracy.get("evaluated", 0) > 0:
        lines.append(f"MY PREDICTION TRACK RECORD: {accuracy['correct']}/{accuracy['evaluated']} correct ({accuracy['accuracy']}% accuracy)")
        lines.append("")

    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


def _build_team_context(team_a: str, team_b: str = "") -> str:
    """Build extra context for specific teams."""
    lines = []

    stats_a = get_team_stats(team_a)
    if stats_a:
        latest = stats_a[0]
        lines.append(f"\nSTATS for {team_a} (from {latest['source']}):")
        try:
            s = json.loads(latest["stats_json"])
            if s.get("form"):
                form_str = " | ".join(
                    f"{f['date']} {f['result']} {f['score']} vs {f['opponent']}"
                    for f in s["form"][:5]
                )
                lines.append(f"  Recent form: {form_str}")
        except Exception:
            pass

    if team_b:
        stats_b = get_team_stats(team_b)
        if stats_b:
            latest = stats_b[0]
            lines.append(f"\nSTATS for {team_b} (from {latest['source']}):")
            try:
                s = json.loads(latest["stats_json"])
                if s.get("form"):
                    form_str = " | ".join(
                        f"{f['date']} {f['result']} {f['score']} vs {f['opponent']}"
                        for f in s["form"][:5]
                    )
                    lines.append(f"  Recent form: {form_str}")
            except Exception:
                pass

        h2h = get_matches_for_teams(team_a, team_b)
        if h2h:
            lines.append(f"\nHEAD-TO-HEAD (recent):")
            for m in h2h[:5]:
                score = f"{m['home_score']}-{m['away_score']}" if m.get("home_score") is not None else "upcoming"
                lines.append(f"  {m['match_date'][:10]} | {m['home_team']} {score} {m['away_team']}")

    return "\n".join(lines)


def chat(user_message: str, team_a: str = "", team_b: str = "") -> dict:
    """
    Send a message to Claude with full data context.
    Returns {"reply": str, "prediction_saved": bool}
    """
    save_chat_message("user", user_message)

    history = get_chat_history(limit=10)
    base_context = _build_context()
    team_context = _build_team_context(team_a, team_b) if team_a else ""

    full_context = base_context + team_context

    messages = []
    for msg in history[:-1]:  # exclude the message we just saved
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"{full_context}\n\nUser question: {user_message}"
    })

    response = get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    reply = response.content[0].text
    save_chat_message("assistant", reply)

    # Auto-save prediction if detected
    prediction_saved = False
    if "PREDICTION:" in reply and team_a:
        try:
            pred_line = [l for l in reply.split("\n") if "PREDICTION:" in l][0]
            pred_value = pred_line.replace("PREDICTION:", "").strip()

            conf = "Medium"
            if "High" in reply:
                conf = "High"
            elif "Low" in reply:
                conf = "Low"

            save_prediction({
                "match_id": None,
                "home_team": team_a,
                "away_team": team_b or "Unknown",
                "prediction": pred_value,
                "confidence": conf,
                "reasoning": reply,
            })
            prediction_saved = True
        except Exception as e:
            print(f"[ai] Could not auto-save prediction: {e}")

    return {"reply": reply, "prediction_saved": prediction_saved}


def summarise_data_for_chat() -> str:
    """Return a plain-text summary of what data we currently have stored."""
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
        lines.append("📅 No upcoming fixtures stored yet. Try fetching matches first.")

    if results:
        lines.append(f"\n✅ {len(results)} recent results stored (showing 5):")
        for m in results[:5]:
            lines.append(f"  • {m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}")
    else:
        lines.append("\n✅ No results stored yet.")

    if preds:
        lines.append(f"\n🔮 {len(preds)} predictions made:")
        for p in preds[:5]:
            lines.append(f"  • {p['home_team']} vs {p['away_team']}: {p['prediction']} ({p['confidence']} confidence)")

    if accuracy.get("evaluated", 0) > 0:
        lines.append(f"\n📊 Accuracy: {accuracy['correct']}/{accuracy['evaluated']} ({accuracy['accuracy']}%)")

    return "\n".join(lines)
