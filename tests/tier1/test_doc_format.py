"""A document checked against a house format, and the change that sets it right, for
check-doc-format. Invented text only."""
import json

import pytest

from googledocstools.doc_format import FormatError, check, parse_format, report
from tests.conftest import Para, described

PT = "PT"


def dim(points):
    return {"magnitude": points, "unit": PT}


FORMAT = {
    "page": {"size": "letter", "margins_inches": 1},
    "body": {"font": "Times New Roman", "size": 12, "line_spacing": 2,
             "first_line_indent_inches": 0.5},
    "list": {"font": "Times New Roman", "size": 12, "line_spacing": 2,
             "first_line_indent_inches": 0},
    "heading_2": {"font": "Times New Roman", "size": 16, "bold": True, "colour": "#000000",
                  "alignment": "centre", "page_break_before": True, "keep_with_next": True,
                  "pattern": "^Chapter \\d+: "},
    "heading_3": {"font": "Times New Roman", "size": 14, "bold": True},
}
NAMED = {"styles": [
    {"namedStyleType": "NORMAL_TEXT",
     "textStyle": {"weightedFontFamily": {"fontFamily": "Times New Roman"}, "fontSize": dim(12)},
     "paragraphStyle": {"lineSpacing": 200, "indentFirstLine": dim(36)}},
    {"namedStyleType": "HEADING_2",
     "textStyle": {"fontSize": dim(16), "bold": True},
     "paragraphStyle": {"pageBreakBefore": True, "keepWithNext": True, "alignment": "CENTER",
                        "indentFirstLine": dim(0)}},
    {"namedStyleType": "HEADING_3",
     "textStyle": {"fontSize": dim(14), "bold": True},
     "paragraphStyle": {"indentFirstLine": dim(0)}},
]}
PAGE = {"pageSize": {"width": dim(612), "height": dim(792)}, "marginTop": dim(72),
        "marginBottom": dim(72), "marginLeft": dim(72), "marginRight": dim(72)}
H2 = {"namedStyleType": "HEADING_2"}
H3 = {"namedStyleType": "HEADING_3"}
LISTED = {"indentFirstLine": dim(0), "indentStart": dim(36)}


def document(paragraphs, page=PAGE):
    answer = described(paragraphs)
    answer["namedStyles"] = NAMED
    answer["documentStyle"] = page
    return answer


def clean():
    return [
        Para("Chapter 1: The start", H2),
        "Body text in the house format.",
        Para("A list item.", LISTED, {"listId": "list-1"}),
        Para("A section", H3),
        [("More text with ", {}), ("emphasis", {"italic": True, "bold": True}), (".", {})],
    ]


def test_a_document_in_the_format_has_no_problems_and_nothing_to_fix():
    checked = check(document(clean()), parse_format(json.dumps(FORMAT)))
    assert (checked.problems, checked.fixes) == ([], [])
    assert report(checked) == "Format: everything matches.\n"


def test_a_pasted_paragraph_in_another_font_and_spacing_is_reported_and_fixed():
    paragraphs = clean() + [Para([("Pasted from the web.", {
        "weightedFontFamily": {"fontFamily": "Arial"}, "fontSize": dim(11)})],
        {"lineSpacing": 100})]
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert [(p.group, p.place, p.beginning) for p in checked.problems] == [
        ("body text: font not Times New Roman", 'under "### A section"', "Pasted from the web."),
        ("body text: size not 12 pt", 'under "### A section"', "Pasted from the web."),
        ("body text: line spacing not 2", 'under "### A section"', "Pasted from the web."),
    ]
    (fix,) = checked.fixes
    assert fix.said == ["font Times New Roman", "size 12 pt", "line spacing 2"]
    start = document(paragraphs)["body"]["content"][-1]["startIndex"]
    end = document(paragraphs)["body"]["content"][-1]["endIndex"]
    assert fix.requests == [
        {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end - 1},
                             "textStyle": {"weightedFontFamily": {"fontFamily": "Times New Roman"},
                                           "fontSize": dim(12)},
                             "fields": "weightedFontFamily,fontSize"}},
        {"updateParagraphStyle": {"range": {"startIndex": start, "endIndex": end},
                                  "paragraphStyle": {"lineSpacing": 200},
                                  "fields": "lineSpacing"}},
    ]


