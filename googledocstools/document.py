"""A Google Doc as the Docs API describes it: finding text in it, and building a change to it."""
from collections import namedtuple

from googledocstools.markup import Span

Paragraph = namedtuple("Paragraph", "kind spans pictures links mark", defaults=((), (), ""))


def units(text):
    """The length of text as the Docs API counts it: in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def find(described, placeholder):
    """Where some text is in a document's body: a list of (start, end) positions.

    A paragraph's text is read as a whole, so text split between differently styled pieces is
    found all the same.
    """
    found = []

    def search(begins, text):
        offset = text.find(placeholder)
        while offset >= 0:
            start = begins + units(text[:offset])
            found.append((start, start + units(placeholder)))
            offset = text.find(placeholder, offset + len(placeholder))

    def walk(content):
        for structural in content:
            for row in structural.get("table", {}).get("tableRows", []):
                for cell in row.get("tableCells", []):
                    walk(cell.get("content", []))
            begins, pieces = None, []  # a stretch of text with nothing else in between
            for element in structural.get("paragraph", {}).get("elements", []):
                if "textRun" not in element:
                    search(begins, "".join(pieces))
                    begins, pieces = None, []
                    continue
                if begins is None:
                    begins = element["startIndex"]
                pieces.append(element["textRun"].get("content", ""))
            search(begins, "".join(pieces))

    walk(described["body"]["content"])
    return found


CLEARED = ("bold,italic,underline,strikethrough,smallCaps,backgroundColor,foregroundColor,"
           "baselineOffset,link")


def _text(index, paragraphs, new_paragraph_first=False):
    """The requests that put paragraphs of Spans in at index, plain except where marked.

    With new_paragraph_first the text starts on a new line, as a caption under a picture does.
    """
    text = "\n".join("".join(span.text for span in paragraph) for paragraph in paragraphs)
    if new_paragraph_first:
        text = "\n" + text
    requests = [
        {"insertText": {"location": {"index": index}, "text": text}},
        # Named and left unset: each goes back to what the paragraph gives. Google gives
        # inserted text the whole look of the first character it replaced; this takes that
        # look off again, all but the font and its size, which are left on purpose.
        {"updateTextStyle": {"range": {"startIndex": index, "endIndex": index + units(text)},
                             "textStyle": {}, "fields": CLEARED}},
    ]
    position = index + (1 if new_paragraph_first else 0)
    for number, paragraph in enumerate(paragraphs):
        if number:
            position += 1  # the line break between paragraphs
        for span in paragraph:
            length = units(span.text)
            style = {}
            if span.bold:
                style["bold"] = True
            if span.italic:
                style["italic"] = True
            if span.link:
                style["link"] = {"url": span.link}
            if style:
                requests.append({"updateTextStyle": {
                    "range": {"startIndex": position, "endIndex": position + length},
                    "textStyle": style, "fields": ",".join(style)}})
            position += length
    return requests


def change(start, end, paragraphs):
    """The requests that put paragraphs of Spans where the text from start to end now is."""
    return [{"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}}] + _text(
        start, paragraphs)


def unmark(start, end):
    """The request that takes the highlight (background colour) off the text from start to end."""
    return {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end},
                                "textStyle": {}, "fields": "backgroundColor"}}


def part_of(placeholder, text, start):
    """Where text is inside a placeholder that begins at start: (its first, its end) position."""
    first = start + units(placeholder[:placeholder.index(text)])
    return first, first + units(text)


def link(start, end, address, part=None):
    """The requests that make text a link and take the highlight off the text from start to end.

    The whole of it becomes the link, or only part, a (first, end) inside it. Style only: no
    text is deleted or put in, so what the text looked like otherwise stays.
    """
    first, last = part or (start, end)
    return [
        {"updateTextStyle": {"range": {"startIndex": start, "endIndex": end},
                             "textStyle": {}, "fields": "backgroundColor"}},
        {"updateTextStyle": {"range": {"startIndex": first, "endIndex": last},
                             "textStyle": {"link": {"url": address}}, "fields": "link"}},
    ]


def _sources(described, elements):
    """Where each picture among a paragraph's elements came from; "" for one that does not say."""
    return tuple(
        described.get("inlineObjects", {}).get(
            element["inlineObjectElement"]["inlineObjectId"], {}).get(
            "inlineObjectProperties", {}).get("embeddedObject", {}).get(
            "imageProperties", {}).get("sourceUri", "")
        for element in elements if "inlineObjectElement" in element)


# What a paragraph may hold that is not text and not a picture, and what it is called when it
# cannot be written.
UNWRITABLE = {
    "person": "a person chip",
    "richLink": "a link chip",
    "equation": "an equation",
    "autoText": "automatic text, such as a page number",
    "footnoteReference": "a footnote reference",
}


