"""Finding a placeholder in a document's description, and building the change that fills it."""
import pytest

from googledocstools import document


@pytest.mark.parametrize("text,units", [
    ("", 0), ("abc", 3), ("é", 1), ("“x”", 3), ("🐿", 2), ("🐿️", 3), ("a🐿️b\n", 6),
])
def test_length_is_counted_as_google_counts_it_in_utf16_units(text, units):
    assert document.units(text) == units


BOLD = {"bold": True}


def test_finds_where_a_placeholder_starts_and_ends():
    from tests.conftest import described

    doc = described(["Hello.", [("Lead-in ", BOLD), ("[INSIGHT]", {})], "After."])
    # "Hello.\n" is 1 to 8; "Lead-in " is 8 to 16; the placeholder is the nine after that.
    assert document.find(doc, "[INSIGHT]") == [(16, 25)]


def test_an_emoji_before_the_placeholder_counts_as_google_counts_it():
    from tests.conftest import described

    doc = described(["🐿️ news: [TITLE] here"])
    # The squirrel is three units (two for the animal, one for its variation mark), so
    # "🐿️ news: " is ten, and the text starts at 1.
    assert document.find(doc, "[TITLE]") == [(11, 18)]
    assert document.find(doc, "🐿️") == [(1, 4)]


def test_a_placeholder_split_between_differently_styled_pieces_is_still_found():
    from tests.conftest import described

    doc = described([[("Before [INS", {}), ("IGH", BOLD), ("T] after", {"italic": True})]])
    assert document.find(doc, "[INSIGHT]") == [(8, 17)]


def test_every_place_the_text_appears_is_found_in_order_and_none_is_an_empty_list():
    from tests.conftest import described

    doc = described(["[TITLE] and again [TITLE].", "Nothing here.", "Last: [TITLE]"])
    # First paragraph: 1 to 28 with its newline. Second: 28 to 42. Third starts at 42.
    assert document.find(doc, "[TITLE]") == [(1, 8), (19, 26), (48, 55)]
    assert document.find(doc, "[MISSING]") == []
    assert document.find(doc, "[title]") == []


def test_text_inside_a_table_is_found_too():
    from tests.conftest import described

    doc = described(["Above the table."])
    cell = {"startIndex": 20, "endIndex": 31, "content": [{
        "startIndex": 21, "endIndex": 31, "paragraph": {"elements": [
            {"startIndex": 21, "endIndex": 31, "textRun": {"content": "x [EVENTS]\n"}}]}}]}
    doc["body"]["content"].append({"startIndex": 18, "endIndex": 32, "table": {
        "rows": 1, "columns": 1, "tableRows": [{"startIndex": 19, "endIndex": 31,
                                                "tableCells": [cell]}]}})
    assert document.find(doc, "[EVENTS]") == [(23, 31)]


def test_a_picture_in_the_paragraph_is_counted_in_positions_and_never_joined_across():
    picture = {"startIndex": 5, "endIndex": 6, "inlineObjectElement": {"inlineObjectId": "p"}}
    # "[INS" is 1 to 5, the picture 5 to 6, and "IGHT] [DONE]" with its newline 6 to 19.
    doc = {"body": {"content": [{"startIndex": 1, "endIndex": 19, "paragraph": {"elements": [
        {"startIndex": 1, "endIndex": 5, "textRun": {"content": "[INS"}},
        picture,
        {"startIndex": 6, "endIndex": 19, "textRun": {"content": "IGHT] [DONE]\n"}},
    ]}}]}}
    assert document.find(doc, "[INSIGHT]") == []
    assert document.find(doc, "[DONE]") == [(12, 18)]


def test_the_change_for_plain_text_takes_the_placeholder_out_and_puts_the_text_in_its_place():
    from googledocstools.markup import Span

    assert document.change(16, 25, [[Span("New text.")]])[:2] == [
        {"deleteContentRange": {"range": {"startIndex": 16, "endIndex": 25}}},
        {"insertText": {"location": {"index": 16}, "text": "New text."}},
    ]


def test_further_paragraphs_follow_each_on_a_new_line():
    from googledocstools.markup import Span

    requests = document.change(16, 25, [[Span("One.")], [Span("Two "), Span("b", bold=True)],
                                        [Span("Three.")]])
    assert requests[1] == {"insertText": {"location": {"index": 16},
                                          "text": "One.\nTwo b\nThree."}}


