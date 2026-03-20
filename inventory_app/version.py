import requests
import json
import os
from functools import lru_cache


GITHUB_OWNER = "Scout064"
GITHUB_REPO = "event-inventory"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_PATH = os.path.join(APP_DIR, "version.json")


@lru_cache(maxsize=1)
def get_github_releases():
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    releases = []
    for r in response.json():
        releases.append({
            "name": r["name"],
            "tag": r["tag_name"],
            "version": r["tag_name"],
            "prerelease": r["prerelease"],
            "draft": r["draft"],
            "published": r["published_at"],
            "url": r["html_url"]
        })
    return releases


def get_stable_releases(limit=1):
    releases = get_github_releases()
    # Filter only stable releases (prerelease=False and draft=False)
    stable_releases = [
        r for r in releases
        if not r["prerelease"] and not r["draft"]
    ]
    # Sort by published date descending (newest first)
    stable_releases.sort(key=lambda r: r["published"], reverse=True)
    # Return only the latest 'limit' releases
    return stable_releases[:limit]


def get_beta_releases(limit=5):
    releases = get_github_releases()
    beta_releases = [
        r for r in releases
        if r["prerelease"] and not r["draft"]
    ]
    # Optionally sort by published date descending
    beta_releases.sort(key=lambda r: r["published"], reverse=True)
    return beta_releases[:limit]


def get_current_version():
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["version"]


def get_build_date():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("buildDate", "Unknown")
        # Optional: Make the ISO date look nicer (e.g., "2026-03-15 20:00")
        if date_str != "Unknown":
            from datetime import datetime
            # Python 3.7+ can parse standard ISO 8601 strings natively
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%B %d, %Y at %H:%M")
        return date_str
    except Exception:
        return "Unknown"