def _spans(elements):
    """The pieces of text among a paragraph's elements, each with how it looks."""
    spans = []
    for element in elements:
        run = element.get("textRun", {})
        style = run.get("textStyle", {})
        text = run.get("content", "").rstrip("\n")
        if text:
            marked = bool(style.get("backgroundColor", {}).get("color") and "link" not in style)
            spans.append(Span(text, bool(style.get("bold")), bool(style.get("italic")),
                              style.get("link", {}).get("url"), marked))
    return spans


ORDERED = ("DECIMAL", "ZERO_DECIMAL", "UPPER_ALPHA", "ALPHA", "UPPER_ROMAN", "ROMAN")


def _marker(described):
    """A function giving what goes before each list item in turn, from its paragraph's bullet
    ("" for no bullet): two spaces per level, then a dash, or the item's number in figures.

    A list's numbers go on across whatever stands between its items, as Google counts them, and
    an item starts the levels under it again. A list or level the document does not describe is
    taken for bullets.
    """
    counted = {}  # (the list's id, its level) -> the last number given

    def mark(bullet):
        if bullet is None:
            return ""
        list_id, level = bullet.get("listId"), bullet.get("nestingLevel", 0)
        for key in [key for key in counted if key[0] == list_id and key[1] > level]:
            del counted[key]
        levels = described.get("lists", {}).get(list_id, {}).get("listProperties", {}).get(
            "nestingLevels", [])
        glyph = levels[level] if level < len(levels) else {}
        if glyph.get("glyphType") not in ORDERED:
            return "  " * level + "- "
        first = glyph.get("startNumber") or 1
        counted[list_id, level] = counted.get((list_id, level), first - 1) + 1
        return "%s%d. " % ("  " * level, counted[list_id, level])

    return mark


def paragraphs(described):
    """The paragraphs of a document's body, in order, each with its kind, pieces and pictures,
    and a list item with its mark.

    A horizontal rule is a paragraph of its own kind, RULE, with no text. Google may hold a rule
    and text in one paragraph; that is read as the rule and then the text, so no text is lost.
    Something that cannot be written (UNWRITABLE) is a paragraph of the kind UNWRITTEN after its
    own paragraph, its one piece saying what it is, so it is never left out silently.
    """
    found = []
    marked = _marker(described)

    def walk(content):
        for structural in content:
            for row in structural.get("table", {}).get("tableRows", []):
                for cell in row.get("tableCells", []):
                    walk(cell.get("content", []))
            walk(structural.get("tableOfContents", {}).get("content", []))
            if "paragraph" not in structural:
                continue
            elements = structural["paragraph"]["elements"]
            kind = structural["paragraph"].get("paragraphStyle", {}).get("namedStyleType")
            mark = marked(structural["paragraph"].get("bullet"))
            stretches = [[]]  # what lies between the rules: the text of one paragraph each
            for element in elements:
                if "horizontalRule" in element:
                    stretches.append([])
                else:
                    stretches[-1].append(element)
            for number, stretch in enumerate(stretches):
                if number:
                    found.append(Paragraph("RULE", []))
                spans, pictures = _spans(stretch), _sources(described, stretch)
                if spans or pictures or len(stretches) == 1:
                    found.append(Paragraph(kind or "NORMAL_TEXT", spans, pictures,
                                           _links(stretch), mark))
                    mark = ""
            for element in elements:
                for key, what in UNWRITABLE.items():
                    if key in element:
                        found.append(Paragraph("UNWRITTEN", [Span(what)]))

    walk(described["body"]["content"])
    return found


def _paragraphs_in(content):
    """Every paragraph in some content, those inside tables too, as the API describes them."""
    for structural in content:
        for row in structural.get("table", {}).get("tableRows", []):
            for cell in row.get("tableCells", []):
                yield from _paragraphs_in(cell.get("content", []))
        if "paragraph" in structural:
            yield structural


Block = namedtuple("Block", "text alignment pictures sources links", defaults=((), ()))


def _links(elements):
    """Each picture's link among a paragraph's elements ("" for none); () if none is a link."""
    links = tuple(element["inlineObjectElement"].get("textStyle", {}).get("link", {}).get(
        "url", "") for element in elements if "inlineObjectElement" in element)
    return links if any(links) else ()