def test_a_list_item_with_a_first_line_indent_is_fixed_to_none():
    paragraphs = clean()
    paragraphs[2] = Para("An indented item.", {"indentFirstLine": dim(18)}, {"listId": "list-1"})
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert [p.group for p in checked.problems] == ["list items: first-line indent not 0 in"]
    assert checked.fixes[0].requests[0]["updateParagraphStyle"]["paragraphStyle"] == {
        "indentFirstLine": dim(0)}


def test_a_heading_in_grey_arial_is_fixed_and_its_level_never_changed():
    paragraphs = clean()
    paragraphs[3] = Para([("A section", {"weightedFontFamily": {"fontFamily": "Arial"},
                                         "foregroundColor": {"color": {"rgbColor": {
                                             "red": 0.4, "green": 0.4, "blue": 0.4}}}})], H3)
    fmt = dict(FORMAT, heading_3=dict(FORMAT["heading_3"], colour="#000000"))
    checked = check(document(paragraphs), parse_format(json.dumps(fmt)))
    assert [p.group for p in checked.problems] == [
        "heading 3: font not Times New Roman", "heading 3: colour not #000000"]
    (request,) = checked.fixes[0].requests
    assert request["updateTextStyle"]["textStyle"] == {
        "weightedFontFamily": {"fontFamily": "Times New Roman"},
        "foregroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}}}
    assert "namedStyleType" not in json.dumps(checked.fixes)


def test_bold_text_posing_as_a_heading_is_reported_and_not_fixed():
    paragraphs = clean() + [[("Not Really A Heading", {"bold": True, "fontSize": dim(16)})]]
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert [p.group for p in checked.problems] == ["body text: size not 12 pt",
                                                   "body text: looks like a heading"]
    assert checked.fixes[0].said == ["size 12 pt"]
    assert "bold" not in json.dumps(checked.fixes[0].requests)


def test_a_chapter_heading_without_its_page_break_or_pattern_is_reported():
    paragraphs = clean()
    paragraphs[0] = Para("The start", dict(H2, pageBreakBefore=False))
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert [(p.group, p.place) for p in checked.problems] == [
        ("heading 2: page break before not on", "at the start"),
        ("heading 2: does not match ^Chapter \\d+: ", "at the start")]
    assert checked.fixes[0].said == ["page break before on"]


def test_a_heading_at_a_level_the_format_does_not_name_is_reported():
    paragraphs = clean() + [Para("Deep", {"namedStyleType": "HEADING_4"})]
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert [p.group for p in checked.problems] == [
        "heading 4: a level the format does not name"]
    assert checked.fixes == []


def test_italic_and_bold_in_body_text_are_left_alone():
    paragraphs = clean()
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert checked.problems == []


def test_an_empty_paragraph_is_not_checked_for_its_font():
    paragraphs = clean() + [[("", {"weightedFontFamily": {"fontFamily": "Arial"}})]]
    assert check(document(paragraphs), parse_format(json.dumps(FORMAT))).problems == []


def test_the_page_size_and_margins_are_checked_and_set():
    a4 = {"pageSize": {"width": dim(595.276), "height": dim(841.89)}, "marginTop": dim(72),
          "marginBottom": dim(54), "marginLeft": dim(72), "marginRight": dim(72)}
    checked = check(document(clean(), a4), parse_format(json.dumps(FORMAT)))
    assert [(p.group, p.place) for p in checked.problems] == [
        ("page: size not letter", None), ("page: margins not 1 in", None)]
    (fix,) = checked.fixes
    assert fix.said == ["size letter", "margins 1 in"]
    assert fix.requests == [{"updateDocumentStyle": {
        "documentStyle": {"pageSize": {"width": dim(612), "height": dim(792)},
                          "marginTop": dim(72), "marginBottom": dim(72), "marginLeft": dim(72),
                          "marginRight": dim(72)},
        "fields": "pageSize,marginTop,marginBottom,marginLeft,marginRight"}}]


def test_what_a_document_does_not_say_is_google_s_default():
    answer = described(["Plain text."])
    checked = check(answer, parse_format(json.dumps({"body": {"font": "Arial", "size": 11,
                                                              "line_spacing": 1}})))
    assert checked.problems == []


def test_the_report_groups_problems_and_shows_three_of_each_unless_asked():
    paragraphs = [Para("Chapter 1: Start", H2)] + [
        [("Arial paragraph %d." % n, {"weightedFontFamily": {"fontFamily": "Arial"}})]
        for n in range(1, 6)]
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert report(checked) == (
        "body text: font not Times New Roman: 5 paragraphs\n"
        '  under "## Chapter 1: Start": Arial paragraph 1.\n'
        '  under "## Chapter 1: Start": Arial paragraph 2.\n'
        '  under "## Chapter 1: Start": Arial paragraph 3.\n'
        "  … and 2 more (-v shows them all)\n"
        "Format: 5 problems in 5 paragraphs.\n")
    assert report(checked, verbose=True).count("Arial paragraph") == 5


def test_a_page_problem_is_one_line_and_counted_with_the_page():
    checked = check(document(clean(), dict(PAGE, marginLeft=dim(90))),
                    parse_format(json.dumps(FORMAT)))
    assert report(checked) == ("page: margins not 1 in\n"
                               "Format: 1 problem in 0 paragraphs and the page.\n")


def test_an_example_format_file_reads_as_it_stands():
    assert parse_format(json.dumps(FORMAT))["heading_2"]["pattern"] == "^Chapter \\d+: "


@pytest.mark.parametrize("fmt,problem", [
    ([], "a JSON object"),
    ({}, "names nothing to check"),
    ({"bodies": {}}, 'unknown part "bodies"'),
    ({"body": {"font": 12}}, 'body: "font" must be'),
    ({"body": {"size": 0}}, 'body: "size" must be a number above 0'),
    ({"body": {"size": True}}, 'body: "size" must be a number above 0'),
    ({"body": {"bold": True}}, 'body: unknown key "bold"'),
    ({"list": {"first_line_indent_inches": -1}}, 'list: "first_line_indent_inches" must be'),
    ({"heading_2": {"colour": "black"}}, 'heading_2: "colour" must be #rrggbb'),
    ({"heading_2": {"alignment": "middle"}}, 'heading_2: "alignment" must be one of'),
    ({"heading_2": {"bold": "yes"}}, 'heading_2: "bold" must be true or false'),
    ({"heading_2": {"pattern": "(["}}, 'heading_2: "pattern" is not a regular expression'),
    ({"title": {"line_spacing": 2}}, 'title: unknown key "line_spacing"'),
    ({"page": {"size": "folio"}}, 'page: "size" must be'),
    ({"page": {"size": [8.5]}}, 'page: "size" must be'),
    ({"page": {"margins_inches": "1"}}, 'page: "margins_inches" must be'),
    ({"heading_7": {"bold": True}}, 'unknown part "heading_7"'),
    ({"body": []}, "body: must be an object"),
])
def test_each_fault_in_a_format_file_is_named(fmt, problem):
    with pytest.raises(FormatError) as raised:
        parse_format(json.dumps(fmt))
    assert any(problem in found for found in raised.value.problems), raised.value.problems


def test_a_format_file_that_is_not_json_is_refused():
    with pytest.raises(FormatError) as raised:
        parse_format("{")
    assert raised.value.problems[0].startswith("not JSON")


def test_the_title_is_checked_against_the_title_part():
    paragraphs = [Para("The Book", {"namedStyleType": "TITLE"})] + clean()
    fmt = dict(FORMAT, title={"size": 24})
    checked = check(document(paragraphs), parse_format(json.dumps(fmt)))
    assert [(p.group, p.place) for p in checked.problems] == [
        ("title: size not 24 pt", "at the start")]
    assert checked.problems and report(checked).splitlines()[1] == "  at the start: The Book"


def test_a_subtitle_and_list_items_with_no_part_of_their_own_are_not_checked():
    paragraphs = clean() + [Para([("A subtitle", {"fontSize": dim(30)})],
                                 {"namedStyleType": "SUBTITLE"})]
    paragraphs[2] = Para("An indented item.", {"indentFirstLine": dim(18)}, {"listId": "list-1"})
    fmt = {key: value for key, value in FORMAT.items() if key != "list"}
    assert check(document(paragraphs), parse_format(json.dumps(fmt))).problems == []


def test_the_example_format_file_in_the_checkout_reads_as_it_stands():
    import os

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(here, "check-doc-format.example.json"), encoding="utf-8") as handle:
        example = parse_format(handle.read())
    assert example["body"] == {"font": "Times New Roman", "size": 12, "line_spacing": 2,
                               "first_line_indent_inches": 0.5}
    assert example["heading_2"]["pattern"] == "^Chapter \\d+: "
