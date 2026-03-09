import requests
from bs4 import BeautifulSoup
from database import save_team_stats

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

FBREF_SEARCH = "https://fbref.com/search/search.fcgi"


def _clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def search_team_fbref(team_name: str) -> str | None:
    """Search FBref for a team and return their page URL."""
    try:
        resp = requests.get(
            FBREF_SEARCH,
            params={"search": team_name, "cat": "clubs"},
            headers=HEADERS,
            timeout=10
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        # Direct redirect means we landed on the team page
        if "/squads/" in resp.url:
            return resp.url

        # Look for search results
        results = soup.select("div.search-item-url")
        for r in results:
            link = r.find("a")
            if link and "/squads/" in link.get("href", ""):
                return "https://fbref.com" + link["href"]

        return None
    except Exception as e:
        print(f"[scraper] Search error for {team_name}: {e}")
        return None


def scrape_team_stats(team_name: str) -> dict:
    """
    Scrape key stats for a team from FBref.
    Returns a dict of stats or empty dict on failure.
    """
    try:
        team_url = search_team_fbref(team_name)
        if not team_url:
            print(f"[scraper] Could not find FBref page for {team_name}")
            return {}

        resp = requests.get(team_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        stats = {
            "team": team_name,
            "source_url": team_url,
            "form": [],
            "top_scorers": [],
            "season_summary": {},
        }

        # --- Recent form (last 5 results) ---
        results_table = soup.find("table", {"id": lambda x: x and "results" in str(x)})
        if results_table:
            rows = results_table.find("tbody").find_all("tr")[:5]
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 8:
                    stats["form"].append({
                        "date": _clean_text(cells[0].get_text()),
                        "competition": _clean_text(cells[2].get_text()),
                        "venue": _clean_text(cells[3].get_text()),
                        "result": _clean_text(cells[5].get_text()),
                        "score": _clean_text(cells[6].get_text()),
                        "opponent": _clean_text(cells[4].get_text()),
                    })

        # --- Season summary stats ---
        for table in soup.find_all("table"):
            caption = table.find("caption")
            if caption and "shooting" in caption.get_text().lower():
                tfoot = table.find("tfoot")
                if tfoot:
                    cells = tfoot.find_all("td")
                    if len(cells) >= 5:
                        stats["season_summary"]["goals"] = _clean_text(cells[0].get_text())
                        stats["season_summary"]["shots"] = _clean_text(cells[1].get_text())
                        stats["season_summary"]["shots_on_target"] = _clean_text(cells[2].get_text())
                break

        # Save to DB
        if stats["form"] or stats["season_summary"]:
            save_team_stats(
                team=team_name,
                competition="",
                stats=stats,
                source="fbref"
            )

        return stats

    except Exception as e:
        print(f"[scraper] Error scraping {team_name}: {e}")
        return {}


def get_quick_form(team_name: str, matches: list) -> str:
    """
    Build a form string (W/D/L) from stored match data.
    Uses match data already in the DB rather than scraping.
    """
    relevant = [
        m for m in matches
        if team_name.lower() in m.get("home_team", "").lower()
        or team_name.lower() in m.get("away_team", "").lower()
    ]
    relevant = [m for m in relevant if m.get("status") == "FINISHED"]
    relevant = sorted(relevant, key=lambda x: x.get("match_date", ""), reverse=True)[:5]

    form = []
    for m in relevant:
        h = m.get("home_score")
        a = m.get("away_score")
        if h is None or a is None:
            continue
        is_home = team_name.lower() in m.get("home_team", "").lower()
        if is_home:
            if h > a:
                form.append("W")
            elif h == a:
                form.append("D")
            else:
                form.append("L")
        else:
            if a > h:
                form.append("W")
            elif a == h:
                form.append("D")
            else:
                form.append("L")

    return " ".join(form) if form else "No recent data"