def test_the_inserted_text_is_first_cleared_of_every_look_but_its_font_and_size():
    from googledocstools.markup import Span

    requests = document.change(16, 25, [[Span("Hi 🐿️")], [Span("x")]])
    # "Hi 🐿️", a newline and "x" are 6 + 1 + 1 units: 16 to 24. The fields are named and left
    # unset, which is how the Docs API is asked to put a property back to what it inherits.
    # Font and size are not among them (Request 4, Squirrel's decision).
    assert requests[2] == {"updateTextStyle": {
        "range": {"startIndex": 16, "endIndex": 24}, "textStyle": {},
        "fields": "bold,italic,underline,strikethrough,smallCaps,backgroundColor,"
                  "foregroundColor,baselineOffset,link"}}
    assert len(requests) == 3


def test_a_bold_piece_is_made_bold_over_exactly_its_own_characters():
    from googledocstools.markup import Span

    requests = document.change(16, 25, [[Span("🐿️ a "), Span("bold bit", bold=True), Span(".")]])
    # "🐿️ a " is six units (the squirrel alone is three), so the bold piece is 22 to 30.
    assert requests[3:] == [{"updateTextStyle": {
        "range": {"startIndex": 22, "endIndex": 30}, "textStyle": {"bold": True},
        "fields": "bold"}}]


def test_a_piece_in_a_later_paragraph_is_placed_after_the_line_breaks_before_it():
    from googledocstools.markup import Span

    requests = document.change(16, 25, [[Span("a")], [Span("bb")], [Span("c "),
                                                                    Span("bold", bold=True)]])
    # "a" 16, break 17, "bb" 18 to 20, break 20, "c " 21 to 23, so the bold piece is 23 to 27.
    assert requests[3:] == [{"updateTextStyle": {
        "range": {"startIndex": 23, "endIndex": 27}, "textStyle": {"bold": True},
        "fields": "bold"}}]


def test_an_italic_piece_is_made_italic():
    from googledocstools.markup import Span

    requests = document.change(16, 25, [[Span("so "), Span("very", italic=True)]])
    assert requests[3:] == [{"updateTextStyle": {
        "range": {"startIndex": 19, "endIndex": 23}, "textStyle": {"italic": True},
        "fields": "italic"}}]


def test_a_link_piece_is_made_a_link_to_its_address():
    from googledocstools.markup import Span

    url = "https://example.org/a?b=1&c=é#d"
    requests = document.change(16, 25, [[Span("see "), Span("this", link=url)]])
    assert requests[3:] == [{"updateTextStyle": {
        "range": {"startIndex": 20, "endIndex": 24}, "textStyle": {"link": {"url": url}},
        "fields": "link"}}]


def test_a_piece_with_several_marks_gets_them_in_one_request():
    from googledocstools.markup import Span

    url = "https://example.org"
    requests = document.change(16, 25, [[Span("all", bold=True, italic=True, link=url),
                                         Span("two", bold=True, link=url)]])
    assert requests[3:] == [
        {"updateTextStyle": {
            "range": {"startIndex": 16, "endIndex": 19},
            "textStyle": {"bold": True, "italic": True, "link": {"url": url}},
            "fields": "bold,italic,link"}},
        {"updateTextStyle": {
            "range": {"startIndex": 19, "endIndex": 22},
            "textStyle": {"bold": True, "link": {"url": url}}, "fields": "bold,link"}},
    ]


# --- reading a document back as paragraphs (check-weekly-email) ----------------------------

def test_a_documents_paragraphs_are_read_back_without_their_line_ends():
    from googledocstools.markup import Span
    from tests.conftest import described

    assert document.paragraphs(described(["Hello.", "Second one."])) == [
        document.Paragraph("NORMAL_TEXT", [Span("Hello.")]),
        document.Paragraph("NORMAL_TEXT", [Span("Second one.")]),
    ]


