import re

# @-mentions written as the mentioned user's email, e.g. "cc @alice@example.com" —
# this project has no separate @username field on User, so email is the only
# identifier a mention can unambiguously resolve to a specific account.
_MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")


def extract_mentioned_emails(body: str) -> list[str]:
    """Returns unique mentioned emails, in first-seen order."""
    seen: dict[str, None] = {}
    for match in _MENTION_RE.finditer(body):
        seen.setdefault(match.group(1), None)
    return list(seen)
