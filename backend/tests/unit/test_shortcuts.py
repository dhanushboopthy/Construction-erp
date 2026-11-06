import pytest

from app.domain.shortcuts import ShortcutError, normalise, validate_set


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Alt+N", "Alt+N"),
        ("alt+n", "Alt+N"),
        (" ALT + shift + 7 ", "Alt+Shift+7"),
        ("shift+alt+q", "Alt+Shift+Q"),
    ],
)
def test_normalise_gives_one_stored_form(raw, stored):
    assert normalise(raw) == stored


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "N",
        "Alt",
        "Alt+",
        "Shift+N",  # no Alt
        "Ctrl+Alt+N",  # Ctrl never
        "Alt+Meta+N",
        "Alt+Alt+N",
        "Alt+NN",
        "Alt+F4",
        "Alt+-",
        "Alt+Shift+Shift+N",
    ],
)
def test_normalise_refuses_what_is_not_alt_plus_one_key(raw):
    with pytest.raises(ShortcutError):
        normalise(raw)


@pytest.mark.parametrize("raw", ["Alt+D", "alt+f", "Alt+E"])
def test_normalise_refuses_what_the_browser_takes(raw):
    with pytest.raises(ShortcutError, match="browser"):
        normalise(raw)


def test_the_editor_key_can_never_be_taken():
    # Ctrl+Shift+Alt+1 has Ctrl in it, and Ctrl is never allowed.
    with pytest.raises(ShortcutError):
        normalise("Ctrl+Shift+Alt+1")


def test_validate_set_returns_canonical_pairs():
    assert validate_set([("go:/items", "alt+i"), ("new", "Alt+Shift+N")]) == [
        ("go:/items", "Alt+I"),
        ("new", "Alt+Shift+N"),
    ]


def test_validate_set_names_the_action_with_the_problem():
    with pytest.raises(ShortcutError) as caught:
        validate_set([("new", "Alt+N"), ("go:/items", "Ctrl+I")])
    assert caught.value.field == "go:/items"


def test_two_actions_cannot_share_a_combination():
    with pytest.raises(ShortcutError, match="already used") as caught:
        validate_set([("new", "Alt+N"), ("go:/items", "alt+n")])
    assert caught.value.field == "go:/items"


def test_an_action_has_one_shortcut():
    with pytest.raises(ShortcutError, match="only one"):
        validate_set([("new", "Alt+N"), ("new", "Alt+M")])


@pytest.mark.parametrize("action", ["", "New", "go items", "x" * 61, "-bad"])
def test_action_ids_are_plain(action):
    with pytest.raises(ShortcutError, match="Unknown action"):
        validate_set([(action, "Alt+N")])