def test_each_piece_keeps_its_bold_italic_and_link():
    from googledocstools.markup import Span
    from tests.conftest import described

    url = "https://example.org"
    doc = described([[("Plain ", {}), ("bold", {"bold": True}), (" it ", {"italic": True}),
                      ("both", {"bold": True, "italic": True, "link": {"url": url}}),
                      (" end", {"underline": True})]])
    assert document.paragraphs(doc)[0].spans == [
        Span("Plain "), Span("bold", bold=True), Span(" it ", italic=True),
        Span("both", bold=True, italic=True, link=url), Span(" end")]


def test_a_paragraphs_kind_is_its_named_style():
    from tests.conftest import Styled, described

    doc = described([Styled("TITLE", "The issue"), Styled("HEADING_2", "Briefly…"), "Text."])
    assert [paragraph.kind for paragraph in document.paragraphs(doc)] == [
        "TITLE", "HEADING_2", "NORMAL_TEXT"]


def test_a_horizontal_rule_is_a_paragraph_of_its_own_kind_with_no_text():
    from tests.conftest import RULE, described

    doc = described(["Above.", RULE, "Below."])
    assert document.paragraphs(doc)[1] == document.Paragraph("RULE", [])
    assert len(document.paragraphs(doc)) == 3


def test_a_rule_and_text_in_one_paragraph_are_a_rule_and_then_the_text():
    from googledocstools.markup import Span
    from tests.conftest import RuleThen, described

    doc = described(["Above.", RuleThen([("Briefly…", {"bold": True})]), "Below."])
    assert document.paragraphs(doc) == [
        document.Paragraph("NORMAL_TEXT", [Span("Above.")]),
        document.Paragraph("RULE", []),
        document.Paragraph("NORMAL_TEXT", [Span("Briefly…", bold=True)]),
        document.Paragraph("NORMAL_TEXT", [Span("Below.")]),
    ]


def test_text_before_a_rule_and_a_picture_after_it_in_one_paragraph_are_all_kept():
    from googledocstools.markup import Span

    doc = {"body": {"content": [{"paragraph": {"elements": [
        {"textRun": {"content": "Before", "textStyle": {}}},
        {"horizontalRule": {}},
        {"inlineObjectElement": {"inlineObjectId": "pic"}},
        {"textRun": {"content": "After\n", "textStyle": {}}}]}}]},
        "inlineObjects": {"pic": {"inlineObjectProperties": {"embeddedObject": {
            "imageProperties": {"sourceUri": "https://u.example/a.png"}}}}}}
    assert document.paragraphs(doc) == [
        document.Paragraph("NORMAL_TEXT", [Span("Before")]),
        document.Paragraph("RULE", []),
        document.Paragraph("NORMAL_TEXT", [Span("After")], ("https://u.example/a.png",)),
    ]


def test_paragraphs_inside_a_table_of_contents_are_read_in_their_place():
    from googledocstools.markup import Span

    line = {"paragraph": {"elements": [{"textRun": {"content": "In contents\n",
                                                    "textStyle": {}}}]}}
    doc = {"body": {"content": [{"tableOfContents": {"content": [line]}}]}}
    assert document.paragraphs(doc) == [document.Paragraph("NORMAL_TEXT", [Span("In contents")])]


def test_an_element_that_cannot_be_written_is_a_note_paragraph_after_its_paragraph():
    from googledocstools.markup import Span

    def paragraph(*elements):
        return {"paragraph": {"elements": list(elements)}}

    text = {"textRun": {"content": "Ask \n", "textStyle": {}}}
    doc = {"body": {"content": [
        paragraph(text, {"person": {"personProperties": {"name": "A. Person"}}}),
        paragraph({"richLink": {}}, {"equation": {}}, {"autoText": {}}, {"footnoteReference": {}}),
        paragraph({"pageBreak": {}}, {"columnBreak": {}}),
    ]}}
    assert document.paragraphs(doc) == [
        document.Paragraph("NORMAL_TEXT", [Span("Ask ")]),
        document.Paragraph("UNWRITTEN", [Span("a person chip")]),
        document.Paragraph("NORMAL_TEXT", []),
        document.Paragraph("UNWRITTEN", [Span("a link chip")]),
        document.Paragraph("UNWRITTEN", [Span("an equation")]),
        document.Paragraph("UNWRITTEN", [Span("automatic text, such as a page number")]),
        document.Paragraph("UNWRITTEN", [Span("a footnote reference")]),
        document.Paragraph("NORMAL_TEXT", []),
    ]


