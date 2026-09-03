#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "projects.json"
OUTPUT = ROOT / "assets" / "signal.svg"
USER_AGENT = "parthganguly-profile-signal/1.0"
GH_TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")

def request_json(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

def probe_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            code = int(getattr(response, "status", 0) or 0)
            return "REACHABLE" if 200 <= code < 400 else "UNVERIFIED"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return "UNVERIFIED"

def parse_github_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None

def latest_release(owner: str, repo: str) -> tuple[str, str]:
    data = request_json(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
    if not isinstance(data, dict):
        return ("UNAVAILABLE", "UNVERIFIED")
    tag = str(data.get("tag_name") or "UNAVAILABLE").upper()
    state = "PUBLISHED" if data.get("draft") is False else "UNVERIFIED"
    return (tag, state)

def latest_public_activity(owner: str, repositories: list[dict]) -> tuple[str, str]:
    newest: tuple[datetime, str] | None = None
    for item in repositories:
        repo = item["repo"]
        label = item["label"]
        data = request_json(f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1")
        if not isinstance(data, list) or not data:
            continue
        commit = data[0].get("commit") or {}
        stamp = ((commit.get("committer") or {}).get("date")
                 or (commit.get("author") or {}).get("date"))
        when = parse_github_date(stamp)
        if not when:
            continue
        if newest is None or when > newest[0]:
            newest = (when, label)
    if newest is None:
        return ("UNAVAILABLE", "UNVERIFIED")
    when, label = newest
    return (f"{label.upper()} · {when.strftime('%d %b %Y').upper()}", "DEFAULT BRANCH")

def svg_text(x: float, y: float, value: str, cls: str) -> str:
    return f'<text x="{x:g}" y="{y:g}" class="{cls}">{escape(value)}</text>'

def render_signal(release: str, release_state: str, deploy_label: str, deploy_state: str,
                  activity: str, activity_state: str) -> str:
    rows = [
        ("RELEASE", f"POTATOCS {release}", release_state),
        ("DEPLOYMENT", deploy_label.upper(), deploy_state),
        ("PUBLIC ACTIVITY", activity, activity_state),
    ]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 230" role="img" aria-labelledby="title desc">',
        '<title id="title">Live engineering signal</title>',
        '<desc id="desc">Generated profile signal showing the latest PotatoCS release, Istakir deployment reachability, and the most recent curated public repository activity.</desc>',
        '<style>.bg{fill:#03070b}.line{stroke:#15324a}.soft{stroke:#0d2639}.label{fill:#f6b72e;font:700 11px Georgia,Times New Roman,serif;letter-spacing:1px}.value{fill:#f7fbfc;font:700 16px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.state{fill:#0de3f4;font:700 12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:1.3px}.state-muted{fill:#8eb8c7;font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:1.3px}.meta{fill:#8bdbe9;font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:1.8px}.foot{fill:#638595;font:10px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:1.2px}</style>',
        '<rect width="1200" height="230" rx="16" class="bg"/>',
        '<circle cx="28" cy="28" r="5" fill="#f6b72e"/>',
        '<circle cx="1150" cy="27" r="10" fill="none" stroke="#0de3f4" stroke-opacity=".22"/>',
        '<circle cx="1150" cy="27" r="4" fill="#0de3f4" fill-opacity=".8"/>',
        svg_text(46, 33, "LIVE SIGNAL / GENERATED FROM PUBLIC ENDPOINTS", "meta"),
        '<path d="M28 58H1172" class="line"/>',
    ]
    ys = [92, 143, 194]
    separators = [111, 162]
    for i, ((label, value, state), y) in enumerate(zip(rows, ys)):
        parts.append(svg_text(28, y, label, "label"))
        parts.append(svg_text(210, y, value, "value"))
        parts.append(svg_text(1000, y, state, "state" if state in {"PUBLISHED", "REACHABLE"} else "state-muted"))
        if i < len(separators):
            parts.append(f'<path d="M28 {separators[i]}H1172" class="soft"/>')
    parts.extend([
        svg_text(28, 218, "public signals only · private repositories are never queried by this workflow", "foot"),
        "</svg>",
    ])
    return "\n".join(parts) + "\n"

def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    owner = config["owner"]
    release, release_state = latest_release(owner, config["release_repository"])
    deploy = config["deployment"]
    deploy_state = probe_url(deploy["url"])
    activity, activity_state = latest_public_activity(owner, config["activity_repositories"])
    svg = render_signal(
        release=release,
        release_state=release_state,
        deploy_label=deploy["label"],
        deploy_state=deploy_state,
        activity=activity,
        activity_state=activity_state,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != svg:
        OUTPUT.write_text(svg, encoding="utf-8")

if __name__ == "__main__":
    main()
