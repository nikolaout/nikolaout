"""Refresh the generated public pull-request list in the profile README."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_URL = "https://api.github.com"
MAX_PULL_REQUESTS = 5
START_MARKER = "<!-- PR_HISTORY_START -->"
END_MARKER = "<!-- PR_HISTORY_END -->"


def fetch_json(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nikolaout-profile-pr-history",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API returned HTTP {error.code} for {url}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the GitHub API: {error.reason}") from error


def escape_markdown(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


def pull_request_status(pull_request: dict) -> tuple[str, str]:
    if pull_request.get("merged_at"):
        return "✅", "merged"
    if pull_request["state"] == "open":
        return "🟢", "open"
    return "⚪", "closed"


def render_history(username: str) -> str:
    query = quote(f"author:{username} is:pr", safe="")
    search = fetch_json(
        f"{API_URL}/search/issues?q={query}&sort=updated&order=desc&per_page={MAX_PULL_REQUESTS}"
    )

    entries: list[str] = []
    for issue in search.get("items", []):
        pull_url = issue.get("pull_request", {}).get("url")
        if not pull_url:
            continue

        pull_request = fetch_json(pull_url)
        icon, status = pull_request_status(pull_request)
        repository = pull_request["base"]["repo"]["full_name"]
        title = escape_markdown(pull_request["title"])
        entries.append(
            f"- {icon} [{title}]({pull_request['html_url']}) — `{repository}` · {status}"
        )

    if not entries:
        entries.append("_No public pull requests found yet._")

    search_query = quote(f"author:{username} is:pr", safe="")
    search_url = f"https://github.com/search?q={search_query}&type=pullrequests"
    return "\n".join(entries + ["", f"[View all pull requests]({search_url})"])


def update_readme(content: str, history: str) -> str:
    pattern = re.compile(
        rf"({re.escape(START_MARKER)}\n).*?(\n{re.escape(END_MARKER)})", re.DOTALL
    )
    updated, replacements = pattern.subn(rf"\g<1>{history}\g<2>", content, count=1)
    if replacements != 1:
        raise RuntimeError("PR history markers were not found exactly once in README.md")
    return updated


def main() -> int:
    username = os.environ.get("PR_HISTORY_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not username:
        raise RuntimeError("Set PR_HISTORY_USERNAME or GITHUB_REPOSITORY_OWNER")

    readme_path = Path(__file__).resolve().parents[2] / "README.md"
    current_content = readme_path.read_text(encoding="utf-8")
    updated_content = update_readme(current_content, render_history(username))

    if updated_content == current_content:
        print("PR history is already current.")
        return 0

    readme_path.write_text(updated_content, encoding="utf-8")
    print("Updated PR history in README.md.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