def test_paragraphs_inside_a_table_are_read_in_their_place():
    from googledocstools.markup import Span
    from tests.conftest import described

    doc = described(["Above."])
    cell = {"content": [{"paragraph": {"elements": [
        {"textRun": {"content": "In the table.\n", "textStyle": {"bold": True}}}]}}]}
    doc["body"]["content"].append({"table": {"tableRows": [{"tableCells": [cell]}]}})
    doc["body"]["content"].append({"paragraph": {"elements": [
        {"textRun": {"content": "Below.\n"}}]}})
    assert [paragraph.spans for paragraph in document.paragraphs(doc)] == [
        [Span("Above.")], [Span("In the table.", bold=True)], [Span("Below.")]]


# --- a picture where a placeholder is (insert-weekly-image) ---------------------------------

def test_a_placeholder_that_is_its_whole_paragraph_is_alone_in_it():
    from tests.conftest import described

    doc = described(["Above.", "[PICTURE]", "Below."])
    ((start, end),) = document.find(doc, "[PICTURE]")
    assert document.alone(doc, start, end) is True


@pytest.mark.parametrize("paragraph", [
    "See the [PICTURE]", "[PICTURE] and a note", "a [PICTURE] b",
    [("Bold lead-in ", {"bold": True}), ("[PICTURE]", {})],
])
def test_a_placeholder_with_words_beside_it_is_not_alone(paragraph):
    from tests.conftest import described

    doc = described(["Above.", paragraph, "Below."])
    ((start, end),) = document.find(doc, "[PICTURE]")
    assert document.alone(doc, start, end) is False


def test_spaces_round_the_placeholder_do_not_stop_it_being_alone():
    from tests.conftest import described

    doc = described(["Above.", [("  ", {"bold": True}), ("[PICTURE]", {}), (" \t", {})]])
    ((start, end),) = document.find(doc, "[PICTURE]")
    assert document.alone(doc, start, end) is True


def test_a_placeholder_alone_in_a_table_cell_is_alone_and_one_beside_a_picture_is_not():
    cell = {"startIndex": 20, "endIndex": 31, "content": [{
        "startIndex": 21, "endIndex": 31, "paragraph": {"elements": [
            {"startIndex": 21, "endIndex": 31, "textRun": {"content": "[PICTURE]\n"}}]}}]}
    picture = {"startIndex": 40, "endIndex": 41, "inlineObjectElement": {"inlineObjectId": "p"}}
    doc = {"body": {"content": [
        {"startIndex": 18, "endIndex": 32, "table": {"tableRows": [{"tableCells": [cell]}]}},
        {"startIndex": 40, "endIndex": 51, "paragraph": {"elements": [
            picture, {"startIndex": 41, "endIndex": 51, "textRun": {"content": "[PICTURE]\n"}}]}},
    ]}}
    assert document.alone(doc, 21, 30) is True
    assert document.alone(doc, 41, 50) is False


def test_a_position_that_is_in_no_paragraph_is_not_alone_in_one():
    from tests.conftest import described

    assert document.alone(described(["Only this."]), 500, 509) is False


def test_the_change_for_a_picture_takes_the_placeholder_out_and_puts_the_picture_in():
    assert document.picture(40, 49, "https://example.org/a b.png?x=1&y='2'", 220, []) == [
        {"deleteContentRange": {"range": {"startIndex": 40, "endIndex": 49}}},
        {"insertInlineImage": {
            "location": {"index": 40}, "uri": "https://example.org/a b.png?x=1&y='2'",
            "objectSize": {"width": {"magnitude": 220, "unit": "PT"}}}},
    ]


def test_a_linked_picture_is_made_a_link_straight_after_it_goes_in_and_before_its_caption():
    from googledocstools.markup import Span

    address = "https://v.example/watch?v=a&t=1s#x é"
    requests = document.picture(40, 49, "https://example.org/a.png", 220, [[Span("Hi")]],
                                link=address)
    assert requests[2] == {"updateTextStyle": {
        "range": {"startIndex": 40, "endIndex": 41}, "textStyle": {"link": {"url": address}},
        "fields": "link"}}
    assert "insertText" in requests[3]