def layout(described):
    """Each paragraph of the body, in order: its text, its alignment (None if never set), how
    many pictures it holds, where each came from ("" for one that does not say), and each one's
    link (() when none of them is a link).
    Paragraphs inside tables are read in their place."""
    blocks = []
    for structural in _paragraphs_in(described["body"]["content"]):
        paragraph = structural["paragraph"]
        text = "".join(element.get("textRun", {}).get("content", "")
                       for element in paragraph["elements"]).rstrip("\n")
        sources = _sources(described, paragraph["elements"])
        blocks.append(Block(text, paragraph.get("paragraphStyle", {}).get("alignment"),
                            len(sources), sources, _links(paragraph["elements"])))
    return blocks


def _stretch(stretches, start, end, *value):
    """Add start to end (with its value, if it has one) to stretches, joining it to the last if
    they meet and have the same value."""
    if stretches and stretches[-1][1] == start and stretches[-1][2:] == list(value):
        stretches[-1][1] = end
    else:
        stretches.append([start, end, *value])


def looks(described):
    """What each paragraph of the body that holds words or pictures looks like beyond its words:
    [(its text, {kind: …})], in order, paragraphs in tables in their place.

    The kinds, each left out when there is none: "underline" and "strikethrough", [[first, end]]
    stretches of the text; "font" and "size", [[first, end, the font or the size in points]];
    "picture", [[its source address, its width, its height]] for each picture (None where Google
    does not say); "link", each picture's link ("" for none), only when one is a link. Bold,
    italic and the links of words are not here: the text as check-weekly-email writes it shows
    them already."""
    found = []
    for structural in _paragraphs_in(described["body"]["content"]):
        elements = structural["paragraph"]["elements"]
        text, look = "", {}
        for element in elements:
            run = element.get("textRun")
            if run is None:
                continue
            piece = run.get("content", "")
            style = run.get("textStyle", {})
            start, end = len(text), len(text) + len(piece.rstrip("\n"))
            text += piece
            if start == end:
                continue
            for kind in ("underline", "strikethrough"):
                if style.get(kind):
                    _stretch(look.setdefault(kind, []), start, end)
            family = style.get("weightedFontFamily", {}).get("fontFamily")
            if family:
                _stretch(look.setdefault("font", []), start, end, family)
            points = style.get("fontSize", {}).get("magnitude")
            if points is not None:
                _stretch(look.setdefault("size", []), start, end, points)
        text = text.rstrip("\n")
        pictured = [element for element in elements if "inlineObjectElement" in element]
        if pictured:
            objects = described.get("inlineObjects", {})
            look["picture"] = []
            for element in pictured:
                embedded = objects.get(element["inlineObjectElement"]["inlineObjectId"], {}).get(
                    "inlineObjectProperties", {}).get("embeddedObject", {})
                measured = embedded.get("size", {})
                look["picture"].append([
                    embedded.get("imageProperties", {}).get("sourceUri", ""),
                    measured.get("width", {}).get("magnitude"),
                    measured.get("height", {}).get("magnitude")])
            if _links(elements):
                look["link"] = list(_links(elements))
        if text or pictured:
            found.append((text, look))
    return found


Place = namedtuple("Place", "index source link after")


def picture_places(described):
    """Every picture in the body, in order, as a Place: its index, where it came from ("" if it
    does not say), its link ("" for none), and the text of the next paragraph that holds text or
    a picture ("" if that holds a picture, or there is none)."""
    structurals = list(_paragraphs_in(described["body"]["content"]))
    blocks = layout(described)
    places = []
    for number, structural in enumerate(structurals):
        elements = structural["paragraph"]["elements"]
        later = [block for block in blocks[number + 1:] if block.text.strip() or block.pictures]
        after = later[0].text if later and not later[0].pictures else ""
        pictured = [element for element in elements if "inlineObjectElement" in element]
        links = _links(elements) or ("",) * len(pictured)
        for element, source, link in zip(pictured, _sources(described, elements), links):
            places.append(Place(element["startIndex"], source, link, after))
    return places


def alone(described, start, end):
    """Whether the text from start to end is the only thing in its paragraph but spaces."""
    for structural in _paragraphs_in(described["body"]["content"]):
        if structural["startIndex"] <= start < structural["endIndex"]:
            beside = ""
            for element in structural["paragraph"]["elements"]:
                if "textRun" not in element:
                    return False  # a picture or the like shares the paragraph
                at = element["startIndex"]
                for character in element["textRun"].get("content", ""):
                    if not start <= at < end:
                        beside += character
                    at += units(character)
            return not beside.strip()
    return False


