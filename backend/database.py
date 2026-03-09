import sqlite3
import json
from datetime import datetime

DB_PATH = "football.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            competition TEXT NOT NULL,
            match_date TEXT NOT NULL,
            status TEXT DEFAULT 'SCHEDULED',
            home_score INTEGER,
            away_score INTEGER,
            raw_data TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT NOT NULL,
            competition TEXT,
            stats_json TEXT NOT NULL,
            source TEXT,
            scraped_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            prediction TEXT NOT NULL,
            confidence TEXT,
            reasoning TEXT,
            actual_result TEXT,
            was_correct INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# --- Matches ---

def upsert_match(match: dict):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO matches (id, home_team, away_team, competition, match_date, status, home_score, away_score, raw_data)
        VALUES (:id, :home_team, :away_team, :competition, :match_date, :status, :home_score, :away_score, :raw_data)
        ON CONFLICT(id) DO UPDATE SET
            status=excluded.status,
            home_score=excluded.home_score,
            away_score=excluded.away_score,
            fetched_at=CURRENT_TIMESTAMP
    """, match)
    conn.commit()
    conn.close()


def get_upcoming_matches(limit: int = 20) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM matches
        WHERE status IN ('SCHEDULED', 'TIMED', 'IN_PLAY', 'LIVE')
        ORDER BY match_date ASC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_recent_results(limit: int = 20) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM matches
        WHERE status = 'FINISHED'
        ORDER BY match_date DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_matches_for_teams(team_a: str, team_b: str) -> list:
    conn = get_connection()
    c = conn.cursor()
    like_a = f"%{team_a}%"
    like_b = f"%{team_b}%"
    c.execute("""
        SELECT * FROM matches
        WHERE (home_team LIKE ? OR away_team LIKE ?)
           OR (home_team LIKE ? OR away_team LIKE ?)
        ORDER BY match_date DESC
        LIMIT 20
    """, (like_a, like_a, like_b, like_b))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# --- Team Stats ---

def save_team_stats(team: str, competition: str, stats: dict, source: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO team_stats (team, competition, stats_json, source)
        VALUES (?, ?, ?, ?)
    """, (team, competition, json.dumps(stats), source))
    conn.commit()
    conn.close()


def get_team_stats(team: str) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM team_stats
        WHERE team LIKE ?
        ORDER BY scraped_at DESC
        LIMIT 5
    """, (f"%{team}%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# --- Predictions ---

def save_prediction(data: dict) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO predictions (match_id, home_team, away_team, prediction, confidence, reasoning)
        VALUES (:match_id, :home_team, :away_team, :prediction, :confidence, :reasoning)
    """, data)
    pred_id = c.lastrowid
    conn.commit()
    conn.close()
    return pred_id


def get_recent_predictions(limit: int = 10) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_prediction_accuracy() -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN was_correct IS NOT NULL THEN 1 ELSE 0 END) as evaluated
        FROM predictions
    """)
    row = dict(c.fetchone())
    conn.close()
    evaluated = row["evaluated"] or 0
    correct = row["correct"] or 0
    total = row["total"] or 0
    accuracy = round((correct / evaluated * 100), 1) if evaluated > 0 else None
    return {
        "total": total,
        "evaluated": evaluated,
        "correct": correct,
        "accuracy": accuracy,
    }


# --- Chat History ---

def save_chat_message(role: str, content: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()


def get_chat_history(limit: int = 20) -> list:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT role, content FROM chat_history
        ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return list(reversed(rows))