def test_a_picture_with_no_link_gets_no_link_request():
    requests = document.picture(40, 49, "https://example.org/a.png", 220, [], link=None)
    assert len(requests) == 2


def test_a_caption_follows_the_picture_as_new_paragraphs_cleared_and_marked():
    from googledocstools.markup import Span

    url = "https://example.org/photographer"
    requests = document.picture(40, 49, "https://example.org/a.png", 220, [
        [Span("Photo: "), Span("Sven", link=url)], [Span("CC BY-SA", bold=True)]])
    # The picture takes position 40. Then a line break (41), "Photo: " (42 to 49), "Sven"
    # (49 to 53), a line break (53), "CC BY-SA" (54 to 62).
    assert requests[2:] == [
        {"insertText": {"location": {"index": 41}, "text": "\nPhoto: Sven\nCC BY-SA"}},
        {"updateTextStyle": {"range": {"startIndex": 41, "endIndex": 62}, "textStyle": {},
                             "fields": document.CLEARED}},
        {"updateTextStyle": {"range": {"startIndex": 49, "endIndex": 53},
                             "textStyle": {"link": {"url": url}}, "fields": "link"}},
        {"updateTextStyle": {"range": {"startIndex": 54, "endIndex": 62},
                             "textStyle": {"bold": True}, "fields": "bold"}},
    ]


def test_a_centred_picture_has_its_paragraph_centred_and_no_other():
    requests = document.picture(40, 49, "https://example.org/a.png", 220, [], centred=True)
    # The picture is the one position at 40: the request reaches its paragraph and no further.
    assert requests[2:] == [{"updateParagraphStyle": {
        "range": {"startIndex": 40, "endIndex": 41},
        "paragraphStyle": {"alignment": "CENTER"}, "fields": "alignment"}}]
    assert document.picture(40, 49, "https://example.org/a.png", 220, [], centred=False)[2:] == []


def test_a_centred_pictures_caption_is_centred_with_it():
    from googledocstools.markup import Span

    requests = document.picture(40, 49, "https://example.org/a.png", 220,
                                [[Span("Photo: Sven")], [Span("CC BY-SA")]], centred=True)
    # The picture is 40; then a break, "Photo: Sven", a break and "CC BY-SA" run to 62.
    assert requests[-1] == {"updateParagraphStyle": {
        "range": {"startIndex": 40, "endIndex": 62},
        "paragraphStyle": {"alignment": "CENTER"}, "fields": "alignment"}}


# --- Request 6: highlighted text that is not a link ----------------------------------------

YELLOW = {"backgroundColor": {"color": {"rgbColor": {"red": 1, "green": 1}}}}


def test_highlighted_text_is_found_with_its_paragraphs_text():
    from tests.conftest import described

    doc = described(["Plain.", [("See the ", {}), ("Hammurabi code", YELLOW), (" here.", {})]])
    assert document.highlights(doc) == [("Hammurabi code", "See the Hammurabi code here.")]


def test_a_highlighted_link_or_highlighted_spaces_or_a_cleared_highlight_is_not_listed():
    from tests.conftest import described

    linked = dict(YELLOW, link={"url": "https://example.org"})
    doc = described([[("a ", {}), ("linked", linked), ("   ", YELLOW), ("x", {"backgroundColor": {}}),
                      (" and ", {}), ("this", YELLOW)]])
    assert document.highlights(doc) == [("this", "a linked   x and this")]


def test_highlighted_pieces_side_by_side_are_one_stretch_and_separate_ones_are_separate():
    from tests.conftest import described

    doc = described([[("Ham", YELLOW), ("murabi", dict(YELLOW, bold=True)), (" managed with ", {}),
                      ("282 laws", YELLOW)]])
    whole = "Hammurabi managed with 282 laws"
    assert document.highlights(doc) == [("Hammurabi", whole), ("282 laws", whole)]


# --- the size of the text at a place, for a caption one point smaller ------------------------

def test_the_size_of_text_is_the_size_set_on_it():
    from tests.conftest import described

    big = {"fontSize": {"magnitude": 14, "unit": "PT"}}
    doc = described(["Plain.", [("[PIC", big), ("TURE]", {})]])
    ((start, _),) = document.find(doc, "[PICTURE]")
    assert document.text_size(doc, start) == 14


