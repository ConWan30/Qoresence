"""Publish docs/discussions/*.md to GitHub Discussions.

Requires GitHub Discussions to be enabled for the repository.
Run with: python scripts/publish_discussions.py
"""

import json
import os
import re
import urllib.request
from pathlib import Path

REPO = os.environ.get("GH_REPO", "ConWan30/Qoresence")
REPO_ID = os.environ.get("GH_REPO_ID")
CATEGORY = os.environ.get("GH_DISCUSSION_CATEGORY", "Announcements")


def get_token() -> str:
    token = os.environ.get("GH_TOKEN")
    if not token:
        import subprocess

        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    return token


def get_repo_id(owner: str, repo: str, token: str) -> str:
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) { id }
    }
    """
    return _graphql(query, {"owner": owner, "repo": repo}, token)["data"]["repository"]["id"]


def get_category_id(repo_id: str, category: str, token: str) -> str:
    query = """
    query($repoId: ID!) {
      node(id: $repoId) {
        ... on Repository {
          discussionCategories(first: 20) {
            nodes { id name }
          }
        }
      }
    }
    """
    cats = _graphql(query, {"repoId": repo_id}, token)["data"]["node"]["discussionCategories"][
        "nodes"
    ]
    for c in cats:
        if c["name"].lower() == category.lower():
            return c["id"]
    raise RuntimeError(
        f"Discussion category {category!r} not found. Options: {[c['name'] for c in cats]}"
    )


def _graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def create_discussion(repo_id: str, category_id: str, title: str, body: str, token: str) -> str:
    query = """
    mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
      createDiscussion(input: {repositoryId: $repositoryId, categoryId: $categoryId, title: $title, body: $body}) {
        discussion { id url }
      }
    }
    """
    data = _graphql(
        query,
        {"repositoryId": repo_id, "categoryId": category_id, "title": title, "body": body},
        token,
    )
    return data["data"]["createDiscussion"]["discussion"]["url"]


def strip_front_matter(text: str) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        return m.group(2).strip()
    return text.strip()


def main() -> None:
    token = get_token()
    owner, repo = REPO.split("/")
    repo_id = REPO_ID or get_repo_id(owner, repo, token)
    cat_id = get_category_id(repo_id, CATEGORY, token)

    for path in sorted(Path("docs/discussions").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        body = strip_front_matter(text)
        title_match = re.search(r'title:\s*"([^"]+)"', text)
        title = title_match.group(1) if title_match else path.stem
        url = create_discussion(repo_id, cat_id, title, body, token)
        print(f"Published: {title} -> {url}")


if __name__ == "__main__":
    main()
