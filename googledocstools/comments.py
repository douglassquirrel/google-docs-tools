"""Comments on a week's document: whom one may be addressed to, and how the list is printed."""
import re

# Shaped like an address: something, @, a name with a dot in it. Wide on purpose: Google may
# take anything like an address in a comment for a mention, and email that person.
_ADDRESS = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")

# The words a comment is about, at the start of its text after any mentions, as the tool writes
# them when it sends no quote (Request 25): `@laura@example.org On "the words": the text`.
_ON = re.compile(r'(?:@\S+ )*On "([^\n]+?)": ')


def recipients(setting):
    """The addresses a comment may be addressed to, from COMMENT_RECIPIENTS, in small letters."""
    return [part.strip().lower() for part in (setting or "").split(",") if part.strip()]


def addresses_in(text):
    """Every email address in some text, in small letters, in order."""
    return [found.lower().lstrip("+") for found in _ADDRESS.findall(text)]


def _when(given):
    """A time as Google writes it (2026-10-19T12:00:05.120Z) as the tools write one."""
    match = re.match(r"([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2})", given or "")
    if not match:
        return "at a time not given" if not given else given
    return "%s %s UTC" % match.groups()


def _by(item):
    name = (item.get("author") or {}).get("displayName") or "someone unnamed"
    return "%s, %s" % (name, _when(item.get("createdTime")))


def _block(comment):
    lines = ["== Comment %s: %s ==" % (comment.get("id"),
                                         "resolved" if comment.get("resolved") else "open"),
             "By " + _by(comment)]
    if comment.get("assigneeEmailAddress"):
        lines.append("Assigned to " + comment["assigneeEmailAddress"])
    if comment.get("mentionedEmailAddresses"):
        lines.append("Mentions: " + ", ".join(comment["mentionedEmailAddresses"]))
    quoted = (comment.get("quotedFileContent") or {}).get("value")
    if not quoted:
        on = _ON.match(comment.get("content") or "")
        quoted = on and on.group(1)
    if quoted:
        lines.append('On: "%s"' % quoted)
    if comment.get("content"):
        lines += comment["content"].split("\n")
    for reply in comment.get("replies") or []:
        if reply.get("deleted"):
            continue
        said = [reply.get("content") or ""]
        action = {"resolve": "(resolved)", "reopen": "(reopened)"}.get(reply.get("action"))
        if action:
            said.append(action)
        first, *rest = " ".join(part for part in said if part).split("\n")
        lines.append("  Reply by %s: %s" % (_by(reply), first))
        lines += ["    " + line for line in rest]
    return lines


def _count(number, word):
    return "%d %s%s" % (number, word, "" if number == 1 else "s")


def listing(found, open_only):
    """The lines --list prints for the comments Google gave, oldest first."""
    kept = sorted((c for c in found if not c.get("deleted")),
                  key=lambda c: c.get("createdTime") or "")
    if not kept:
        return ["No comments."]
    shut = [c for c in kept if c.get("resolved")]
    if open_only:
        kept = [c for c in kept if not c.get("resolved")]
        lines = ["%s (%d resolved left out)" % (_count(len(kept), "open comment"), len(shut))]
    else:
        lines = ["%s: %d open, %d resolved" % (
            _count(len(kept), "comment"), len(kept) - len(shut), len(shut))]
    for comment in kept:
        lines += [""] + _block(comment)
    return lines