def test_text_with_no_size_of_its_own_has_the_size_its_paragraphs_style_gives():
    from tests.conftest import Styled, described

    doc = described(["[PICTURE]", Styled("HEADING_2", "[HEADING PICTURE]")])
    doc["namedStyles"] = {"styles": [
        {"namedStyleType": "NORMAL_TEXT", "textStyle": {"fontSize": {"magnitude": 12, "unit": "PT"}}},
        {"namedStyleType": "HEADING_2", "textStyle": {"fontSize": {"magnitude": 16, "unit": "PT"}}},
    ]}
    assert document.text_size(doc, 1) == 12
    ((start, _),) = document.find(doc, "[HEADING PICTURE]")
    assert document.text_size(doc, start) == 16


def test_where_the_document_names_no_size_at_all_it_is_taken_to_be_11_points():
    from tests.conftest import described

    doc = described(["[PICTURE]"])
    assert document.text_size(doc, 1) == 11
    doc["namedStyles"] = {"styles": [{"namedStyleType": "NORMAL_TEXT", "textStyle": {}}]}
    assert document.text_size(doc, 1) == 11


def test_a_captions_size_is_set_over_the_caption_and_not_the_picture():
    from googledocstools.markup import Span

    requests = document.picture(40, 49, "https://example.org/a.png", 220,
                                [[Span("Photo: Sven")], [Span("CC BY-SA")]],
                                centred=True, caption_size=10)
    # The picture is 40; the caption, with its two line breaks, runs from 41 to 62.
    assert {"updateTextStyle": {
        "range": {"startIndex": 41, "endIndex": 62},
        "textStyle": {"fontSize": {"magnitude": 10, "unit": "PT"}},
        "fields": "fontSize"}} in requests
    assert requests[-1]["updateParagraphStyle"]["range"] == {"startIndex": 40, "endIndex": 62}
    without = document.picture(40, 49, "https://example.org/a.png", 220,
                               [[Span("Photo: Sven")]], centred=True)
    assert not any("fontSize" in request.get("updateTextStyle", {}).get("fields", "")
                   for request in without)


def test_the_layout_gives_each_paragraphs_text_its_alignment_and_how_many_pictures_it_has():
    from tests.conftest import PICTURE, Styled, described

    doc = described([
        "Plain.",
        Styled("NORMAL_TEXT", [(PICTURE, {})], alignment="CENTER"),
        Styled("NORMAL_TEXT", [("Photo: ", BOLD), ("Someone", {})], alignment="CENTER"),
        Styled("HEADING_2", "Last"),
    ])
    assert document.layout(doc) == [
        document.Block("Plain.", None, 0), document.Block("", "CENTER", 1, ("",)),
        document.Block("Photo: Someone", "CENTER", 0), document.Block("Last", None, 0)]


def test_the_layout_gives_where_each_picture_came_from_and_nothing_for_one_that_does_not_say():
    from tests.conftest import PICTURE, Styled, described

    doc = described([
        Styled("NORMAL_TEXT", [(PICTURE, {"source": "https://example.org/a.png"})]),
        Styled("NORMAL_TEXT", [(PICTURE, {})]),
    ])
    assert document.layout(doc) == [
        document.Block("", None, 1, ("https://example.org/a.png",)),
        document.Block("", None, 1, ("",))]


def test_the_layout_gives_each_pictures_link_as_google_keeps_it_and_nothing_where_none():
    from tests.conftest import PICTURE, Styled, described

    doc = described([
        Styled("NORMAL_TEXT", [(PICTURE, {"link": {"url": "https://v.example/w?v=1&t=2"}}),
                               (PICTURE, {})]),
        Styled("NORMAL_TEXT", [(PICTURE, {})]),
    ])
    assert doc["body"]["content"][1]["paragraph"]["elements"][0]["inlineObjectElement"][
        "textStyle"] == {"link": {"url": "https://v.example/w?v=1&t=2"}}
    assert document.layout(doc) == [
        document.Block("", None, 2, ("", ""), ("https://v.example/w?v=1&t=2", "")),
        document.Block("", None, 1, ("",))]


