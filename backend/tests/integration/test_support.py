"""M22: support tickets between a company and Duolink.

Company calls run at acme.localhost (and beta.localhost for isolation), admin calls at
admin.localhost, as the app's database role.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.tenancy import set_platform
from tests.conftest import login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)

pytestmark = pytest.mark.integration

HELP = "/api/v1/support/tickets"
ADMIN = "/api/v1/admin/support/tickets"
NEW = {
    "subject": "Cannot print the bill",
    "category": "printing",
    "priority": "high",
    "body": "The PDF comes out blank on the second shop.",
}


def counter(client, owner, username, password="counter-pass-123"):  # noqa: S107
    shop = client.get("/api/v1/locations", headers=owner).json()[0]["id"]
    made = client.post(
        "/api/v1/users",
        headers=owner,
        json={
            "username": username,
            "full_name": username.title(),
            "role": "counter",
            "password": password,
            "location_ids": [shop],
        },
    )
    assert made.status_code == 201, made.text
    return login(client, username, password, host="acme.localhost")


def raise_ticket(client, who, **changes):
    made = client.post(HELP, headers=who, json=NEW | changes)
    assert made.status_code == 201, made.text
    return made.json()


# ------------------------------------------------------------------ raising and reading


def test_a_counter_user_raises_a_ticket_duolink_replies_and_they_read_it(
    client, boss, helper, acme
):
    owner = owner_of(client)
    mala = counter(client, owner, "mala")
    ticket = raise_ticket(client, mala)
    assert ticket["number"] == "T-000001" and ticket["status"] == "open"
    assert ticket["raised_by_name"] == "Mala" and ticket["unread"] is False
    assert [m["author_kind"] for m in ticket["messages"]] == ["company_user"]

    # Duolink Support (the read-only role) replies: it is their job.
    answered = client.post(
        f"{ADMIN}/{ticket['id']}/reply", headers=helper, json={"body": "Try the new template."}
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "waiting_on_company"

    assert client.get(f"{HELP}/unread-count", headers=mala).json() == {"unread": 1}
    mine = client.get(HELP, headers=mala).json()["items"]
    assert [t["unread"] for t in mine] == [True]

    thread = client.get(f"{HELP}/{ticket['id']}", headers=mala).json()
    assert [m["author_kind"] for m in thread["messages"]] == ["company_user", "platform_admin"]
    assert thread["messages"][1]["author_name"] == "Duolink Support"  # not the admin's own name
    assert client.get(f"{HELP}/unread-count", headers=mala).json() == {"unread": 0}


def test_another_counter_user_does_not_see_it_but_the_owner_and_accountant_do(client, boss, acme):
    owner = owner_of(client)
    mala, ravi = counter(client, owner, "mala"), counter(client, owner, "kumar")
    ticket = raise_ticket(client, mala)

    assert client.get(HELP, headers=ravi).json()["items"] == []
    hidden = client.get(f"{HELP}/{ticket['id']}", headers=ravi)
    assert hidden.status_code == 404 and hidden.json()["code"] == "TICKET_NOT_FOUND"
    assert (
        client.post(f"{HELP}/{ticket['id']}/reply", headers=ravi, json={"body": "hi"}).status_code
        == 404
    )
    assert client.post(f"{HELP}/{ticket['id']}/close", headers=ravi).status_code == 404

    assert [t["number"] for t in client.get(HELP, headers=owner).json()["items"]] == ["T-000001"]
    accountant = client.post(
        "/api/v1/users",
        headers=owner,
        json={
            "username": "asha",
            "full_name": "Asha",
            "role": "accountant",
            "password": "asha-pass-12345",
        },
    )
    assert accountant.status_code == 201
    asha = login(client, "asha", "asha-pass-12345", host="acme.localhost")
    assert client.get(f"{HELP}/{ticket['id']}", headers=asha).status_code == 200


def test_numbers_count_up_per_company(client, boss, acme):
    owner = owner_of(client)
    numbers = [raise_ticket(client, owner)["number"] for _ in range(3)]
    assert numbers == ["T-000001", "T-000002", "T-000003"]
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="bela",
        owner_email="b@b.example",
    )
    beta = login(client, "bela", "ravi-pass-123", host="beta.localhost")
    assert raise_ticket(client, beta)["number"] == "T-000001"  # its own count


def test_company_a_tickets_never_show_in_company_b(client, boss, acme):
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="bela",
        owner_email="b@b.example",
    )
    owner = owner_of(client)
    ticket = raise_ticket(client, owner)
    beta = login(client, "bela", "ravi-pass-123", host="beta.localhost")
    assert client.get(HELP, headers=beta).json()["items"] == []
    assert client.get(f"{HELP}/{ticket['id']}", headers=beta).status_code == 404
    # The token of one company is no good at the other's address.
    assert client.get(HELP, headers={**owner, "host": "beta.localhost"}).status_code == 401


def test_the_database_hides_other_companies_tickets(client, boss, acme, seeded):
    from app.core.tenancy import set_tenant

    raise_ticket(client, owner_of(client))
    set_tenant(seeded, 1)  # the default company "main"
    assert seeded.execute(text("SELECT count(*) FROM support_ticket")).scalar_one() == 0
    set_platform(seeded)
    assert seeded.execute(text("SELECT count(*) FROM support_ticket")).scalar_one() == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"subject": "no"},
        {"subject": "x" * 201},
        {"body": ""},
        {"body": "x" * 5001},
        {"category": "weather"},
        {"priority": "whenever"},
    ],
)
def test_a_bad_ticket_is_refused(client, boss, acme, bad):
    assert client.post(HELP, headers=owner_of(client), json=NEW | bad).status_code == 422


# ------------------------------------------------------------------ replying and closing


def test_a_company_reply_returns_a_waiting_ticket_to_duolink(client, boss, helper, acme):
    owner = owner_of(client)
    ticket = raise_ticket(client, owner)
    client.post(f"{ADMIN}/{ticket['id']}/reply", headers=boss, json={"body": "Which shop?"})
    back = client.post(f"{HELP}/{ticket['id']}/reply", headers=owner, json={"body": "The second."})
    assert back.status_code == 200 and back.json()["status"] == "open"
    assert [m["author_kind"] for m in back.json()["messages"]] == [
        "company_user",
        "platform_admin",
        "company_user",
    ]


def test_only_the_person_who_raised_a_ticket_closes_it_and_a_closed_ticket_takes_no_reply(
    client, boss, acme
):
    owner = owner_of(client)
    mala = counter(client, owner, "mala")
    ticket = raise_ticket(client, mala)
    url = f"{HELP}/{ticket['id']}"
    assert client.get(url, headers=mala).json()["can_close"] is True
    assert client.get(url, headers=owner).json()["can_close"] is False  # sees it, did not raise it
    denied = client.post(f"{url}/close", headers=owner)
    assert denied.status_code == 403 and denied.json()["code"] == "TICKET_NOT_YOURS"

    closed = client.post(f"{url}/close", headers=mala)
    assert (
        closed.status_code == 200
        and closed.json()["status"] == "closed"
        and closed.json()["closed_at"]
    )
    assert client.post(f"{url}/close", headers=mala).json()["code"] == "TICKET_CLOSED"
    refused = client.post(f"{url}/reply", headers=mala, json={"body": "one more thing"})
    assert refused.status_code == 409 and refused.json()["code"] == "TICKET_CLOSED"


def test_an_expired_company_can_still_raise_and_answer_tickets(client, boss, acme):
    owner = owner_of(client)
    lapsed = client.patch(
        f"/api/v1/admin/tenants/{acme['id']}",
        headers=boss,
        json={"trial_ends_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    )
    assert lapsed.status_code == 200
    assert (
        client.post(
            "/api/v1/parties", headers=owner, json={"name": "X", "type": "customer"}
        ).status_code
        == 403
    )
    ticket = raise_ticket(client, owner)  # allowed: the M21 exception list
    assert (
        client.post(
            f"{HELP}/{ticket['id']}/reply", headers=owner, json={"body": "Hello?"}
        ).status_code
        == 200
    )
    assert client.post(f"{HELP}/{ticket['id']}/close", headers=owner).status_code == 200


# ------------------------------------------------------------------ Duolink's side


def test_an_admin_reply_needs_a_message_or_a_status(client, boss, acme):
    ticket = raise_ticket(client, owner_of(client))
    url = f"{ADMIN}/{ticket['id']}/reply"
    assert client.post(url, headers=boss, json={}).status_code == 422
    assert client.post(url, headers=boss, json={"body": "   "}).status_code == 422
    assert client.post(url, headers=boss, json={"status": "done"}).status_code == 422
    only_status = client.post(url, headers=boss, json={"status": "in_progress"})
    assert only_status.status_code == 200 and only_status.json()["status"] == "in_progress"
    assert len(only_status.json()["messages"]) == 1  # no message was added


def test_resolving_and_reopening_with_a_reply(client, boss, acme):
    owner = owner_of(client)
    ticket = raise_ticket(client, owner)
    url = f"{ADMIN}/{ticket['id']}/reply"
    done = client.post(url, headers=boss, json={"body": "Fixed.", "status": "resolved"}).json()
    assert done["status"] == "resolved"
    # The company answers a resolved ticket: it reopens.
    assert (
        client.post(
            f"{HELP}/{ticket['id']}/reply", headers=owner, json={"body": "Still broken"}
        ).json()["status"]
        == "open"
    )
    closed = client.patch(f"{ADMIN}/{ticket['id']}", headers=boss, json={"status": "closed"}).json()
    assert closed["status"] == "closed" and closed["closed_at"]
    no_message = client.post(url, headers=boss, json={"body": "Anyone there?"})
    assert no_message.status_code == 409 and no_message.json()["code"] == "TICKET_CLOSED"
    reopened = client.post(url, headers=boss, json={"body": "Reopening", "status": "open"}).json()
    assert reopened["status"] == "open" and reopened["closed_at"] is None


def test_the_admin_list_filters_and_counts(client, boss, helper, acme):
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="bela",
        owner_email="b@b.example",
    )
    owner = owner_of(client)
    beta = login(client, "bela", "ravi-pass-123", host="beta.localhost")
    first = raise_ticket(client, owner, priority="urgent", subject="Urgent sign-in problem")
    raise_ticket(client, owner, priority="low", category="stock", subject="Stock report slow")
    raise_ticket(client, beta, subject="Beta's printing issue")
    me = client.get("/api/v1/admin/auth/me", headers=boss).json()["id"]
    client.patch(f"{ADMIN}/{first['id']}", headers=boss, json={"assigned_admin_id": me})

    everything = client.get(ADMIN, headers=helper).json()
    assert everything["total"] == 3
    assert everything["counts"] == {
        "open": 3, "in_progress": 0, "waiting_on_company": 0, "resolved": 0, "closed": 0,
        "urgent_open": 1, "unassigned": 2,
    }  # fmt: skip
    row = next(t for t in everything["items"] if t["id"] == first["id"])
    assert (
        row["tenant_slug"] == "acme"
        and row["assigned_admin_name"] == "Duolink Ops"
        and row["unread"]
    )

    def numbers(**params):
        return sorted(
            t["subject"] for t in client.get(ADMIN, headers=boss, params=params).json()["items"]
        )

    assert numbers(priority="urgent") == ["Urgent sign-in problem"]
    assert numbers(tenant_id=acme["id"]) == ["Stock report slow", "Urgent sign-in problem"]
    assert numbers(assigned="me") == ["Urgent sign-in problem"]
    assert len(numbers(assigned="unassigned")) == 2
    assert numbers(q="beta") == ["Beta's printing issue"]  # the subject or the company
    assert numbers(q="T-000001") != []
    assert numbers(status="resolved") == []
    page = client.get(ADMIN, headers=boss, params={"limit": 1, "offset": 1}).json()
    assert len(page["items"]) == 1 and page["total"] == 3


def test_an_admin_opening_a_ticket_marks_the_company_message_read(client, boss, acme):
    ticket = raise_ticket(client, owner_of(client))
    unread = client.get(ADMIN, headers=boss).json()["items"][0]["unread"]
    assert unread is True
    client.get(f"{ADMIN}/{ticket['id']}", headers=boss)
    assert client.get(ADMIN, headers=boss).json()["items"][0]["unread"] is False


def test_assigning_to_someone_who_does_not_exist_is_refused_and_null_unassigns(client, boss, acme):
    ticket = raise_ticket(client, owner_of(client))
    url = f"{ADMIN}/{ticket['id']}"
    assert client.patch(url, headers=boss, json={"assigned_admin_id": 9999}).status_code == 404
    me = client.get("/api/v1/admin/auth/me", headers=boss).json()["id"]
    assert (
        client.patch(url, headers=boss, json={"assigned_admin_id": me}).json()["assigned_admin_id"]
        == me
    )
    assert (
        client.patch(url, headers=boss, json={"assigned_admin_id": None}).json()[
            "assigned_admin_id"
        ]
        is None
    )
    assert client.get(f"{ADMIN}/99999", headers=boss).status_code == 404


def test_a_message_cannot_be_changed_or_deleted(client, boss, acme, seeded):
    raise_ticket(client, owner_of(client))
    set_platform(seeded)
    for statement in ("UPDATE support_message SET body = 'x'", "DELETE FROM support_message"):
        with (
            pytest.raises(DBAPIError, match=r"append-only|not allowed|ledger"),
            seeded.begin_nested(),
        ):
            seeded.execute(text(statement))


def test_every_admin_reply_and_change_is_audited_without_the_message(client, boss, acme):
    ticket = raise_ticket(client, owner_of(client), body="A secret detail the audit must not copy")
    client.post(f"{ADMIN}/{ticket['id']}/reply", headers=boss, json={"body": "Looking into it"})
    client.patch(f"{ADMIN}/{ticket['id']}", headers=boss, json={"priority": "low"})
    events = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 20}).json()["items"]
    rows = [e for e in events if e["action"].startswith("support_")]
    assert {e["action"] for e in rows} == {"support_reply", "support_update"}
    blob = str(rows)
    assert "secret detail" not in blob and "Looking into it" not in blob
    assert (
        next(e for e in rows if e["action"] == "support_reply")["details"]["ticket"] == "T-000001"
    )


# ------------------------------------------------------------------ no money in a ticket


def test_a_ticket_answer_carries_no_amount_field(client, boss, acme):
    import re

    raise_ticket(client, owner_of(client))
    money = re.compile(r"amount|cost|price|rate|profit|margin|balance|taxable|gst|value|paid")

    def keys(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                yield key
                yield from keys(inner)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    first = client.get(ADMIN, headers=boss).json()
    detail = client.get(f"{ADMIN}/{first['items'][0]['id']}", headers=boss).json()
    company = client.get(HELP, headers=owner_of(client)).json()
    for body in (first, detail, company):
        assert [k for k in keys(body) if money.search(k)] == []
