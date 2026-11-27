"""A document checked against a house format, and the change that sets it right, for
check-doc-format. Invented text only."""
import json

import pytest

from googledocstools.doc_format import Fix, FormatError, Problem, check, parse_format, report
from tests.conftest import FOOTNOTE, Para, described

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
    assert example["footnote"] == {"font": "Times New Roman", "size": 10}


TITLE_PAGE = [
    Para([("The Invented Book", {"fontSize": dim(28), "bold": True})],
         {"namedStyleType": "TITLE", "alignment": "CENTER"}),
    Para([("A subtitle", {"bold": True, "italic": True})], {"alignment": "CENTER"}),
    Para("Contents", {"indentFirstLine": dim(0)}),
    Para("Chapter 1: The start", {"indentFirstLine": dim(0), "indentStart": dim(36)}),
]


def test_start_at_leaves_the_front_matter_unchecked_and_unfixed_and_says_how_much():
    paragraphs = TITLE_PAGE + clean() + [[("Pasted.", {"weightedFontFamily": {
        "fontFamily": "Arial"}})]]
    fmt = dict(FORMAT, start_at="heading_2", title={"size": 24})
    checked = check(document(paragraphs), parse_format(json.dumps(fmt)))
    assert [(p.group, p.beginning) for p in checked.problems] == [
        ("body text: font not Times New Roman", "Pasted.")]
    assert [fix.beginning for fix in checked.fixes] == ["Pasted."]
    assert report(checked).splitlines()[-2:] == [
        "Left out: 4 paragraphs before the first heading 2.",
        "Format: 1 problem in 1 paragraph."]


def test_start_at_still_checks_the_page():
    fmt = dict(FORMAT, start_at="heading_2")
    checked = check(document(TITLE_PAGE + clean(), dict(PAGE, marginLeft=dim(90))),
                    parse_format(json.dumps(fmt)))
    assert [p.group for p in checked.problems] == ["page: margins not 1 in"]


def test_start_at_with_no_such_heading_leaves_nothing_out_and_says_so():
    fmt = dict(FORMAT, start_at="heading_1")
    checked = check(document(clean()), parse_format(json.dumps(fmt)))
    assert report(checked) == ("Left out: nothing; the document has no heading 1.\n"
                               "Format: everything matches.\n")


def test_a_clean_document_from_its_start_says_what_it_left_out_too():
    fmt = dict(FORMAT, start_at="heading_2")
    checked = check(document(TITLE_PAGE + clean()), parse_format(json.dumps(fmt)))
    assert report(checked) == ("Left out: 4 paragraphs before the first heading 2.\n"
                               "Format: everything matches.\n")


def test_empty_paragraphs_are_never_checked_or_fixed_whatever_they_set():
    paragraphs = clean() + [
        Para("", {"indentFirstLine": dim(0), "lineSpacing": 100}),
        Para("   ", {"indentFirstLine": dim(0)}),
        Para("", H2),
        Para("", {"namedStyleType": "HEADING_4"}),
    ]
    checked = check(document(paragraphs), parse_format(json.dumps(FORMAT)))
    assert (checked.problems, checked.fixes) == ([], [])


@pytest.mark.parametrize("value", ["heading_7", "body", "page", 2, None])
def test_start_at_must_name_the_title_or_a_heading_level(value):
    with pytest.raises(FormatError) as raised:
        parse_format(json.dumps(dict(FORMAT, start_at=value)))
    assert any('"start_at" must be title or heading_1 to heading_6' in problem
               for problem in raised.value.problems), raised.value.problems


def test_start_at_alone_names_nothing_to_check():
    with pytest.raises(FormatError) as raised:
        parse_format(json.dumps({"start_at": "heading_2"}))
    assert raised.value.problems == ["the file names nothing to check"]


def test_start_at_on_the_first_paragraph_leaves_out_none_and_says_it_was_found():
    fmt = dict(FORMAT, start_at="heading_2")
    checked = check(document(clean()), parse_format(json.dumps(fmt)))
    assert report(checked) == ("Left out: 0 paragraphs before the first heading 2.\n"
                               "Format: everything matches.\n")


ARIAL_OWN = {"weightedFontFamily": {"fontFamily": "Arial"}}
TIMES = {"weightedFontFamily": {"fontFamily": "Times New Roman"}}


def test_setting_the_font_gives_back_each_pieces_own_bold_in_the_same_change():
    # Google drops a piece's own bold when its font is set (seen 22 November 2026).
    paragraphs = clean() + [Para([("Some ", ARIAL_OWN), ("strong", dict(ARIAL_OWN, bold=True)),
                                  (" words in a sentence long enough.", ARIAL_OWN)])]
    described_ = document(paragraphs)
    start, end = (described_["body"]["content"][-1][key] for key in ("startIndex", "endIndex"))
    (fix,) = check(described_, parse_format(json.dumps(FORMAT))).fixes
    assert fix.said == ["font Times New Roman"]
    assert fix.requests == [
        {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end - 1},
                             "textStyle": TIMES, "fields": "weightedFontFamily"}},
        {"updateTextStyle": {"range": {"startIndex": start + 5, "endIndex": start + 11},
                             "textStyle": {"bold": True}, "fields": "bold"}},
    ]


