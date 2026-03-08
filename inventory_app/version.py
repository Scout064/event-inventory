import requests
import json
from pathlib import Path

GITHUB_OWNER = "Scout064"
GITHUB_REPO = "event-inventory"

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


def get_curret_version():
    path = Path("version.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
