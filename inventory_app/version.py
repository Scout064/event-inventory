import requests
import json
import os
import time
from packaging import version

GITHUB_OWNER = "Scout064"
GITHUB_REPO = "event-inventory"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_PATH = os.path.join(APP_DIR, "version.json")

# 1-Hour TTL Cache to prevent GitHub API rate limiting
_github_cache = {"releases": None, "timestamp": 0}
CACHE_TTL = 3600


def get_github_releases():
    if time.time() - _github_cache["timestamp"] < CACHE_TTL and _github_cache["releases"] is not None:
        return _github_cache["releases"]

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    try:
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
        _github_cache["releases"] = releases
        _github_cache["timestamp"] = time.time()
        return releases
    except Exception as e:
        print(f"GitHub API Error: {e}")
        return _github_cache["releases"] or []


def get_stable_releases(limit=1):
    releases = get_github_releases()
    stable_releases = [r for r in releases if not r["prerelease"] and not r["draft"]]
    stable_releases.sort(key=lambda r: r["published"], reverse=True)
    return stable_releases[:limit]


def get_beta_releases(limit=5):
    releases = get_github_releases()
    beta_releases = [r for r in releases if r["prerelease"] and not r["draft"]]
    beta_releases.sort(key=lambda r: r["published"], reverse=True)
    return beta_releases[:limit]


def get_current_version():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("version", "v0.0.0")
    except Exception:
        return "v0.0.0"


def get_build_date():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("buildDate", "Unknown")
        if date_str != "Unknown":
            from datetime import datetime
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%B %d, %Y at %H:%M")
        return date_str
    except Exception:
        return "Unknown"


def get_version_status():
    """Compares current version against GitHub to trigger UI alerts."""
    current_str = get_current_version()
    status = {
        "current": current_str,
        "is_alpha": "alpha" in current_str.lower(),
        "is_beta": "beta" in current_str.lower(),
        "update_available": False,
        "latest_stable": None
    }
    try:
        stable_releases = get_stable_releases(limit=1)
        if stable_releases:
            latest_stable_str = stable_releases[0]["version"]
            status["latest_stable"] = latest_stable_str
            # Use packaging.version to accurately compare semantic versions (e.g. 1.2.0 > 1.2.0-alpha)
            curr_v = version.parse(current_str)
            latest_v = version.parse(latest_stable_str)
            if latest_v > curr_v:
                status["update_available"] = True
    except Exception as e:
        print(f"Error checking version status: {e}")
    return status