def test_a_heading_given_its_font_and_its_bold_gets_the_bold_after_the_font():
    paragraphs = clean() + [Para([("Plain heading", dict(ARIAL_OWN, bold=False))], H3)]
    described_ = document(paragraphs)
    start, end = (described_["body"]["content"][-1][key] for key in ("startIndex", "endIndex"))
    (fix,) = check(described_, parse_format(json.dumps(FORMAT))).fixes
    assert fix.said == ["font Times New Roman", "bold on"]
    assert fix.requests == [
        {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end - 1},
                             "textStyle": TIMES, "fields": "weightedFontFamily"}},
        {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end - 1},
                             "textStyle": {"bold": True}, "fields": "bold"}},
    ]


# Footnotes (Request 09): a footnote's paragraphs are Normal text, with Google's 10 pt on the text.
ARIAL_10 = {"weightedFontFamily": {"fontFamily": "Arial"}, "fontSize": dim(10)}
TIMES_10 = {"weightedFontFamily": {"fontFamily": "Times New Roman"}, "fontSize": dim(10)}
NOTES = {"footnote": {"font": "Times New Roman", "size": 10}}


def mark(note_id):
    return (FOOTNOTE, {"footnote": note_id})


def noted(paragraphs, footnotes):
    answer = described(paragraphs, footnotes=footnotes)
    answer["namedStyles"] = NAMED
    answer["documentStyle"] = PAGE
    return answer


def two_notes():
    return noted([[("A quoted line", {}), mark("n-1"), (" ends.", {})],
                  [("Another", {}), mark("n-2"), (".", {})]],
                 {"n-1": [[(" Jo Bloggs, ", ARIAL_10), ("A Book", dict(ARIAL_10, italic=True)),
                           (".", ARIAL_10)]],
                  "n-2": [[(" A note already right.", TIMES_10)]]})


def test_the_footnote_part_takes_the_keys_body_text_takes_and_no_others():
    assert parse_format(json.dumps({"footnote": {"font": "Times New Roman", "size": 10,
                                                 "line_spacing": 1,
                                                 "first_line_indent_inches": 0}}))
    with pytest.raises(FormatError) as refused:
        parse_format(json.dumps({"footnote": {"bold": True, "size": 0}}))
    assert refused.value.problems == ['footnote: unknown key "bold"',
                                      'footnote: "size" must be a number above 0']


def test_each_footnote_is_checked_and_fixed_in_its_own_segment_leaving_italic_alone():
    checked = check(two_notes(), NOTES)
    assert checked.problems == [Problem("footnote: font not Times New Roman", "footnote 1",
                                        "Jo Bloggs, A Book.", ("n-1", 0))]
    assert checked.fixes == [Fix("footnote 1", "Jo Bloggs, A Book.", ["font Times New Roman"], [
        {"updateTextStyle": {"range": {"segmentId": "n-1", "startIndex": 0, "endIndex": 19},
                             "textStyle": {"weightedFontFamily": {"fontFamily": "Times New Roman"}},
                             "fields": "weightedFontFamily"}}])]


def test_a_footnotes_own_bold_is_put_back_after_its_font_and_its_spacing_set():
    found = noted([[("Text", {}), mark("n-1")]],
                  {"n-1": [[(" See ", ARIAL_10), ("this", dict(ARIAL_10, bold=True)),
                            (" page.", ARIAL_10)]]})
    fixes = check(found, {"footnote": {"font": "Times New Roman", "line_spacing": 1}}).fixes
    assert fixes[0].said == ["font Times New Roman", "line spacing 1"]
    assert fixes[0].requests[1:] == [
        {"updateTextStyle": {"range": {"segmentId": "n-1", "startIndex": 5, "endIndex": 9},
                             "textStyle": {"bold": True}, "fields": "bold"}},
        {"updateParagraphStyle": {"range": {"segmentId": "n-1", "startIndex": 0, "endIndex": 16},
                                  "paragraphStyle": {"lineSpacing": 100}, "fields": "lineSpacing"}},
    ]


def test_a_format_without_the_part_checks_no_footnote_and_a_document_without_any_is_clean():
    assert check(two_notes(), {"body": {"font": "Times New Roman"}}).problems == []
    assert check(noted(["No notes here."], {}), NOTES).problems == []


def test_a_footnote_marked_in_the_front_matter_is_left_out_with_it():
    found = noted([[("Front matter", {}), mark("n-1")], Para("Chapter 1: The start", H2),
                   [("Chapter text", {}), mark("n-2")]],
                  {"n-1": [[(" Front note.", ARIAL_10)]], "n-2": [[(" Chapter note.", ARIAL_10)]]})
    checked = check(found, dict(NOTES, start_at="heading_2"))
    assert [(problem.place, problem.beginning) for problem in checked.problems] == [
        ("footnote 2", "Chapter note.")]


def test_the_report_counts_a_footnotes_paragraph_apart_from_the_body_paragraph_at_its_place():
    found = noted([[("Body in Arial", ARIAL_10), mark("n-1")]],
                  {"n-1": [[(" A note in Arial.", ARIAL_10)]]})
    shown = report(check(found, {"body": {"font": "Times New Roman"},
                                 "footnote": {"font": "Times New Roman"}}))
    assert shown == ("body text: font not Times New Roman: 1 paragraph\n"
                     "  at the start: Body in Arial\n"
                     "footnote: font not Times New Roman: 1 paragraph\n"
                     "  footnote 1: A note in Arial.\n"
                     "Format: 2 problems in 2 paragraphs.\n")


def test_an_empty_footnote_is_not_checked():
    found = noted([[("Text", {}), mark("n-1")]], {"n-1": [[(" ", ARIAL_10)]]})
    assert check(found, NOTES).problems == []
