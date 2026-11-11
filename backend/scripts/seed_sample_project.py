"""
Fills the local database with one realistic sample project, for trying features by hand.

    cd backend && source .venv/bin/activate && python -m scripts.seed_sample_project

It goes through the real API (in-process, no server needed), so every write takes the same
path a browser would: validation, permissions, activity log, live-update events. Safe to
run twice: it stops if the sample users already exist. Local development only; it creates
accounts with a known password.

Sign in afterwards as priya.sample@example.com / samplepass123 (also arjun.*, sara.*).
"""

import asyncio
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient

from app.main import app

PASSWORD = "samplepass123"
USERS = {
    "priya": ("priya.sample@example.com", "Priya Sharma"),
    "arjun": ("arjun.sample@example.com", "Arjun Mehta"),
    "sara": ("sara.sample@example.com", "Sara Khan"),
}
LABELS = {
    "frontend": "#3b82f6",
    "backend": "#10b981",
    "bug": "#ef4444",
    "payments": "#f59e0b",
}


def _in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# The long thread: enough back-and-forth that a summary is genuinely useful.
GATEWAY_THREAD = [
    ("sara", "Support got 14 tickets this week about checkout spinning forever and then "
             "showing 'payment failed'. All of them were card payments, none were UPI."),
    ("arjun", "Logs show the gateway call taking 28-35 seconds on those requests. Our HTTP "
              "client times out at 30s, so we mark the order failed even when the bank "
              "eventually approves it."),
    ("priya", "So some of these customers were actually charged? That's the real problem."),
    ("arjun", "Yes, I found 6 orders where the gateway shows 'captured' but our database "
              "says 'failed'. Those customers paid and got nothing."),
    ("sara", "I'll refund those 6 manually today and email them an apology."),
    ("priya", "Thanks Sara. Arjun, is the slowness on our side or theirs?"),
    ("arjun", "Theirs. Their status page shows degraded performance for card payments in "
              "the Mumbai region since Monday. Our own latency is normal."),
    ("priya", "We can't fix their outage, but we can stop losing orders. Options?"),
    ("arjun", "Two changes: raise our timeout to 60s, and stop treating a timeout as "
              "failure. Instead mark the order 'pending' and confirm it with the "
              "gateway's webhook, which arrives once the payment settles."),
    ("sara", "From the customer side, 'pending' needs a clear message, otherwise they'll "
             "retry and pay twice."),
    ("priya", "Agreed. Decision: Arjun does the timeout + webhook change this sprint, "
              "Sara writes the 'payment is processing' message, and we add a duplicate-"
              "payment check before allowing a retry."),
    ("arjun", "Webhook handler is up for review. Tested with the gateway's sandbox: a "
              "delayed approval now moves the order from pending to paid within seconds."),
]

ANALYTICS_THREAD = [
    ("priya", "We need checkout funnel numbers before the launch review. Which tool?"),
    ("sara", "Marketing already pays for one, but it only tracks page views, not steps."),
    ("arjun", "We could log our own events to Postgres: cart_viewed, address_entered, "
              "payment_started, payment_succeeded. Cheap and we own the data."),
    ("priya", "Do that for launch. We can revisit a proper tool next quarter."),
    ("arjun", "Event table and the four events are in. Dashboard query is next."),
]


