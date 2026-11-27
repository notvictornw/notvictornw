#!/usr/bin/env python3
"""Refresh the live repository-data block in README.md from the GitHub API."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

OWNER = os.environ.get("GH_OWNER", "notvictornw")
README = os.environ.get("README_PATH", "README.md")

# Only the projects that are actually presented in README.md.
REPOS: list[tuple[str, str]] = [
    ("PanarNW", "PanarNW"),
    ("notvictornw-site", "notvictornw-site"),
    ("PanarNW-Backup", "PanarNW-Backup"),
    ("PanarNW-Valorant", "PanarNW-Valorant"),
    ("apex", "apex"),
    ("Aiden (opencode-telegram-bot)", "opencode-telegram-bot"),
    ("Equicord-Themes-LOL", "Equicord-Themes-LOL"),
    ("NieworldAPI", "NieworldAPI"),
]

TOTAL_START = "<!-- METRICS:TOTAL:START -->"
TOTAL_END = "<!-- METRICS:TOTAL:END -->"
TABLE_START = "<!-- METRICS:START -->"
TABLE_END = "<!-- METRICS:END -->"


def request(path: str) -> tuple[Any, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "notvictornw-readme-metrics",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response), response.headers.get("Link", "")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API {path} failed: HTTP {exc.code}") from exc


def last_page(link_header: str) -> int | None:
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link_header)
    return int(match.group(1)) if match else None


def count_commits(repo: str) -> int:
    data, link = request(f"/repos/{OWNER}/{repo}/commits?per_page=1")
    return last_page(link) or len(data)


def count_releases(repo: str) -> int:
    data, link = request(f"/repos/{OWNER}/{repo}/releases?per_page=100")
    pages = last_page(link)
    if not pages:
        return len(data)
    last_data, _ = request(f"/repos/{OWNER}/{repo}/releases?per_page=100&page={pages}")
    return (pages - 1) * 100 + len(last_data)


def gather_rows() -> tuple[list[str], int]:
    rows: list[str] = []
    total = 0

    for label, repo in REPOS:
        meta, _ = request(f"/repos/{OWNER}/{repo}")
        commits = count_commits(repo)
        releases = count_releases(repo)
        total += commits

        pushed = str(meta.get("pushed_at", ""))[:10] or "—"
        license_info = meta.get("license")
        license_name = license_info["spdx_id"] if license_info else "none"
        if license_name == "NOASSERTION":
            license_name = "custom"
        visibility = "Private" if meta.get("private") else "Public"

        rows.append(
            f"| [{label}](https://github.com/{OWNER}/{repo}) "
            f"| {commits:,} | {releases} | {pushed} | {license_name} | {visibility} |"
        )

    rows.append("| bot-faccao | — | — | — | — | Local |")
    return rows, total


def replace_block(text: str, start: str, end: str, body: str) -> str:
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index < 0 or end_index < 0 or end_index <= start_index:
        raise RuntimeError(f"Missing or misordered markers: {start} / {end}")
    return f"{text[: start_index + len(start)]}\n{body.strip()}\n{text[end_index:]}"


def main() -> int:
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise RuntimeError(
            "GH_TOKEN is required: use a PAT that can read every tracked private repo"
        )
    rows, total = gather_rows()
    table = "\n".join(
        [
            "| Project | Commits | Releases | Last push | License | Visibility |",
            "|---|---:|---:|---|---|---|",
            *rows,
        ]
    )
    total_line = (
        f"**{total:,} commits across {len(REPOS)} tracked GitHub repositories** "
        "— auto-refreshed hourly from the GitHub API."
    )

    with open(README, encoding="utf-8", newline="") as handle:
        text = handle.read()

    text = replace_block(text, TABLE_START, TABLE_END, table)
    text = replace_block(text, TOTAL_START, TOTAL_END, total_line)

    temp_path = f"{README}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp_path, README)

    print(f"Updated {README}: {total:,} commits across {len(REPOS)} repos")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
