"""The pure pieces of google-sign-in: the PKCE challenge, the address to open, the env file."""
from urllib.parse import parse_qs, urlsplit

from googledocstools.sign_in import authorization_url, challenge_for, with_token

HOSTILE = "it's \\ \"x\" $HOME `id` é 🐿️"
LINE = "export GOOGLE_OAUTH_REFRESH_TOKEN="
SCOPE = "https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/drive"


def test_the_challenge_is_the_one_the_pkce_standard_gives_for_its_own_example():
    # RFC 7636, appendix B.
    assert challenge_for("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


def test_the_address_to_open_carries_each_thing_google_asks_for():
    url = authorization_url("an-id", "http://127.0.0.1:5000", "a-state", "a-challenge",
                            "tools-user@example.org")
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https", "accounts.google.com", "/o/oauth2/v2/auth")
    assert parse_qs(parts.query) == {
        "client_id": ["an-id"],
        "redirect_uri": ["http://127.0.0.1:5000"],
        "response_type": ["code"],
        "scope": [SCOPE],
        "code_challenge": ["a-challenge"],
        "code_challenge_method": ["S256"],
        "state": ["a-state"],
        "login_hint": ["tools-user@example.org"],
    }


def test_hostile_characters_in_the_account_stay_inside_their_own_part_of_the_address():
    url = authorization_url("id", "http://127.0.0.1:1", "s", "c", "a&scope=everything#@x y")
    query = parse_qs(urlsplit(url).query)
    assert query["login_hint"] == ["a&scope=everything#@x y"]
    assert query["scope"] == [SCOPE]
    assert urlsplit(url).fragment == ""


def test_the_token_replaces_the_empty_value_and_every_other_line_is_kept():
    before = "# a note\nexport GOOGLE_OAUTH_CLIENT_ID='abc'\n" + LINE + "''\n# after\n"
    assert with_token(before, "new-token") == (
        "# a note\nexport GOOGLE_OAUTH_CLIENT_ID='abc'\n" + LINE + "new-token\n# after\n")


def test_an_old_token_is_replaced_not_kept_beside_the_new_one():
    after = with_token(LINE + "'old-token'\n", "new-token")
    assert after == LINE + "new-token\n"
    assert "old-token" not in after


def test_every_line_that_sets_the_token_is_replaced_so_no_stale_one_is_left():
    after = with_token(LINE + "one\nOTHER=1\n" + LINE + "two\n", "new")
    assert after == LINE + "new\nOTHER=1\n" + LINE + "new\n"


def test_a_line_without_export_keeps_its_own_form():
    assert with_token("GOOGLE_OAUTH_REFRESH_TOKEN=old\n", "new") == (
        "GOOGLE_OAUTH_REFRESH_TOKEN=new\n")


def test_the_line_is_added_at_the_end_when_there_is_none():
    assert with_token("A=1\n", "new") == "A=1\n" + LINE + "new\n"
    assert with_token("A=1", "new") == "A=1\n" + LINE + "new\n"
    assert with_token("", "new") == LINE + "new\n"


def test_a_comment_or_a_longer_name_is_not_mistaken_for_the_line():
    before = "# " + LINE + "''\nexport GOOGLE_OAUTH_REFRESH_TOKEN_OLD='keep'\n"
    assert with_token(before, "new") == before + LINE + "new\n"


def test_windows_line_endings_and_a_missing_final_newline_are_kept_as_they_are():
    assert with_token("A=1\r\n" + LINE + "''", "new") == "A=1\r\n" + LINE + "new"


def test_a_token_with_hostile_characters_is_quoted_for_the_shell():
    after = with_token(LINE + "''\n", HOSTILE)
    assert after == LINE + "'it'\"'\"'s \\ \"x\" $HOME `id` é 🐿️'\n"