async def main() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://seed") as api:
        login = await api.post(
            "/api/auth/login", json={"email": USERS["priya"][0], "password": PASSWORD}
        )
        if login.status_code == 200:
            print("Sample data already exists. Sign in as", USERS["priya"][0])
            return

        tokens = {}
        user_ids = {}
        for key, (email, name) in USERS.items():
            resp = await api.post(
                "/api/auth/register",
                json={"email": email, "password": PASSWORD, "full_name": name},
            )
            resp.raise_for_status()
            login = await api.post("/api/auth/login", json={"email": email, "password": PASSWORD})
            login.raise_for_status()
            tokens[key] = {"Authorization": f"Bearer {login.json()['access_token']}"}
            user_ids[key] = resp.json()["id"]

        owner = tokens["priya"]

        async def post(path: str, body: dict, as_user: str = "priya") -> dict:
            resp = await api.post(path, json=body, headers=tokens[as_user])
            resp.raise_for_status()
            return resp.json()

        org = await post("/api/organizations", {"name": "Northwind Retail"})
        workspace = await post(f"/api/organizations/{org['id']}/workspaces", {"name": "Product"})
        project = await post(
            f"/api/workspaces/{workspace['id']}/projects",
            {
                "name": "Checkout Revamp",
                "description": "Rebuild the checkout flow before the festive sale: guest "
                "checkout, faster payments, fewer failed orders.",
            },
        )
        pid = project["id"]
        for teammate in ("arjun", "sara"):
            email = USERS[teammate][0]
            await post(f"/api/workspaces/{workspace['id']}/members", {"email": email})
            await post(f"/api/projects/{pid}/members", {"email": email})

        labels = {
            name: (await post(f"/api/projects/{pid}/labels", {"name": name, "color": color}))[
                "id"
            ]
            for name, color in LABELS.items()
        }

        async def task(title, *, description=None, status="todo", priority="medium",
                       assignee=None, due_in=None, label_names=(), parent=None) -> dict:
            created = await post(
                f"/api/projects/{pid}/tasks",
                {
                    "title": title,
                    "description": description,
                    "status": status,
                    "priority": priority,
                    "assignee_id": user_ids[assignee] if assignee else None,
                    "due_date": _in_days(due_in) if due_in is not None else None,
                    "parent_task_id": parent,
                },
            )
            if label_names:
                resp = await api.patch(
                    f"/api/tasks/{created['id']}",
                    json={"label_ids": [labels[n] for n in label_names]},
                    headers=owner,
                )
                resp.raise_for_status()
            return created

        async def thread(task_id: str, messages: list[tuple[str, str]]) -> None:
            for author, body in messages:
                await post(f"/api/tasks/{task_id}/comments", {"body": body}, as_user=author)

        gateway = await task(
            "Payment gateway timeouts at checkout",
            description="Card payments intermittently fail after ~30s and the order is "
            "marked failed even when the bank approves it.",
            status="in_progress", priority="urgent", assignee="arjun", due_in=2,
            label_names=("backend", "payments", "bug"),
        )
        await thread(gateway["id"], GATEWAY_THREAD)

        guest = await task(
            "Guest checkout",
            description="Let customers buy without creating an account. Collect email and "
            "phone only; offer account creation after the order is placed.",
            status="in_progress", priority="high", assignee="sara", due_in=10,
            label_names=("frontend", "backend"),
        )
        await task("Email-only order lookup page", parent=guest["id"], assignee="sara")
        await task("Rate-limit guest orders per phone number", parent=guest["id"],
                   assignee="arjun")
        await task("Offer account creation on the confirmation page", parent=guest["id"],
                   status="done", assignee="sara")

        analytics = await task(
            "Checkout funnel analytics",
            description="Measure drop-off between cart, address, payment and success.",
            status="in_review", priority="medium", assignee="arjun", due_in=5,
            label_names=("backend",),
        )
        await thread(analytics["id"], ANALYTICS_THREAD)

        address = await task(
            "Address form rejects valid PIN codes",
            description="PIN codes starting with 0 are rejected by the validation regex.",
            status="done", priority="high", assignee="sara", label_names=("frontend", "bug"),
        )
        await thread(address["id"], [
            ("sara", "The regex assumed the first digit is 1-9. Fixed and added tests for "
                     "PIN codes starting with 0."),
            ("priya", "Thanks, verified on staging."),
        ])

        await task("Show delivery date estimate before payment", status="todo",
                   priority="medium", assignee="sara", due_in=14, label_names=("frontend",))
        await task("Save cards for returning customers",
                   description="Tokenised cards only; we never store card numbers.",
                   status="todo", priority="low", label_names=("payments", "backend"))
        await task("Load test checkout at 5x festive-sale traffic", status="todo",
                   priority="high", assignee="arjun", due_in=7, label_names=("backend",))
        await task("Write 'payment is processing' message", status="todo",
                   priority="high", assignee="sara", due_in=3, label_names=("frontend",))
        await task("Duplicate-payment check before retry", status="todo", priority="urgent",
                   assignee="arjun", due_in=4, label_names=("payments", "backend"))
        await task("Update refund policy page", status="done", priority="low",
                   assignee="priya")

        print("Created sample project 'Checkout Revamp' with 3 members, 13 tasks (3 of them "
              "subtasks) and comment threads.")
        print("Sign in as", USERS["priya"][0], "/", PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
