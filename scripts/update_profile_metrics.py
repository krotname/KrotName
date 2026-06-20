from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN = os.getenv("GITHUB_LOGIN", "krotname")
START_MARKER = "<!-- ACTIVITY-MIX:START -->"
END_MARKER = "<!-- ACTIVITY-MIX:END -->"


def github_graphql(query: str, variables: dict[str, str]) -> dict:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN or GH_TOKEN is required")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("errors"):
        raise SystemExit(json.dumps(payload["errors"], ensure_ascii=False, indent=2))

    return payload["data"]


def contribution_counts() -> tuple[dict[str, int], dt.date, dt.date]:
    end = dt.datetime.now(dt.timezone.utc).date()
    start = end - dt.timedelta(days=365)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
        }
      }
    }
    """
    data = github_graphql(
        query,
        {
            "login": LOGIN,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        },
    )
    collection = data["user"]["contributionsCollection"]
    counts = {
        "Commits": collection["totalCommitContributions"],
        "Pull requests": collection["totalPullRequestContributions"],
        "Code review": collection["totalPullRequestReviewContributions"],
        "Issues": collection["totalIssueContributions"],
    }
    return counts, start, end


def rounded_percentages(counts: dict[str, int]) -> dict[str, int]:
    total = sum(counts.values())
    if total == 0:
        return {name: 0 for name in counts}

    raw = {name: value * 100 / total for name, value in counts.items()}
    percentages = {name: math.floor(value) for name, value in raw.items()}
    remainder = 100 - sum(percentages.values())

    ranked = sorted(raw, key=lambda name: raw[name] - percentages[name], reverse=True)
    for name in ranked[:remainder]:
        percentages[name] += 1

    return percentages


def mermaid_block(intro: str, percentages: dict[str, int]) -> str:
    lines = [
        intro,
        "",
        "```mermaid",
        "pie showData",
        "    title GitHub activity",
    ]
    lines.extend(f'    "{name} {value}%" : {value}' for name, value in percentages.items())
    lines.append("```")
    return "\n".join(lines)


def replace_marked_block(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    replacement = f"{START_MARKER}\n{block}\n{END_MARKER}"
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        raise SystemExit(f"Expected exactly one dynamic block in {path}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def main() -> None:
    counts, start, end = contribution_counts()
    percentages = rounded_percentages(counts)
    total = sum(counts.values())

    replace_marked_block(
        ROOT / "README.md",
        mermaid_block(
            f"Последние 12 месяцев ({start.isoformat()} - {end.isoformat()}), "
            f"GitHub contribution totals: {total}.",
            percentages,
        ),
    )
    replace_marked_block(
        ROOT / "README.en.md",
        mermaid_block(
            f"Last 12 months ({start.isoformat()} - {end.isoformat()}), "
            f"GitHub contribution totals: {total}.",
            percentages,
        ),
    )


if __name__ == "__main__":
    main()
