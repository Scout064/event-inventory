import requests
import json
import os
from pathlib import Path
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


def get_current_version():
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["version"]
