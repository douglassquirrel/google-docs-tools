"""Reading an edits file for edit-doc: a JSON list of {find, replace, occurrence?, id?, why?,
where?}, the shape of word-tools' propose-edits list, so one list serves both. Pure."""
import json
import unicodedata
from collections import namedtuple

KEYS = ("id", "where", "find", "replace", "occurrence", "why")


class Edit(namedtuple("Edit", "number id find replace occurrence why")):
    """One edit; number is its place in the file, from 1."""

    @property
    def name(self):
        """How messages name it: its id, else its place."""
        return self.id or "edit %d" % self.number


class EditsError(Exception):
    """The edits file cannot be used: problems names every fault in it."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def _faults(item):
    """Everything wrong with one edit, in words for the person who wrote the file."""
    faults = ['unknown key "%s"' % key for key in item if key not in KEYS]
    for key in ("id", "why"):
        if not isinstance(item.get(key, ""), str):
            faults.append('"%s" must be text' % key)
    find, replace = item.get("find"), item.get("replace")
    if not isinstance(find, str) or not find:
        faults.append('"find" must be text and not empty')
        find = None
    if not isinstance(replace, str):
        faults.append('"replace" must be text (empty to delete)')
        replace = None
    if find is not None and replace is not None and (
            unicodedata.normalize("NFC", find) == unicodedata.normalize("NFC", replace)):
        faults.append('"replace" is the same as "find", so the edit would change nothing')
    for key, value in (("find", find), ("replace", replace)):
        if value is not None and ("\n" in value or "\r" in value):
            faults.append('"%s" holds a line break; an edit must stay within one paragraph' % key)
        if value is not None and "\t" in value:
            faults.append('"%s" holds a tab, which an edit here cannot make' % key)
    if item.get("where", "body") != "body":
        faults.append('"where" may only be body here: a Google Doc\'s notes are not edited')
    occurrence = item.get("occurrence", 1)
    if type(occurrence) is not int or occurrence < 1:
        faults.append('"occurrence" must be a whole number, 1 or more')
    return faults


def parse_edits(text):
    """The edits in an edits file's text, or EditsError naming every fault."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise EditsError(["not JSON: %s" % error])
    if not isinstance(data, list):
        raise EditsError(["the file must hold a JSON list of edits, [{...}, {...}]"])
    if not data:
        raise EditsError(["the list has no edits in it"])
    edits, problems = [], []
    for number, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            problems.append('edit %d: must be an object with "find" and "replace"' % number)
            continue
        named = item.get("id") if isinstance(item.get("id"), str) and item.get("id") else (
            "edit %d" % number)
        faults = _faults(item)
        problems += ["%s: %s" % (named, fault) for fault in faults]
        if not faults:
            edits.append(Edit(number, item.get("id", ""), item["find"], item["replace"],
                              item.get("occurrence"), item.get("why", "")))
    if problems:
        raise EditsError(problems)
    return edits
