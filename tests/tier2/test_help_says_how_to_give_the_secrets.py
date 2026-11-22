"""Every command's --help says how to give it the Google secrets: through lobster-tools' secrets
command and the shared set (PLAN.md Settled 13), or a secrets file sourced in the same command."""
import importlib
import re

import pytest

COMMANDS = ["read_doc", "comment_doc", "watch_doc", "insert_picture", "replace_picture",
            "count_doc", "check_typography", "edit_doc", "insert_paragraphs", "check_doc_format"]


@pytest.mark.parametrize("module", COMMANDS)
def test_help_names_the_shared_set_and_not_the_old_folder(module, capsys):
    code = importlib.import_module("googledocstools." + module).main(["--help"], env={})
    out = " ".join(capsys.readouterr().out.split())  # as one line, whatever argparse wraps
    assert code == 0
    assert "secrets run google -- " in out and "source a secrets file" in out
    assert "google-docs-tools-secrets" not in out


def test_the_sign_in_help_sends_a_person_elsewhere_for_the_shared_set(capsys):
    from googledocstools import sign_in
    code = sign_in.main(["--help"], env={})
    # argparse may break a line after a word's hyphen: join that without a space.
    out = " ".join(re.sub(r"(?<=\w)-\n\s*", "-", capsys.readouterr().out).split())
    assert code == 0 and "source a secrets file" in out
    assert "shared" in out and "online-publishing-tools' google-sign-in" in out
    assert "google-docs-tools-secrets" not in out
