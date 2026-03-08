"""Automatic GitHub issue reporter for the Minecraft Webhook integration."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import GITHUB_REPO_NAME, GITHUB_REPO_OWNER

_LOGGER = logging.getLogger(__name__)

# At most one issue per unique error per hour
RATE_LIMIT_SECONDS = 3600

# In-memory cache of hashes → last reported time
_reported_issues: dict[str, datetime] = {}


class GitHubIssueReporter:
    """Creates GitHub issues automatically when the integration hits an error."""

    def __init__(self, github_token: str) -> None:
        """Initialise with a personal access token."""
        self._token = github_token
        self._session: aiohttp.ClientSession | None = None
        self._headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Minecraft-Webhook-HA-Integration",
        }

    # ── Session management ────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a live aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _make_hash(self, error_type: str, error_message: str) -> str:
        """Short MD5 hash of error type + first line of message."""
        first_line = error_message.split("\n")[0][:100]
        return hashlib.md5(f"{error_type}:{first_line}".encode()).hexdigest()[:12]

    def _is_rate_limited(self, issue_hash: str) -> bool:
        """Return True if this hash was reported within the last hour."""
        last = _reported_issues.get(issue_hash)
        if last and datetime.now() - last < timedelta(seconds=RATE_LIMIT_SECONDS):
            return True
        return False

    async def _issue_already_exists(self, issue_hash: str) -> bool:
        """Return True if an open GitHub issue already contains this hash."""
        session = await self._get_session()
        url = (
            f"https://api.github.com/repos"
            f"/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues"
        )
        params = {"state": "open", "labels": "auto-reported", "per_page": 100}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    for issue in await resp.json():
                        if f"[{issue_hash}]" in issue.get("title", ""):
                            return True
        except Exception as exc:
            _LOGGER.debug("Could not check existing issues: %s", exc)
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    async def report_error(
        self,
        error_type: str,
        error_message: str,
        tb: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Create a GitHub issue for this error if it hasn't been reported yet.

        Returns True if an issue was created.
        """
        if not self._token:
            return False

        issue_hash = self._make_hash(error_type, error_message)

        if self._is_rate_limited(issue_hash):
            _LOGGER.debug("Skipping error report — rate limited (%s)", issue_hash)
            return False

        if await self._issue_already_exists(issue_hash):
            _LOGGER.debug("Skipping error report — issue already open (%s)", issue_hash)
            return False

        title = f"[Auto] [{issue_hash}] {error_type}: {error_message[:80]}"
        body  = self._build_body(error_type, error_message, tb, extra, issue_hash)

        created = await self._create_issue(title, body)
        if created:
            _reported_issues[issue_hash] = datetime.now()
            _LOGGER.info("Auto-reported error to GitHub: %s", title)

        return created

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_body(
        self,
        error_type: str,
        error_message: str,
        tb: str | None,
        extra: dict[str, Any] | None,
        issue_hash: str,
    ) -> str:
        body = f"""## Auto-Reported Error

**Error Type:** `{error_type}`
**Issue Hash:** `{issue_hash}`
**Reported At:** {datetime.now().isoformat()}

### Error Message
```
{error_message}
```
"""
        if tb:
            body += f"""
### Traceback
```python
{tb}
```
"""
        if extra:
            body += "\n### Additional Information\n"
            for k, v in extra.items():
                body += f"- **{k}:** {v}\n"

        body += """
---
*This issue was automatically created by the Minecraft Webhook HA integration.*
*If this is a duplicate or not a real bug, please close it.*
"""
        return body

    async def _create_issue(self, title: str, body: str) -> bool:
        """POST a new issue to GitHub. Returns True on success."""
        session = await self._get_session()
        url = (
            f"https://api.github.com/repos"
            f"/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues"
        )
        payload = {
            "title": title,
            "body": body,
            "labels": ["auto-reported", "bug"],
        }
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 201:
                    result = await resp.json()
                    _LOGGER.debug("Created GitHub issue #%s", result.get("number"))
                    return True
                err = await resp.text()
                _LOGGER.warning(
                    "GitHub issue creation failed (%s): %s", resp.status, err
                )
        except Exception as exc:
            _LOGGER.warning("Could not create GitHub issue: %s", exc)
        return False