YELLOW = {"backgroundColor": {"color": {"rgbColor": {"red": 1, "green": 1}}}}


def test_a_highlighted_piece_that_is_not_a_link_is_marked_in_the_paragraphs():
    from tests.conftest import described

    doc = described([[("See ", {}), ("Hammurabi", YELLOW), (" and ", {}),
                      ("this", dict(YELLOW, link={"url": "https://example.org"}))]])
    assert [(span.text, span.highlight) for span in document.paragraphs(doc)[0].spans] == [
        ("See ", False), ("Hammurabi", True), (" and ", False), ("this", False)]


def test_a_paragraph_that_holds_pictures_says_where_each_came_from_and_others_hold_none():
    from tests.conftest import PICTURE, Styled, described

    doc = described([
        Styled("NORMAL_TEXT", [(PICTURE, {"source": "https://example.org/a.png"})]),
        "Text.",
        Styled("NORMAL_TEXT", [(PICTURE, {}), ("", {}), (PICTURE, {"source": "https://x.example/b"})]),
    ])
    assert [paragraph.pictures for paragraph in document.paragraphs(doc)] == [
        ("https://example.org/a.png",), (), ("", "https://x.example/b")]


# --- how far a highlight reaches around some text (Request 23) ------------------------------

def test_the_highlight_a_placeholder_is_part_of_reaches_on_after_it_within_its_paragraph():
    from tests.conftest import described

    marked = "[note] livestream in November"
    doc = described(["Before.", [("At my ", {}), (marked, YELLOW), (", I'll show it.", {})]])
    start = 1 + len("Before.\n") + len("At my ")
    end = start + len("[note] livestream")
    assert document.reach(doc, start, end) == (start, start + len(marked))


def test_the_highlight_a_placeholder_is_part_of_reaches_back_before_it():
    from tests.conftest import described

    doc = described([[("Plain ", {}), ("Hammurabi's ", YELLOW), ("[note]", YELLOW), (" end.", {})]])
    start = 1 + len("Plain Hammurabi's ")
    assert document.reach(doc, start, start + len("[note]")) == (
        1 + len("Plain "), start + len("[note]"))


def test_the_reach_of_a_highlight_counts_an_emoji_at_its_end_as_google_does():
    from tests.conftest import described

    marked = "[note] for 🐿"  # the squirrel alone, two units, with no variation mark after it
    doc = described([[(marked, YELLOW), (" after.", {})]])
    assert document.reach(doc, 1, 1 + len("[note]")) == (1, 1 + document.units(marked))


def test_a_highlight_only_beside_the_text_is_not_its_reach():
    from tests.conftest import described

    doc = described([[("Ham ", YELLOW), ("[note]", {}), (" more", YELLOW)]])
    start = 1 + len("Ham ")
    assert document.reach(doc, start, start + len("[note]")) == (start, start + len("[note]"))


def test_the_reach_of_a_highlight_stops_at_its_paragraphs_end_and_at_a_picture():
    from tests.conftest import PICTURE, described

    doc = described([[("Before", YELLOW)], [("[note] on", YELLOW)], [("next", YELLOW)],
                     [("x ", YELLOW), (PICTURE + "[pic] y", YELLOW)]])
    start = 1 + len("Before\n")
    assert document.reach(doc, start, start + len("[note]")) == (start, start + len("[note] on"))
    pic = 1 + len("Before\n[note] on\nnext\nx ") + 1
    assert document.reach(doc, pic, pic + len("[pic]")) == (pic, pic + len("[pic] y"))


@pytest.mark.parametrize("runs,expected", [
    ([("a ", {}), (" in November", YELLOW), (", I", {})], True),
    ([("a ", {}), (" in", {}), (" November", YELLOW), (", I", {})], True),
    ([("a ", YELLOW), (" in November", {}), (", I", YELLOW)], False),
    ([("a ", {}), (" in November", {"backgroundColor": {}}), (", I", {})], False),
])
def test_text_is_highlighted_when_any_of_it_is(runs, expected):
    from tests.conftest import described

    doc = described([runs])
    start = 1 + len("a ")
    assert document.highlighted(doc, start, start + len(" in November")) is expected


