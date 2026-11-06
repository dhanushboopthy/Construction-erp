"""A user's own keyboard shortcuts (/api/v1/me/shortcuts).

The default company "main" is seeded with owner, counter1, counter2 and accounts.
"""

import pytest

from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
URL = "/api/v1/me/shortcuts"


def test_a_new_user_has_no_changes(client):
    owner = login(client, *OWNER)
    assert client.get(URL, headers=owner).json() == {"items": []}


def test_a_user_saves_and_reads_back_their_changes(client):
    owner = login(client, *OWNER)
    saved = client.put(
        URL,
        headers=owner,
        json={
            "items": [
                {"action_id": "new", "combo": "alt+shift+n"},
                {"action_id": "go:/items", "combo": "Alt+I"},
            ]
        },
    )
    assert saved.status_code == 200
    assert saved.json()["items"] == [
        {"action_id": "go:/items", "combo": "Alt+I"},
        {"action_id": "new", "combo": "Alt+Shift+N"},
    ]
    assert client.get(URL, headers=owner).json() == saved.json()


def test_saving_again_replaces_and_two_combinations_can_be_swapped(client):
    owner = login(client, *OWNER)
    first = {"items": [{"action_id": "a", "combo": "Alt+X"}, {"action_id": "b", "combo": "Alt+Y"}]}
    swapped = {
        "items": [{"action_id": "a", "combo": "Alt+Y"}, {"action_id": "b", "combo": "Alt+X"}]
    }
    assert client.put(URL, headers=owner, json=first).status_code == 200
    again = client.put(URL, headers=owner, json=swapped)
    assert again.status_code == 200
    assert again.json()["items"] == swapped["items"]


@pytest.mark.parametrize(
    ("items", "field"),
    [
        ([{"action_id": "new", "combo": "Ctrl+N"}], "new"),
        ([{"action_id": "new", "combo": "Alt+D"}], "new"),
        ([{"action_id": "new", "combo": "N"}], "new"),
        (
            [{"action_id": "a", "combo": "Alt+N"}, {"action_id": "b", "combo": "alt+n"}],
            "b",
        ),
        ([{"action_id": "x", "combo": "Alt+N"}, {"action_id": "x", "combo": "Alt+M"}], "x"),
        ([{"action_id": "Bad Id", "combo": "Alt+N"}], "Bad Id"),
    ],
)
def test_a_bad_set_is_refused_and_changes_nothing(client, items, field):
    owner = login(client, *OWNER)
    client.put(URL, headers=owner, json={"items": [{"action_id": "keep", "combo": "Alt+K"}]})
    refused = client.put(URL, headers=owner, json={"items": items})
    assert refused.status_code == 422
    assert refused.json()["code"] == "INVALID_SHORTCUT"
    assert refused.json()["field"] == field
    assert client.get(URL, headers=owner).json()["items"] == [
        {"action_id": "keep", "combo": "Alt+K"}
    ]


def test_each_user_sees_only_their_own(client):
    owner = login(client, *OWNER)
    counter = login(client, *COUNTER)
    client.put(URL, headers=owner, json={"items": [{"action_id": "new", "combo": "Alt+B"}]})
    assert client.get(URL, headers=counter).json() == {"items": []}
    # The same combination is fine for another user.
    assert (
        client.put(
            URL, headers=counter, json={"items": [{"action_id": "go:/sales", "combo": "Alt+B"}]}
        ).status_code
        == 200
    )
    assert client.get(URL, headers=owner).json()["items"] == [
        {"action_id": "new", "combo": "Alt+B"}
    ]


def test_reset_restores_every_default(client):
    owner = login(client, *OWNER)
    client.put(URL, headers=owner, json={"items": [{"action_id": "new", "combo": "Alt+B"}]})
    assert client.delete(URL, headers=owner).status_code == 204
    assert client.get(URL, headers=owner).json() == {"items": []}


def test_it_needs_a_sign_in(client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"items": []}).status_code == 401