def picture(start, end, uri, width, caption, centred=False, caption_size=None, link=None):
    """The requests that put a picture, and a caption under it, where start to end now is.

    With a link, the picture itself is made a link (its one position), before the caption."""
    requests = [
        {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}},
        {"insertInlineImage": {
            "location": {"index": start}, "uri": uri,
            "objectSize": {"width": {"magnitude": width, "unit": "PT"}}}},
    ]
    if link is not None:
        requests.append(picture_link(start, link))
    last = start + 1  # the picture is one wide
    if caption:
        text = _text(last, caption, new_paragraph_first=True)
        requests += text
        last += units(text[0]["insertText"]["text"])
        if caption_size is not None:
            requests.append({"updateTextStyle": {
                "range": {"startIndex": start + 1, "endIndex": last},
                "textStyle": {"fontSize": {"magnitude": caption_size, "unit": "PT"}},
                "fields": "fontSize"}})
    if centred:
        # From the picture to the end of its caption: every paragraph the range touches.
        requests.append({"updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": last},
            "paragraphStyle": {"alignment": "CENTER"}, "fields": "alignment"}})
    return requests


def picture_link(index, link):
    """The request that makes the picture at index a link, or takes its link off (link None)."""
    return {"updateTextStyle": {"range": {"startIndex": index, "endIndex": index + 1},
                                "textStyle": {"link": {"url": link}} if link else {},
                                "fields": "link"}}


def highlights(described):
    """Each stretch of highlighted text in the body that is not a link: (it, its paragraph's text).

    Highlighted pieces side by side are one stretch; a stretch that is only spaces is left out.
    """
    found = []
    for structural in _paragraphs_in(described["body"]["content"]):
        runs = [element["textRun"] for element in structural["paragraph"]["elements"]
                if "textRun" in element]
        whole = "".join(run.get("content", "") for run in runs).rstrip("\n")
        stretch = ""
        for run in runs + [{}]:  # an empty piece at the end closes the last stretch
            style = run.get("textStyle", {})
            if style.get("backgroundColor", {}).get("color") and "link" not in style:
                stretch += run.get("content", "").rstrip("\n")
                continue
            if stretch.strip():
                found.append((stretch, whole))
            stretch = ""
    return found


USUAL_SIZE = 11  # points: what Google Docs gives normal text, taken when a document says nothing


def text_size(described, index):
    """The size, in points, of the text at a position in the document.

    The size set on that text itself; failing that, the size its paragraph's named style
    gives; failing that, the usual 11.
    """
    for structural in _paragraphs_in(described["body"]["content"]):
        for element in structural["paragraph"]["elements"]:
            if element["startIndex"] <= index < element["endIndex"]:
                own = element.get("textRun", {}).get("textStyle", {}).get("fontSize", {})
                if "magnitude" in own:
                    return own["magnitude"]
                kind = structural["paragraph"].get("paragraphStyle", {}).get("namedStyleType")
                for style in described.get("namedStyles", {}).get("styles", []):
                    given = style.get("textStyle", {}).get("fontSize", {})
                    if style.get("namedStyleType") == kind and "magnitude" in given:
                        return given["magnitude"]
    return USUAL_SIZE


def _marks(described, index):
    """Each character of the paragraph holding index, but its line break: (where, how wide,
    highlighted, the character). Something that is not text, such as a picture, is one wide, not
    highlighted and "".
    The index is always in some paragraph: it comes from text found in one."""
    structural = next(found for found in _paragraphs_in(described["body"]["content"])
                      if found["startIndex"] <= index < found["endIndex"])
    marks = []
    for element in structural["paragraph"]["elements"]:
        run = element.get("textRun")
        at = element["startIndex"]
        if run is None:
            marks.append((at, 1, False, ""))
            continue
        marked = bool(run.get("textStyle", {}).get("backgroundColor", {}).get("color"))
        for character in run.get("content", ""):
            if character != "\n":
                marks.append((at, units(character), marked, character))
            at += units(character)
    return marks


def reach(described, start, end):
    """How far the highlight that the text from start to end is part of reaches: (first, last).

    Only within its paragraph, and only where the text itself is highlighted at that edge.
    """
    marks = _marks(described, start)
    first = start
    if any(at == start and marked for at, _, marked, _ in marks):
        for at, _, marked, _ in reversed(marks):
            if at < start:
                if not marked:
                    break
                first = at
    last = end
    after = [marked for at, wide, marked, _ in marks if at + wide >= end]
    if after and after[0]:
        for at, wide, marked, _ in marks:
            if at >= end:
                if not marked:
                    break
                last = at + wide
    return first, last


def highlighted(described, start, end):
    """Whether any of the text from start to end is highlighted."""
    return any(marked for at, _, marked, _ in _marks(described, start) if start <= at < end)


def text_at(described, start, end):
    """The text of the body from start to end, which are in one paragraph."""
    return "".join(character for at, _, _, character in _marks(described, start)
                   if start <= at < end)
