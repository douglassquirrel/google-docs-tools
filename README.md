# google-docs-tools

Small command-line programs for working on a Google Doc with an AI assistant: read the document
as text, count its words by chapter, check its quotes, dashes and format, put comments in it or list
them, look at what has changed since the last look, make a list of edits in it as suggestions, put
new paragraphs (headings, text, bulleted lists) into it, set its format, and put a picture in, from a file or an address, or in place of one already there. For
Squirrel's book projects (`wrangling-ai`, `beyond-ai`), whose drafts live in Google Docs, and for any
other project that needs the same. Each command takes the document by its id or address and keeps
everything particular to one project in a settings file or on the command line. A command changes a
document only as the person running it has written out exactly (the words to find and what they
become, the new paragraphs, the format to set), never with words of its own; what changes anything
at Google is listed, and nothing else does: those edits, those paragraphs and that format; adding a comment; putting a picture in, or in
place of another; and, for a picture from a file, uploading it into a named Drive folder and sharing
that one copy with anyone only while Google fetches it, then taking the sharing back.
Nothing is ever deleted or binned. The Google layer came from
[online-publishing-tools](https://github.com/douglassquirrel/online-publishing-tools) on
1 November 2026, copied and made general; that repository keeps its own.

| Command | Job |
|---|---|
| `read-doc` | Print a Google Doc as text: headings with `#`, **bold**, *italic*, links, list items, a `---` for a rule; with `--footnotes`, the footnotes too. Reads only. |
| `comment-doc` | Add a comment on some of the document's words, addressed to a named person if wanted; or list the document's comments. |
| `watch-doc` | One quiet look at a document and its comments: only what changed since the last look. Reads only, and writes its own snapshot file. |
| `insert-picture` | Put a picture where some words stand alone in their paragraph, from a file or an address, with a caption and a link if wanted. |
| `replace-picture` | List the pictures, or put a new picture in place of one, keeping its link, width and caption. |
| `count-doc` | The words in each chapter (or part) of a document, and the total, counted as word-tools' `check-manuscript` counts. Reads only. |
| `check-typography` | List straight quotes and apostrophes, double hyphens and spaced hyphens, with the curly quote or en dash each should be. Reads only. |
| `edit-doc` | Make a list of find → replace edits in a document, as suggestions to accept or reject, or outright. The list has the shape of word-tools' `propose-edits` list. |
| `insert-paragraphs` | Put new paragraphs (headings, text, bulleted list items) written in a file into a document, after or before a given paragraph, as suggestions or outright. |
| `insert-footnote` | Put a footnote with the caller's text straight after given words, optionally taking out a bracketed note there, as a suggestion or outright. |
| `check-doc-format` | Check a document against a house format (page, body text, list items, title and headings) and, with `--fix`, set it right, formatting only. |
| `google-sign-in` | Run once, by a person: sign in to Google in a browser and store the token the other tools use. |

## Requirements

- macOS with the command-line developer tools (which give `/usr/bin/python3`, Python 3.9), or
  Linux with Python 3.9 or later. Nothing else: no package to install, no server, no Docker.
- A Google Cloud project with the Google Docs API and the Google Drive API switched on and an
  OAuth client of type "Desktop app" (see "One-time set-up"), and the three Google secrets: in
  Squirrel's projects, the shared set `google` of
  [lobster-tools](https://github.com/douglassquirrel/lobster-tools)' `secrets` command
  (`~/projects/secrets/google`); elsewhere, a secrets file of your own.
- The machine or shell must be able to reach `oauth2.googleapis.com`, `www.googleapis.com` and
  `docs.googleapis.com`; `google-sign-in` also needs a browser on the same machine.
- Each document must be shared with the Google account the tools sign in as (reading needs at
  least a viewer's access; commenting at least a commenter's).

## Installation

Clone the repository; the commands are the files at its top and run from any folder.

```bash
git clone git@github.com:douglassquirrel/google-docs-tools.git ~/projects/code/writing/google-docs-tools-code/google-docs-tools
~/projects/code/writing/google-docs-tools-code/google-docs-tools/read-doc --help
```

### One-time set-up for Google

In Squirrel's projects there is nothing to do: these tools and `online-publishing-tools` share one
set of secrets, `google`, kept by lobster-tools' `secrets` command (22 November 2026), made and
signed in from `online-publishing-tools`, whose token has every permission these tools ask for and
more. Check it holds all three names (it prints names only, never a value):

```bash
~/projects/code/lobster-tools-code/lobster-tools/secrets check google
```

If Google stops accepting the shared token, sign in again with `online-publishing-tools`'
`google-sign-in`, never this one: this one asks for fewer permissions, and refuses a file in the
shared sets.

Elsewhere, with a secrets file of your own, it is done by a person, in this order. Steps 1 to 3 are
in a browser and are not something these tools do.

1. In the Google Cloud console, in a project inside your organization: switch on the "Google
   Docs API" and the "Google Drive API" (Menu > APIs & Services > Library).
2. Menu > Google Auth platform > Branding > Get Started: give an app name and a support email,
   choose the "Internal" audience, finish.
3. Menu > Google Auth platform > Clients > Create Client > "Desktop app". Copy the client id
   and the client secret.
4. Make a secrets folder (here `~/google-secrets`) with one file, readable by you
   alone:

   ```bash
   mkdir -m 700 ~/google-secrets
   ( umask 177; printf "export GOOGLE_OAUTH_CLIENT_ID=''\nexport GOOGLE_OAUTH_CLIENT_SECRET=''\nexport GOOGLE_OAUTH_REFRESH_TOKEN=''\n" > ~/google-secrets/env.sh )
   ```

   Paste the client id and the client secret between the quotes on their lines.
5. Sign in, as the Google account the tools are to act as (`EMAIL` below), unless the folder
   already holds a refresh token for that account:

   ```bash
   set -a; . ~/google-secrets/env.sh; set +a
   ~/projects/code/writing/google-docs-tools-code/google-docs-tools/google-sign-in --account EMAIL --env-file ~/google-secrets/env.sh
   ```

   It prints a Google address. Open it in a browser, choose that account, approve Google Docs and
   Google Drive. The command then stores the token in `env.sh` and says so. If any other account
   signs in, nothing is stored.
6. If comments are to be addressed to people, write a settings file from
   `google-docs-tools.conf.example` (see "The settings file").

A secrets folder is never a git repository and is never copied. Where a session works on the Mac
through connected folders (a Claude session's device shell), connect this checkout, lobster-tools'
checkout and the shared set's folder, `~/projects/secrets/google`, to it. They appear under
`$HOME/mnt/`, and a run there is:

```bash
python3 "$HOME/mnt/lobster-tools/secrets" run --set-dir "$HOME/mnt/google" --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- "$HOME/mnt/google-docs-tools/read-doc" DOCUMENT-ID
```

## Quick start

Every command needs the three Google secrets in its environment, so each run goes through
lobster-tools' `secrets` command with the shared set (`--need` makes it refuse at once, naming a
name that is missing or empty; values it might print are masked):

```bash
S=~/projects/code/lobster-tools-code/lobster-tools/secrets
$S run google --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- ./read-doc https://docs.google.com/document/d/DOCUMENT-ID/edit --title
```

prints the document's name, a blank line, and the document as text. With a secrets file of your
own instead, source it in the same command: `set -a; . FILE; set +a; ./read-doc …`. Then

```bash
$S run google --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- ./comment-doc DOCUMENT-ID --add "Is this the right year?" --on "in 1998 the" --dry-run
```

checks that the words are in the document exactly once and says what it would add, adding nothing;
without `--dry-run` it adds the comment and prints its id and the document's address with the
comment selected. `comment-doc DOCUMENT-ID --list` prints the comments, oldest first. For a
session that looks at a document every few minutes,

```bash
$S run google --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- ./watch-doc DOCUMENT-ID --snapshot ~/looks/my-book.snapshot
```

makes a snapshot on its first run, and after that prints only what changed since the last one:

    2026-11-01 19:40 UTC: 2 paragraphs changed, 1 new note, 1 new comment
    == Changed ==
    changed, under "## Chapter one": …in the early {-spring-}{+autumn+}
    added, under "## Chapter one": A new paragraph here.
    == New notes ==
    [check this date]  in: …signed in 1998 [check this date] by both sides…
    == Comments ==
    new comment by Ann Example, 2026-11-01 19:38 UTC on "the words": Is this right?

## Usage

`DOC`, in every command, is the document's id (the part of its address between `/d/` and `/edit`)
or its whole address.

### `read-doc`: the document as text

    read-doc DOC [--title] [--highlights] [--footnotes] [--timeout SECONDS]

Prints the body as text: the title and headings with one `#` per level (the title counts as
level 1), `**bold**`, `*italic*`, `[words](address)` for a link, list items with `- ` or their number
(`1. `) and two more spaces for each level, a blank line between paragraphs and between list items,
`---` for a horizontal rule, and `<!-- not written: … -->` where a paragraph holds something that
has no text form (a footnote reference, a person chip, an equation). Text in tables is read in its
place. Empty paragraphs are left out. Every call to Google is a read.

| Flag | Meaning |
|---|---|
| `--title` | Print the document's name first, as a line, then a blank line. |
| `--highlights` | Mark highlighted text (a background colour that is not a link) as `{==text==}`. |
| `--footnotes` | After the body, list each footnote in the order of its mark: its number, up to six words before the mark, and its text in the same markup (paragraphs of one footnote joined with ` / `). |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

With `--footnotes` the body is as without it, and then:

    <!-- footnotes -->
    1 | A quoted line | Jo Bloggs, *A Made-Up Book*, p. 3.
    2 | Another “quote” | https://example.org/an-article

or `<!-- footnotes: none -->`.

### `comment-doc`: a comment on some words, or the list of comments

    comment-doc DOC --add TEXT --on QUOTE [--to EMAIL] [--quote] [--dry-run] [--settings FILE] [--timeout SECONDS]
    comment-doc DOC --list [--open-only] [--settings FILE] [--timeout SECONDS]

`--add` puts one comment on the words given with `--on`, which must be in the document exactly
once, within one paragraph (copy them exactly). Google shows a comment added this way under All
comments, not on the words themselves, so the words go at the start of the comment's text, as
`On "QUOTE": TEXT`; with `--quote` they go to Google as a quote instead, and the text as it is
(the editor then labels the quote "Original content deleted"). It prints `Added comment ID on
"QUOTE"` and the document's address with `?disco=ID`, which opens it with the comment selected.
It never changes the document's text, a comment already there, or anyone's access.

| Flag | Meaning |
|---|---|
| `--add TEXT` | The comment's text. Needs `--on`. |
| `--on QUOTE` | The words the comment is about. |
| `--to EMAIL` | Address the comment to this person, so that Google emails them. Only an address in the setting `COMMENT_RECIPIENTS`, whatever its capitals; the comment's text then starts `@address`. |
| `--quote` | Give the words to Google as a quote, not at the start of the text. |
| `--dry-run` | Check everything, say what would be added, add nothing. |
| `--list` | Print the document's comments, oldest first, each with who wrote it and when, what it is on, its text and its replies. Deleted ones are left out. |
| `--open-only` | With `--list`: leave out the resolved ones. |
| `--settings FILE` | The settings file. Without it, `~/.google-docs-tools.conf` if it exists. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

Google emails whoever a comment names, so the text may hold no address but the ones in
`COMMENT_RECIPIENTS`, and nor may the words of `--on` (they go in the text), unless `--quote` keeps
them out of it. A comment is added once: if Google cannot be reached while it is being added, the
command says to `--list` before trying again.

### `watch-doc`: what is new since the last look

    watch-doc DOC --snapshot FILE [--dry-run] [--settings FILE] [--note-open TEXT] [--note-close TEXT]
              [--placeholder-open TEXT] [--placeholder-close TEXT] [--skip-doubled yes|no] [--timeout SECONDS]
              [--wait [--every SECONDS] [--for SECONDS] [--settle SECONDS]]

The first line is always one summary line, with the time of the look: `2026-11-01 19:45 UTC: nothing
new`, or a count of each kind of thing that is new. Every call to Google is a read. Without
`--wait`, scheduling the looks is up to whoever runs it.

With no file at `--snapshot` it makes one, and prints the notes, each with a few words around it,
then how many placeholders there are and how many comments are open:

    2026-11-01 19:40 UTC: no snapshot yet, so one was made
    == Notes: 1 ==
    [check this date]  in: …signed in 1998 [check this date] by both sides…
    Placeholders: 3
    Open comments: 2

With a snapshot it compares and prints only what changed, in these parts, each left out when empty:

- `== Changed ==`: a line for each paragraph changed, added or removed, starting with where it is:
  under the nearest heading above it, or after the paragraph before it if there is no heading, or
  at the start. A changed paragraph is shown word by word, `{-old-}{+new+}`, with three words of
  what is the same on each side; one added or removed is shown whole. The text is compared as
  `read-doc` prints it with no flags, so bold, italic, a link, a heading's level and a list mark
  count as changes.
- `== New notes ==` and `== Notes gone ==`: the note, and the words around it.
- `== Comments ==`: each new comment and reply (who, when, what it is on if known, its text), and
  each comment resolved or reopened.

| Flag | Meaning |
|---|---|
| `--snapshot FILE` | The snapshot of the last look, written over with this one. Made if it is not there. Only ever written over if it is this command's snapshot of this document. |
| `--dry-run` | Do the look and print it, but save no snapshot. |
| `--note-open TEXT`, `--note-close TEXT` | What a note in the document starts and ends with. Default `[` and `]`. Taken literally; may be longer than one character. |
| `--placeholder-open TEXT`, `--placeholder-close TEXT` | The same for a placeholder. Default `{` and `}`. |
| `--skip-doubled yes\|no` | Whether text in doubled note markers, such as a merge tag `[[contact.first_name]]`, is left out of the notes. Default yes. |
| `--settings FILE` | The settings file. Without it, `~/.google-docs-tools.conf` if it exists. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

The snapshot holds the document's text, so it is written readable by its owner alone. It is written
beside FILE and moved into place after the look is printed, so a failure leaves the old one, and is
saved on every run that gets that far, whether or not anything was new.

**`--wait`: one background command that looks every few minutes.** It looks as above, and if
nothing is new it waits `--every` seconds (default 300, at least 60) and looks again, saving the
snapshot after each look. It returns as soon as a look finds anything the summary line counts
(paragraphs changed, notes new or gone, comments new, replied to, resolved or reopened), printing
that look just as a run without `--wait` would, with exit 0; with no snapshot yet, the first look
returns at once. After `--for` seconds (default 2700, 45 minutes) with nothing new it prints one line
and exits 6:

    2026-11-01 20:25 UTC: nothing new in 45 minutes (10 looks)

A look that fails ends it at once, as a run without `--wait` does (exit 4, or 2, 3 or 5); it never
tries again by itself. Stopped while it waits (the session stops it, or Ctrl-C), it says so on
standard error and exits 143 (or 130), leaving the snapshot of its last look whole and nothing
beside it. `--every` and `--for` without `--wait`, `--every` under 60, or `--every` over `--for` are
exit 2. A highlight added on its own is not seen, so it does not end the wait. Run it as a
background command, for example from a Claude Code session:

```bash
~/projects/code/lobster-tools-code/lobster-tools/secrets run google --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- ./watch-doc DOCUMENT-ID --snapshot ~/looks/my-book.snapshot --wait
```

A shell whose calls are cut off after a few minutes (a Claude session's device shell) cannot run a
`--wait`; there, run single looks on a schedule as before.

**`--settle SECONDS`: wake only when the writer pauses.** With `--wait --settle 120`, a look that
finds something new does not end the wait: it looks again every 120 seconds, and returns at the
first look that finds nothing changed since the look before, with one report of everything changed
since the wait began (the snapshot it started from, compared with the document at the end), printed
as a single look prints it, exit 0. A paragraph changed three times shows once, from start to end;
a note typed in two goes shows once, whole. Before anything changes it looks every `--every` seconds;
`--for` still bounds the whole wait, so a writer who never pauses gets everything when it runs out
(exit 0), and with nothing new at all it is exit 6 as before. Changes undone before it settles are
nothing new. The snapshot is saved only when it reports, so a look that fails while it settles ends
it with that look's exit code, saying the changes were seen and not reported, and the next run
reports them. With no snapshot yet the first look returns at once. `--settle` without `--wait`,
under 30 or over `--for` is exit 2.

### `insert-picture`: a picture where some words are

    insert-picture DOC --at WORDS (--image-file FILE | --image-url URL) [--caption TEXT] [--link URL]
                   [--width POINTS] [--no-centre] [--folder ID] [--settings FILE] [--dry-run] [--timeout SECONDS]

The words (a placeholder such as `[PICTURE]`) must be in the document exactly once and alone in
their paragraph, which becomes the picture. The picture is centred, and its caption with it, unless
`--no-centre`. It is one change to the document, made whole or not at all, and only if nobody has
changed the document since it was read.

```bash
./insert-picture DOCUMENT-ID --at "[PICTURE]" --image-file ~/Desktop/frame.png --caption "A *frame* grab." --dry-run
```

    Dry run: nothing was uploaded, shared or changed.
    Document: My book
    Link: https://docs.google.com/document/d/DOCUMENT-ID/edit
    In place of: [PICTURE]
    Picture: /Users/you/Desktop/frame.png (PNG, 1406 x 1046 pixels)
    Would upload: picture for My book, 2026-11-02 21:50 UTC, frame.png, into the folder FOLDER-ID, shared only while it goes in
    Width: 220 pt
    Centred: yes
    Caption paragraphs: 1
    Caption size: 10 pt

| Flag | Meaning |
|---|---|
| `--at WORDS` | The words the picture takes the place of. |
| `--image-file FILE` | A PNG, JPEG or GIF on this machine, known by its first bytes, not its name; under 50 MB and at most 25 megapixels. |
| `--image-url URL` | Instead, a public `https://` address; Google fetches it, and nothing is uploaded or shared. |
| `--caption TEXT` | A caption under the picture, in `read-doc`'s markup (`**bold**`, `*italic*`, `[words](address)`; a blank line starts a new paragraph), one point smaller than the text it replaces. |
| `--link URL` | Make the picture itself a link (`http://` or `https://`). |
| `--width POINTS` | The picture's width. Default 220. Google keeps its proportions. |
| `--no-centre` | Leave the alignment as the words' paragraph had it. |
| `--folder ID` | The Drive folder an uploaded copy goes into: the part of the folder's address after `/folders/`. Without it, the setting `UPLOAD_FOLDER_ID`. Needed with `--image-file`. |
| `--settings FILE` | The settings file. Without it, `~/.google-docs-tools.conf` if it exists. |
| `--dry-run` | Check everything and read the document, then say what would be done; upload, share and change nothing. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

**A picture from a file, and sharing.** Google puts a picture into a document only from an address
it can fetch, and will not fetch a Drive file that is not shared. So the file is uploaded into the
folder, named `picture for <document>, <time> UTC, <file name>`; that one copy is shared "anyone
with the link can view" for the one change to the document; and the sharing is taken back straight
after, whether the change worked or not. The document keeps its own copy of the picture, so it stays
after the sharing is gone. The uploaded copy stays in the folder, not shared, and the run prints its
link. If the sharing cannot be taken back, the run fails with exit 4 and a message starting `STILL
SHARED` that names the copy: open it in Drive, choose Share, and set General access to Restricted.

### `replace-picture`: a new picture in place of an old one

    replace-picture DOC --list
    replace-picture DOC --picture N (--image-file FILE | --image-url URL) [--width POINTS] [--folder ID]
                    [--settings FILE] [--dry-run] [--timeout SECONDS]

`--list` prints the pictures, numbered in the order they come in the document, and reads only:

    3 pictures in My book
    1. 220 pt wide, from https://img.example/one.png, then "A caption under it."
    2. 165 pt wide, from https://img.example/two.png, linked to https://v.example/two, then "Another caption."
    3. width not given

`--picture N` puts the new picture in place of picture N, at its width unless `--width` is given,
with its link, in one change: the old picture is taken out and the new one put in at the same place,
so the caption under it and its paragraph's alignment stay as they were. (Google's own way of
swapping a picture crops the new one to the old one's shape.) The new picture's height follows its
own shape. A picture from a file is uploaded and shared just as for `insert-picture`; `--dry-run`
says which picture would go and changes nothing.

### `count-doc`: the words in each chapter

    count-doc DOC [--level N] [--exclude-braces] [--exclude-lorem] [--timeout SECONDS]

Prints the words in each part of the document, then the total. A part starts at the title or at a
heading at level N or above (default 2, so `##` and `#` headings each start one) and runs to the
next; its heading's words count in it. Text before the first part has a line of its own. Words are
counted as word-tools' `check-manuscript` counts them: what lies between spaces, in every paragraph
of the body, headings, list items and tables included. Footnotes are not counted (`check-manuscript`
adds notes to its total), and neither are chips, footnote marks or pictures. The document is read as
it would be with every pending suggestion accepted; an account that may only view the document is
not shown its suggestions, so then they are not counted, and the last line says so. Every call to
Google is a read.

    $ count-doc DOC --exclude-braces
       212  Before the first heading
     4,702  Chapter 1: The start
     3,951  Chapter 2: The middle
     8,865  Total
    Left out: 37 words in braces.
    Pending suggestions are counted as if accepted.

| Flag | Meaning |
|---|---|
| `--level N` | The heading level that starts a part, 1 to 6. Headings above it, and the title, start one too. Default 2. |
| `--exclude-braces` | Leave out text in braces, `{like this}` (a brace with no partner in its paragraph is text), and say how many words that was. |
| `--exclude-lorem` | Leave out each paragraph of lorem ipsum filler: one that starts "Lorem ipsum" or "Duis aute", or of whose words more than half are lorem ipsum's own. Says how many words that was. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

### `check-typography`: straight quotes and odd dashes

    check-typography DOC [--checks quotes,dashes] [--settings FILE] [--timeout SECONDS]

Lists each paragraph (headings and list items included) that holds a straight double quote `"` or
a straight apostrophe or single quote `'` (the check `quotes`), or a double hyphen `--` or a hyphen
with a space each side ` - ` (the check `dashes`), with where it is, its first words, and a line for
each word that needs fixing, with the word before and after, as it is and as it would be. A quote
at the start of a paragraph, or after a space, an opening bracket or a dash, opens (“ ‘); any other
closes (” ’, which is also the apostrophe). Both dashes become an en dash, `–`. Link text that is
itself a web address, and merge tags in doubled brackets such as `[[contact.first_name]]`, are left
out; a link's address is never part of the text. Every call to Google is a read: to make the
changes, give them to `edit-doc`.

    $ check-typography DOC
    == Typography: 2 ==
    under "## Briefly…": We don't want "this" -- or that.
      We don't want → We don’t want
      want "this" -- or → want “this” – or
    under "## Briefly…": A spaced - hyphen.
      spaced - hyphen. → spaced – hyphen.
    Typography: 2 paragraphs to fix.

| Flag | Meaning |
|---|---|
| `--checks LIST` | Which checks: a comma list of `quotes` and `dashes`. Wins over the setting `TYPOGRAPHY_CHECKS`; both, if neither is given. |
| `--settings FILE` | The settings file to read instead of `~/.google-docs-tools.conf`. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

Exit code 0 when there is nothing to fix and 1 when there is something.

### `edit-doc`: a list of edits, as suggestions

    edit-doc DOC EDITS.json [--direct] [--dry-run] [--timeout SECONDS]

Makes each edit in the list as a Google Docs suggestion, for the document's editors to accept or
reject, or outright with `--direct`. The list has the shape of word-tools' `propose-edits` list, so
one list serves a Word file and a Google Doc:

```json
[
  {"id": "E1", "find": "the quick fox", "replace": "the slow fox", "why": "plainer"},
  {"find": "one and one", "replace": "one", "occurrence": 2},
  {"find": "a {put an example here} b", "replace": "a b"}
]
```

`find` is exact text within one paragraph, found even across bold, italic or linked pieces;
`replace` is what it becomes (empty to delete; to put words in, give the words on either side in
both). `occurrence` picks the Nth match, in the document's order, where there are several; `id`
names the edit in the report (`edit N` otherwise); `why` is for the person reading the list; `where`
may be given, as `body` only. Only the words that change are changed: the words `find` and
`replace` share at their start and end are left alone, so a one-word change marks one word, and the
new words take the look of the old.

The whole list is checked before anything is changed, and nothing is changed if any edit cannot be
made: a `find` not in the document, in it more than once with no `occurrence`, `occurrence` beyond
the last, touching text in a pending suggestion, running across a paragraph break, a footnote mark,
a chip or a picture, or overlapping another edit. The edits go to Google in one change, all or
nothing, made only if the document is as it was when read; if someone changed it meanwhile, nothing
is changed and you run the command again. Afterwards the command reads the document again, as it
would be with the suggestions accepted, and checks each edit's new words are there.

    $ edit-doc DOC edits.json
    E1 | The [quick → slow] fox jumps. | suggested
    edit 2 | A [bold → strong] word here. | suggested
    2 edits suggested; each is in the document.

| Flag | Meaning |
|---|---|
| `--direct` | Make the edits outright, not as suggestions. |
| `--dry-run` | Check every edit and say where it would go (`would be suggested`); change nothing. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

To make the fixes `check-typography` proposes, give each as an edit: `{"find": "We don't want",
"replace": "We don’t want"}`.

### `insert-paragraphs`: new paragraphs beside a given one

    insert-paragraphs DOC CONTENT.md (--after WORDS | --before WORDS) [--direct] [--dry-run] [--timeout SECONDS]

Puts the paragraphs written in `CONTENT.md` into the document after (or before) the paragraph that
holds `WORDS`, as Google Docs suggestions for its editors to accept or reject, or outright with
`--direct`. `WORDS` must be in the document exactly once, within one paragraph, outside a table and
outside a pending suggestion, as for `comment-doc --on`. The file is in `read-doc`'s markup, so what
`read-doc` prints can be fed back:

```markdown
### A heading three

A plain paragraph with an *italic* word, which may go on
over more than one line.

{A placeholder: braces are plain text}

- a bulleted item
- another, **bold** in part, with [a link](https://example.org/)
```

`#` to `######` make a heading 1 to 6, `- ` a bulleted list item, anything else a plain paragraph;
`**bold**`, `*italic*` and `[words](https://…)` work in any of them. A blank line ends a paragraph;
a heading is one line, and a new heading or `- ` starts a new paragraph even without a blank line.
Each new paragraph takes the document's own style for its kind (Normal text, Heading 3), not the
look or the bullet of the paragraph beside it, so it matches the house format `check-doc-format`
checks. Consecutive items make one list, with Google's plain bullets (disc, circle, square); items
put in right after a list with the same bullets join it.

Refused, changing nothing: a numbered or indented (nested) list item, a heading of seven `#`, a
heading or item with no words, a character Google would drop, a mark left open, or new paragraphs
that hold `WORDS` themselves (exit 2, every fault named with its line, before Google is asked);
`WORDS` not there once, in a table or in a pending suggestion (exit 5). The paragraphs go to Google
in one change, all or nothing, made only if the document is as it was when read; afterwards the
command reads the document again, as it would be with the suggestions accepted, and checks each new
paragraph stands there, in order, with its kind, its words and their look.

    $ insert-paragraphs DOC "new paragraphs.md" --after "first paragraph"
    Document: A draft for tests
    After: The first paragraph under it.
      1 | heading 3 | A new heading
      2 | paragraph | A plain paragraph with an *italic* word.
      3 | paragraph | {A placeholder}
      4 | list item | one
      5 | list item | two
    5 new paragraphs suggested; each is in the document.

| Flag | Meaning |
|---|---|
| `--after WORDS` | Put them after the paragraph holding these words. |
| `--before WORDS` | Put them before it. One of the two is needed. |
| `--direct` | Put them in outright, not as suggestions. |
| `--dry-run` | Check everything and say where they would go (`would be suggested`); change nothing. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

### `check-doc-format`: a document against its house format

    check-doc-format DOC --format FORMAT.json [--fix] [--dry-run] [-v] [--timeout SECONDS]

Checks the document against a house format and reports, grouped by what is wrong, each paragraph
that does not match, with where it is and its first words (three of each kind unless `-v`); a
heading at a level the format does not name; a heading that does not match its pattern; and normal
text that looks like a heading (all bold, or 2 points or more above the body's size, in 15 words or
fewer). What a paragraph has is what it sets itself, else what its named style sets in the
document, else Google's default (Arial 11, single spacing). A paragraph with no text, or only spaces,
is never checked or fixed. With `"start_at": "heading_2"` in the format file, everything before the
first heading 2 (a book's title page and contents, laid out by hand) is left alone too, and the
report says how many paragraphs that was; the page is still checked. The check only reads.

With `--fix`, it sets every font, size, bold, colour, alignment, line spacing, first-line indent,
page break, keep-with-next, page size and margin that does not match, in one change made only if the
document is as it was when read, then reads the document and checks it again. It never changes a
character of text, never a heading's level, and never bold or italic in body text or list items
(the author's emphasis); a heading at the wrong level, one not matching its pattern, and text that
looks like a heading are reported and left for a person. With `--fix --dry-run` it says what it
would set and changes nothing.

The format file, every part optional (`check-doc-format.example.json` in this folder is a full one):

```json
{
  "start_at": "heading_2",
  "page": {"size": "letter", "margins_inches": 1},
  "body": {"font": "Times New Roman", "size": 12, "line_spacing": 2, "first_line_indent_inches": 0.5},
  "list": {"font": "Times New Roman", "size": 12, "line_spacing": 2, "first_line_indent_inches": 0},
  "heading_2": {"font": "Times New Roman", "size": 16, "bold": true, "colour": "#000000",
                "alignment": "centre", "page_break_before": true, "keep_with_next": true,
                "pattern": "^Chapter \\d+: "}
}
```

| Part | Settings |
|---|---|
| `start_at` | `title` or `heading_1` to `heading_6`: check and fix nothing before the first paragraph of that kind. Not a part, a setting of the whole file. |
| `page` | `size`: `letter`, `a4` or `[width, height]` in inches; `margins_inches`: one number for all four. |
| `body` (normal text), `list` (list items) | `font`, `size` (points), `line_spacing` (a multiple of single: 2 is double), `first_line_indent_inches`. |
| `title`, `heading_1` to `heading_6` | `font`, `size`, `bold`, `colour` (`#rrggbb`), `alignment` (`left`, `centre`, `right`, `justified`), `page_break_before`, `keep_with_next`, `pattern` (a regular expression the heading's text must match). |

    $ check-doc-format DOC --format book.json
    body text: font not Times New Roman: 1 paragraph
      under "## Chapter 1: The start": Pasted from the web.
    list items: first-line indent not 0 in: 1 paragraph
      under "## Chapter 1: The start": An indented item.
    Left out: 4 paragraphs before the first heading 2.
    Format: 2 problems in 2 paragraphs.

| Flag | Meaning |
|---|---|
| `--format FILE` | The house format, a JSON file. Required. (Not `--settings`, which is the settings file for the other commands.) |
| `--fix` | Set what does not match, then check again. |
| `--dry-run` | With `--fix`: say what would be set; change nothing. |
| `-v` | List every paragraph that does not match, not three of each kind. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

Exit code 0 when everything matches (after the fix, with `--fix`), 1 when something does not.

### `google-sign-in`: the one-time sign-in

    google-sign-in --account EMAIL --env-file FILE [--port N] [--timeout SECONDS] [--dry-run]

See "One-time set-up". It listens on 127.0.0.1 for the browser to bring Google's answer back,
checks that the account that signed in is the one named, and stores the refresh token in the env
file as `GOOGLE_OAUTH_REFRESH_TOKEN`, keeping every other line and leaving the file mode 600. Unless
its exit code is 0, nothing was stored. `--dry-run` checks the arguments, the environment and the
file and contacts nothing.

It refuses (exit 2, before anything is contacted) an env file inside lobster-tools' shared secrets
sets: the folder `LOBSTER_SECRETS_ROOT` names, else `SECRETS_ROOT` in `~/.lobster-tools.conf`, else
`~/projects/secrets`, a link into it included. A shared set's token serves other tools too, with
more permissions than this command asks for (Google Docs and Google Drive), and a sign-in here would
take theirs away: sign in for the shared set `google` with online-publishing-tools' `google-sign-in`.

### The settings file

`~/.google-docs-tools.conf`, or the file given with `--settings`: `KEY=value` lines and `#`
comments, read and never run; nothing secret goes in it. `google-docs-tools.conf.example` is the
model. A flag, where there is one, wins over the file.

| Setting | Used by | Meaning |
|---|---|---|
| `COMMENT_RECIPIENTS` | `comment-doc` | The only addresses a comment may be addressed to or name, with commas between. |
| `NOTE_OPEN`, `NOTE_CLOSE` | `watch-doc` | What a note starts and ends with. Default `[` and `]`. |
| `PLACEHOLDER_OPEN`, `PLACEHOLDER_CLOSE` | `watch-doc` | What a placeholder starts and ends with. Default `{` and `}`. |
| `UPLOAD_FOLDER_ID` | `insert-picture`, `replace-picture` | The Drive folder a picture from a file is uploaded into. |
| `SKIP_DOUBLED` | `watch-doc` | `yes` or `no`: whether text in doubled note markers is left out of the notes. Default `yes`. |

### The secrets

Three environment variables, read from the environment and nowhere else, which the commands never
print: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `GOOGLE_OAUTH_REFRESH_TOKEN`. In
Squirrel's projects they are in lobster-tools' shared set `google`: run each command as `secrets run
google --need GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN -- COMMAND …` (in a device shell, `python3
"$HOME/mnt/lobster-tools/secrets" run --set-dir "$HOME/mnt/google" … -- …`, as under "One-time
set-up"). Otherwise source your own secrets file in the same command as the tool. A missing one
stops the command with exit 3 and how to run it; an empty one, with exit 3 and how to see which are
set.

### `insert-footnote`: a footnote after given words

    insert-footnote DOC --after WORDS --text TEXT [--remove WORDS] [--direct] [--dry-run] [--timeout SECONDS]

Puts a footnote mark straight after `--after`'s words and the footnote's text into it, as a Google
Docs suggestion for its editors to accept or reject, or outright with `--direct`. `WORDS` must be
in the document exactly once, within one paragraph and outside a pending suggestion, as for
`comment-doc --on`. `TEXT` is one paragraph in `read-doc`'s markup: `*italic*` for a book's or a
magazine's title, `**bold**`, `[words](https://…)` for a link; a bare address stays plain text.
`--remove` takes out words standing straight after `--after`'s in the same change, typically the
author's bracketed note asking for the footnote, so the mark ends up where the note was:

    $ insert-footnote DOC --after "a phrase" --remove " [source: an article]" --text "Jo Bloggs, *A Made-Up Book*, p. 3."
    Document: A draft for tests
    After: …has a phrase
    Removed: " [source: an article]"
    Text: Jo Bloggs, *A Made-Up Book*, p. 3.
    Footnote 1 suggested; the mark and its text are in the document.

It takes two changes: Google says which footnote it made only in its answer to the change that
makes the mark, so the text goes in with a second one, made only if the document is as the first
left it. If the second fails, the document holds an empty footnote mark, and the command says so,
and where: reject it (or remove it), or type the text in by hand, before running it again, which
would put in a second mark. It never retries and never undoes. Afterwards it reads the document
again, as it would be with the suggestions accepted, and checks the mark stands straight after the
words and its footnote holds the text with its look. Google numbers footnotes itself, so a footnote
put in before others takes their numbers. `read-doc --footnotes` lists what a document already has.

Refused before Google is asked (exit 2): no words for `--after`, `--text` or `--remove`, a line
break in any of them, a mark left open, a character Google would drop. Refused, changing nothing
(exit 5): `--after`'s words not there exactly once or touching a pending suggestion, or `--remove`'s
words not straight after them.

| Flag | Meaning |
|---|---|
| `--after WORDS` | Put the mark straight after these words. Needed. |
| `--text TEXT` | The footnote's text. Needed. |
| `--remove WORDS` | Take these words out of the body in the same change; they must stand straight after `--after`'s. |
| `--direct` | Make the footnote outright, not as a suggestion. |
| `--dry-run` | Check everything and say what would be done (`A footnote would be suggested`); change nothing. |
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

## Errors and exit codes

| Code | Meaning |
|---|---|
| 0 | Done (or, with `--dry-run`, checked). For `watch-doc`, the look worked, whether or not anything is new: the summary line says which. |
| 6 | `watch-doc --wait`: nothing new in `--for` seconds. |
| 130, 143 | `watch-doc --wait`: stopped while it waited (Ctrl-C, or told to stop); the snapshot of its last look is kept. |
| 1 | `check-typography`: something to fix. `check-doc-format`: something does not match the format (after the fix, with `--fix`). |
| 2, for `edit-doc` and `check-doc-format` | Also: an edits or format file that cannot be read, is not JSON in UTF-8, or has faults; every fault is named. Nothing is contacted. |
| 2, for `insert-paragraphs` | Also: a content file that cannot be read, is not UTF-8, or has faults (each named with its line), or holds the words of `--after` or `--before`; neither of those given, or words empty or with a line break. Nothing is contacted. |
| 2, for `insert-footnote` | Also: `--after`, `--text` or `--remove` empty or with a line break; a mark in `--text` left open, or a character Google would drop. Nothing is contacted. |
| 2 | Bad arguments or settings: for `google-sign-in`, an `--env-file` in a shared secrets set; a `DOC` that is not an id or an address, flags that do not go together, an address not in `COMMENT_RECIPIENTS`, an unreadable `--settings` file, an empty marker. For `watch-doc`, also a `--snapshot` file that is not its snapshot of this document, or no folder to make it in; the file is left as it was. |
| 2, for the picture commands | Also: a picture file that is not a PNG, JPEG or GIF, is empty, over 50 MB or over 25 megapixels; no upload folder; `--list` with other flags. Nothing is contacted. |
| 3 | Cannot sign in to Google: a secret is not set or empty, or Google refused the stored token (run `google-sign-in` again). |
| 4 | Google could not be reached, or answered with an error; the message names the step and Google's own words. For the picture commands, also a picture Google could not fetch, a document changed by someone while the command ran (run it again), or a sharing that could not be taken back (`STILL SHARED`, see above). When Google stopped answering partway, the message says what may or may not have happened. |
| 4, for `edit-doc`, `insert-paragraphs` and `check-doc-format` | Also the document changed while the command read it (nothing was changed; run it again), or Google went out of reach while the change was being made (the message says it may or may not have been made, and how to look). |
| 4, for `insert-footnote` | Also the document changed while it read it (nothing was changed); or the mark was made but its text could not be put in, or Google did not say which footnote it made: the message says the document holds an empty footnote mark (or may, if Google went out of reach), after which words, and what to do. |
| 5, for `insert-footnote` | Also `--after`'s words not in the document exactly once or touching a pending suggestion, or `--remove`'s words not straight after them (nothing was changed); or the footnote not in the document as asked afterwards. |
| 5, for `edit-doc` | Also an edit that cannot be made (each is named, and nothing was changed), or an edit not in the document afterwards. |
| 5, for `insert-paragraphs` | Also the words of `--after` or `--before` not in the document exactly once, in a table or in a pending suggestion (nothing was changed), or a new paragraph not in the document afterwards (each is marked). |
| 5 | The document is not as it must be: no document with that id that this account can see, in the bin, not a Google Doc; or the words of `--on` or `--at` are not in it exactly once, or `--at`'s are not alone in their paragraph; no picture N; an upload folder this account cannot see; Google not saying an old picture's width (give `--width`). For `watch-doc`, also a snapshot that could not be written: the look was printed, the old snapshot stands, and the next look reports the same again. |

Every message says what happened and what to do, on standard error, with the command's name
first; there is never a traceback. When a comment was being added as Google went out of reach, the
message says it may or may not have been added and to `--list` before trying again.

## Testing

```bash
/usr/bin/python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest        # the whole suite, with coverage
.venv/bin/ruff check .  # lint
```

No test reaches Google or the network: a stand-in (`tests/conftest.py`) answers as Google does
and records every call, so the tests assert exactly which calls were made and that the read-only
commands wrote nothing; the sign-in's listener is stood in for too, and the real transport is tried
only against a server on this machine. Every document, account, id and token in the tests is
invented. 1053 tests, in about 14 seconds; coverage of `googledocstools/` 99% (the five statements
not run build the picture-and-caption requests that no command here makes yet). The stand-in also
holds pending suggestions and answers Google's suggestions view modes, as Google's reference
describes them. `tests/tier1/` are pure functions,
`tests/tier2/` the commands against the stand-in.

**Checks to make by hand against Google**, read-only but for one comment: `read-doc` on a real
document you have shared with the account, with `--title`; `comment-doc --list` on it; `comment-doc
--add … --dry-run` on words in it; then one real `--add` and `--list` again to see it; `read-doc` on
a document with a nested bullet list and a numbered list; `count-doc` and `check-typography` on a
real document; `edit-doc --dry-run`, then `edit-doc` and `edit-doc --direct` on a scratch document,
seeing the suggestions in Google Docs and accepting one; `insert-paragraphs --dry-run`, then as
suggestions and with `--direct` on a scratch document, after a paragraph and after the last one,
reading the result with `read-doc` and checking it with `check-doc-format`; `insert-footnote --dry-run`, then as a
suggestion with `--remove` and with `--direct` on a scratch document, reading the footnotes back with `read-doc
--footnotes`; `check-doc-format` with the example format
on a scratch document, then `--fix --dry-run`, `--fix`, and the check again; `watch-doc` twice on a document, editing
it between the two; `insert-picture --dry-run`, then for real, on a scratch document, from a file
and from an address, then `replace-picture --list` and `--picture 1` on it, checking each time that
the uploaded copy is in the folder and no longer shared. On 16 November 2026 `count-doc`, `check-typography` and `check-doc-format` (the check) ran on
Google's public sample document, read-only; then, on a scratch document, `edit-doc` made a real
suggestion (Google put the new words just before the struck ones, in the same bold) and a direct
edit and its undoing, and `check-doc-format --fix` set a heading's bold and keep-with-next and set
them back, each checking again with "everything matches". On 21 November 2026 `insert-paragraphs`
put a heading 3, three paragraphs and a three-item list into a scratch document as suggestions
(Google takes the headings and bullets as part of the suggested text), and `read-doc` read them back
exactly as written; `check-doc-format` reads suggestions inline, so it reports the new text's look
before its suggested change until the suggestions are accepted. On 22 November 2026 `check-doc-format
--fix` set a heading's bold, then its font, then both back, on a scratch document: Google drops text's
own bold when its font is set, which the fix now puts back in the same change. The same day
`watch-doc --wait` ran read-only on a scratch document: a first look, two-minute waits with nothing
new (exit 6, 3 looks), and a stop (exit 143, the snapshot whole, nothing beside it). On 27 November
2026, before `insert-footnote` was written, one footnote was suggested by hand on a scratch document:
Google takes a footnote as a suggestion, starts the footnote with a space, and puts the text given in
a second change into the same suggestion. The same day `read-doc --footnotes` listed it, and
`insert-footnote` suggested a second footnote with an italic title and a link, taking out the words
after its mark, and found it as written (Google numbered it 2, after the first); its dry runs and
refusals (words there seven times, words not there) changed nothing. As of 1 November 2026, `read-doc` and `comment-doc --list` have been run on a
real document, and `watch-doc` twice on a public sample document with nothing changed between (sign
in, reading, comments, the snapshot). On 2 November 2026 the picture commands ran on scratch
documents: `insert-picture` from a file, with a caption, a link and a width; `replace-picture --list`;
`--picture 1` from a file of another shape (its link, width and caption kept) and `--picture 2` from
an address; each uploaded copy was left shared with its owner alone. A real `--add` and real lists
are still to come.

## Known limitations

- `read-doc` writes the body only: not headers or footers, nor footnotes' text unless asked with
  `--footnotes` (a footnote's place is marked), and not pictures (a paragraph that is only a picture
  is left out).
- `insert-footnote` writes a footnote of one paragraph, and never changes a footnote already there;
  `edit-doc` cannot change a footnote's text either. Nothing here deletes a footnote: reject a
  suggested one, or delete one, in Google Docs.
- `read-doc` reads with pending suggestions inline, where Google holds a suggested footnote's italic
  and links as a suggested change of look: `--footnotes` shows them once the suggestion is accepted
  (seen 27 November 2026). `insert-footnote` checks its footnote as with suggestions accepted.
- A numbered list is written in figures whatever the document shows: an item shown as `b.` or
  `ii.` comes out as `2. `. A numbered heading has its number first (`1. ## Heading`).
- `watch-doc` does not see a highlight, an underline, a font or a picture changing, a comment
  edited or a comment deleted. It does not retry; if Google fails, run it again. It keeps no history:
  each look is compared with the one before.
- A comment goes on words that are in the document exactly once, within one paragraph; Google
  shows it under All comments rather than anchored on the words.
- `edit-doc` changes only what the caller writes out exactly: it never makes up words, and it does
  not edit footnotes, headers or footers. Whether Google puts a suggested insertion before or after
  the words it replaces is Google's affair; the command checks only that the new words are there.
- `insert-paragraphs` puts in headings, plain paragraphs and bulleted items only: not numbered or
  nested items, tables, pictures or a title, and not beside a paragraph inside a table. Its bullets
  are Google's plain preset; it cannot add items to a list elsewhere in the document.
- A picture's height is left to Google, which keeps the picture's own proportions.
- `count-doc` counts the body only, not footnotes, headers or footers, so a document with notes
  counts lower than `check-manuscript`, which adds its notes.
- `check-doc-format` reads list items' first-line indent as Google holds it, which is where a
  bullet stands; it does not read a list's own indents. It does not check headers, footers or
  footnotes, or text inside tables against a part of its own (they are body text).
- `check-typography` and `edit-doc` read the document with pending suggestions inline: a
  straight quote in a suggested deletion is still listed, and `edit-doc` refuses to touch text in
  a pending suggestion.

## Notes for users

- 1 November 2026: first version: `google-sign-in`, `read-doc`, `comment-doc`, copied from
  `online-publishing-tools` and made general. The sign-in asks for Google Docs and Google Drive
  only, not mail.
- 1 November 2026: running a command no longer writes `__pycache__` into the checkout, on any
  Python, so setting `PYTHONDONTWRITEBYTECODE` is no longer needed.
- 1 November 2026: `read-doc` now marks list items (`- `, or `1. ` for a numbered list, two more
  spaces for each level). They came out as plain paragraphs before, so the text of a document with
  lists has changed.
- 1 November 2026: new command, `watch-doc`.
- 2 November 2026: new commands, `insert-picture` and `replace-picture`, and the setting
  `UPLOAD_FOLDER_ID`. They are the first commands here that change a document, and the first that
  upload or share anything (briefly, and taken back).

- 16 November 2026: new command, `count-doc`.
- 16 November 2026: new command, `check-typography`, and the setting `TYPOGRAPHY_CHECKS`.
- 16 November 2026: new command, `edit-doc`, the first here that changes a document's words, always
  exactly as its edits file says.
- 16 November 2026: new command, `check-doc-format`, with `check-doc-format.example.json`. Exit
  code 1 is now used, by it and by `check-typography`, for "something does not match".
- 16 November 2026: `check-doc-format` no longer checks or fixes a paragraph with no text, and takes
  `"start_at": "heading_2"` (or any heading level, or `title`) in the format file to leave a book's
  front matter alone. A format file without it checks everything, as before, but empty paragraphs.
- 21 November 2026: new command, `insert-paragraphs`, which puts new paragraphs written out in a
  file into a document beside a given paragraph.
- 22 November 2026: `google-sign-in` refuses an `--env-file` inside lobster-tools' shared secrets
  sets; sign in for the shared set `google` with online-publishing-tools' `google-sign-in`.
- 22 November 2026: `watch-doc --wait --settle SECONDS` returns only once the document has stood
  still that long, with one report of all that changed since the wait began.
- 22 November 2026: `watch-doc --wait` (with `--every` and `--for`) looks again and again and returns
  when a look finds something new (exit 0), or after 45 minutes of nothing new (exit 6, a new exit
  code). Without `--wait`, `watch-doc` is as before, but that Ctrl-C now ends any run with a plain
  message, not a traceback.
- 22 November 2026: `check-doc-format --fix` no longer takes bold off text whose font it sets (body
  text and headings alike), and one run sets a heading's font and bold together. Bold it took off
  before this is not put back by itself.
- 22 November 2026: the Google secrets now come from lobster-tools' shared set `google`: run each
  command through `secrets run google --need … -- COMMAND` instead of sourcing
  `google-docs-tools-secrets/env.sh`, which goes out of use. In a device shell, connect lobster-tools
  and `~/projects/secrets/google` in its place. The commands' help and their message for a missing
  secret say so.
- 27 November 2026: new command, `insert-footnote`, which puts a footnote with the caller's text
  after given words, and `read-doc --footnotes`, which lists a document's footnotes after its body.
  `read-doc` without the flag is as before.

## Contributing

Development is test-first: every piece of behaviour starts as a failing test. The test runner and
linter (`pytest`, `pytest-cov`, `ruff`) are in `requirements-dev.txt` and are needed only for
development, never to run the commands.

## Licence

MIT. See [LICENSE](LICENSE).
