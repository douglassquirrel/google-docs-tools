import pytest

from googledocstools.settings import SettingsError, parse_settings, read_settings


def test_reads_key_value_lines():
    assert parse_settings("A=1\nB=two\n") == {"A": "1", "B": "two"}


def test_skips_blank_lines_and_whole_line_comments():
    assert parse_settings("# a note\n\n   \nA=1\n  # indented note\n") == {"A": "1"}


def test_trims_spaces_round_the_key_and_the_value():
    assert parse_settings("  A  =  two words  \n") == {"A": "two words"}


def test_takes_matching_quotes_off_a_value_and_keeps_what_is_inside():
    text = "A=\"  kept  \"\nB='it''s'\nC=\"unbalanced\nD='\n"
    assert parse_settings(text) == {"A": "  kept  ", "B": "it''s", "C": "\"unbalanced", "D": "'"}


def test_a_hash_or_an_equals_sign_inside_a_value_is_part_of_the_value():
    assert parse_settings("A={date} issue #12 = draft\n") == {"A": "{date} issue #12 = draft"}


def test_an_empty_value_is_kept_as_empty():
    assert parse_settings("A=\nB=''\n") == {"A": "", "B": ""}


def test_a_later_line_wins_over_an_earlier_one_for_the_same_key():
    assert parse_settings("A=1\nA=2\n") == {"A": "2"}


def test_reads_windows_line_endings_and_no_final_newline():
    assert parse_settings("A=1\r\nB=2") == {"A": "1", "B": "2"}


def test_keeps_unicode_in_values():
    assert parse_settings("A=Señor 🐿️ café\n") == {"A": "Señor 🐿️ café"}


def test_a_line_that_is_not_key_value_is_refused_with_its_line_number():
    with pytest.raises(SettingsError) as error:
        parse_settings("A=1\nthis is not a setting\n")
    assert "line 2" in str(error.value)


def test_a_line_with_no_key_is_refused_with_its_line_number():
    with pytest.raises(SettingsError) as error:
        parse_settings("=value\n")
    assert "line 1" in str(error.value)


def test_reads_the_named_file(tmp_path):
    named = tmp_path / "my settings.conf"
    named.write_text("A=1\n", encoding="utf-8")
    assert read_settings(str(named), str(tmp_path / "absent.conf")) == {"A": "1"}


def test_a_named_file_that_is_missing_is_an_error_naming_it(tmp_path):
    named = tmp_path / "nowhere.conf"
    with pytest.raises(SettingsError) as error:
        read_settings(str(named), str(tmp_path / "absent.conf"))
    assert str(named) in str(error.value)


def test_with_no_named_file_the_default_is_read_if_it_exists(tmp_path):
    default = tmp_path / "default.conf"
    default.write_text("A=from default\n", encoding="utf-8")
    assert read_settings(None, str(default)) == {"A": "from default"}


def test_with_no_named_file_and_no_default_there_are_no_settings_and_no_error(tmp_path):
    assert read_settings(None, str(tmp_path / "absent.conf")) == {}


def test_the_named_file_is_used_instead_of_the_default_not_merged_with_it(tmp_path):
    default = tmp_path / "default.conf"
    default.write_text("A=default\nB=default\n", encoding="utf-8")
    named = tmp_path / "named.conf"
    named.write_text("A=named\n", encoding="utf-8")
    assert read_settings(str(named), str(default)) == {"A": "named"}


def test_a_settings_file_that_is_not_text_is_an_error_not_a_traceback(tmp_path):
    named = tmp_path / "binary.conf"
    named.write_bytes(b"A=\xff\xfe\n")
    with pytest.raises(SettingsError) as error:
        read_settings(str(named), str(tmp_path / "absent.conf"))
    assert str(named) in str(error.value)


def test_a_problem_in_a_file_names_the_file_as_well_as_the_line(tmp_path):
    named = tmp_path / "bad.conf"
    named.write_text("A=1\noops\n", encoding="utf-8")
    with pytest.raises(SettingsError) as error:
        read_settings(str(named), str(tmp_path / "absent.conf"))
    assert str(named) in str(error.value) and "line 2" in str(error.value)