def test_the_text_between_two_positions_is_read_across_pieces_as_google_counts_them():
    from tests.conftest import described

    doc = described(["🐿 first", [("At my ", {}), ("live", BOLD), ("stream in", YELLOW), (" May", {})]])
    start = 1 + document.units("🐿 first\nAt my li")
    assert document.text_at(doc, start, start + len("vestream in M")) == "vestream in M"


# --- a picture's link (Request 28) -------------------------------------------------------------

def test_every_picture_is_listed_in_order_with_its_place_address_link_and_what_follows_it():
    from tests.conftest import PICTURE, described

    doc = described([
        "Intro.",
        [(PICTURE, {"source": "https://img.example/a.jpg"})],
        "",
        "Image: the video, and more words than eight in all of it",
        [(PICTURE, {"link": {"url": "https://v.example/?a=1&b=2"}}), (PICTURE, {})],
        [(PICTURE, {})],
    ])
    assert document.picture_places(doc) == [
        document.Place(8, "https://img.example/a.jpg", "",
                       "Image: the video, and more words than eight in all of it"),
        document.Place(68, "", "https://v.example/?a=1&b=2", ""),
        document.Place(69, "", "", ""),
        document.Place(71, "", "", ""),
    ]


def test_a_document_with_no_pictures_has_no_places():
    from tests.conftest import described

    assert document.picture_places(described(["Just words."])) == []


def test_taking_a_pictures_link_off_sets_an_empty_style_for_the_link_alone():
    assert document.picture_link(40, None) == {"updateTextStyle": {
        "range": {"startIndex": 40, "endIndex": 41}, "textStyle": {}, "fields": "link"}}


def test_the_paragraphs_give_each_pictures_link_and_none_where_no_picture_is_a_link():
    from tests.conftest import PICTURE, described

    doc = described([[(PICTURE, {}), (PICTURE, {"link": {"url": "https://v.example/"}})],
                     [(PICTURE, {})]])
    found = document.paragraphs(doc)
    assert found[0].links == ("", "https://v.example/") and found[1].links == ()



# --- open question 48: what a paragraph looks like, beyond its words --------------------------

UNDERLINE = {"underline": True}
STRUCK = {"strikethrough": True}
GEORGIA = {"weightedFontFamily": {"fontFamily": "Georgia", "weight": 400}}


def size(points):
    return {"fontSize": {"magnitude": points, "unit": "PT"}}


def test_a_paragraphs_look_is_its_underline_strikethrough_font_and_size_stretches():
    from tests.conftest import described

    doc = described([[("Plain ", {}), ("under", UNDERLINE), (" and ", {}), ("struck", STRUCK),
                      (" in ", size(13)), ("Georgia", dict(GEORGIA, **size(11)))]])
    assert document.looks(doc) == [("Plain under and struck in Georgia", {
        "underline": [[6, 11]], "strikethrough": [[16, 22]], "font": [[26, 33, "Georgia"]],
        "size": [[22, 26, 13], [26, 33, 11]]})]


def test_one_look_split_between_pieces_is_one_stretch_and_bold_italic_links_are_not_part_of_it():
    from tests.conftest import described

    doc = described([[("one ", UNDERLINE), ("two", dict(UNDERLINE, bold=True)),
                      (" three", {"italic": True, "link": {"url": "https://example.org/"}})],
                     "Nothing to see here."])
    assert document.looks(doc) == [("one two three", {"underline": [[0, 7]]}),
                                   ("Nothing to see here.", {})]


def test_a_paragraphs_pictures_are_each_ones_source_and_size_and_their_links_if_any():
    from tests.conftest import PICTURE, RULE, described

    doc = described([
        [(PICTURE, {"source": "https://u.example/a.png", "size": (283.5, 150)}),
         (PICTURE, {"link": {"url": "https://v.example/w"}})],
        RULE, "",
        [("Words and ", {}), (PICTURE, {"source": "https://u.example/b.png"}), (" more", {})]])
    assert document.looks(doc) == [
        ("", {"picture": [["https://u.example/a.png", 283.5, 150], ["", None, None]],
              "link": ["", "https://v.example/w"]}),
        ("Words and  more", {"picture": [["https://u.example/b.png", None, None]]})]
