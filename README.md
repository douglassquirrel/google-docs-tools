# google-docs-tools

Small command-line programs for working on a Google Doc with an AI assistant: read the document
as text, put comments in it or list them, look at what has changed since the last look, and put a
picture in, from a file or an address, or in place of one already there. For Squirrel's book projects (`wrangling-ai`,
`beyond-ai`), whose drafts live in Google Docs, and for any other project that needs the same.
Each command takes the document by its id or address, keeps everything particular to one project
in a settings file or on the command line, and never changes the document's words. What changes
anything at Google is listed, and nothing else does: adding a comment; putting a picture in, or in
place of another; and, for a picture from a file, uploading it into a named Drive folder and
sharing that one copy with anyone only while Google fetches it, then taking the sharing back.
Nothing is ever deleted or binned. The Google layer came from
[online-publishing-tools](https://github.com/douglassquirrel/online-publishing-tools) on
1 November 2026, copied and made general; that repository keeps its own.

| Command | Job |
|---|---|
| `read-doc` | Print a Google Doc as text: headings with `#`, **bold**, *italic*, links, list items, a `---` for a rule. Reads only. |
| `comment-doc` | Add a comment on some of the document's words, addressed to a named person if wanted; or list the document's comments. |
| `watch-doc` | One quiet look at a document and its comments: only what changed since the last look. Reads only, and writes its own snapshot file. |
| `insert-picture` | Put a picture where some words stand alone in their paragraph, from a file or an address, with a caption and a link if wanted. |
| `replace-picture` | List the pictures, or put a new picture in place of one, keeping its link, width and caption. |
| `google-sign-in` | Run once, by a person: sign in to Google in a browser and store the token the other tools use. |

## Requirements

- macOS with the command-line developer tools (which give `/usr/bin/python3`, Python 3.9), or
  Linux with Python 3.9 or later. Nothing else: no package to install, no server, no Docker.
- A Google Cloud project with the Google Docs API and the Google Drive API switched on and an
  OAuth client of type "Desktop app" (see "One-time set-up"), and a secrets folder beside this
  checkout, `google-docs-tools-secrets/`.
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

Done by a person, in this order. Steps 1 to 4 are in a browser and are not something these tools
do. The same Google Cloud client as `online-publishing-tools` uses may serve, in which case steps
1 to 3 are done and the secrets folder gets the same client id and secret (Squirrel's decision
of 1 November 2026: the secrets may be shared among the relevant tools projects).

1. In the Google Cloud console, in a project inside your organization: switch on the "Google
   Docs API" and the "Google Drive API" (Menu > APIs & Services > Library).
2. Menu > Google Auth platform > Branding > Get Started: give an app name and a support email,
   choose the "Internal" audience, finish.
3. Menu > Google Auth platform > Clients > Create Client > "Desktop app". Copy the client id
   and the client secret.
4. Make the secrets folder beside this checkout's outer folder, with one file, readable by you
   alone:

   ```bash
   mkdir -m 700 ~/projects/code/writing/google-docs-tools-secrets
   ( umask 177; printf "export GOOGLE_OAUTH_CLIENT_ID=''\nexport GOOGLE_OAUTH_CLIENT_SECRET=''\nexport GOOGLE_OAUTH_REFRESH_TOKEN=''\n" > ~/projects/code/writing/google-docs-tools-secrets/env.sh )
   ```

   Paste the client id and the client secret between the quotes on their lines.
5. Sign in, as the Google account the tools are to act as (`EMAIL` below), unless the folder
   already holds a refresh token for that account:

   ```bash
   set -a; . ~/projects/code/writing/google-docs-tools-secrets/env.sh; set +a
   ~/projects/code/writing/google-docs-tools-code/google-docs-tools/google-sign-in --account EMAIL --env-file ~/projects/code/writing/google-docs-tools-secrets/env.sh
   ```

   It prints a Google address. Open it in a browser, choose that account, approve Google Docs and
   Google Drive. The command then stores the token in `env.sh` and says so. If any other account
   signs in, nothing is stored.
6. If comments are to be addressed to people, write a settings file from
   `google-docs-tools.conf.example` (see "The settings file").

The secrets folder is never a git repository and is never copied. Where a session works on the Mac
through a connected folder (Claude's device shell), connect this checkout and the secrets folder to
it: they appear as `$HOME/mnt/google-docs-tools/` and `$HOME/mnt/google-docs-tools-secrets/`.

## Quick start

Every command needs the three Google secrets in its environment, so each run starts by sourcing
the secrets file in the same command:

```bash
set -a; . ~/projects/code/writing/google-docs-tools-secrets/env.sh; set +a
./read-doc https://docs.google.com/document/d/DOCUMENT-ID/edit --title
```

prints the document's name, a blank line, and the document as text. Then

```bash
./comment-doc DOCUMENT-ID --add "Is this the right year?" --on "in 1998 the" --dry-run
```

checks that the words are in the document exactly once and says what it would add, adding nothing;
without `--dry-run` it adds the comment and prints its id and the document's address with the
comment selected. `./comment-doc DOCUMENT-ID --list` prints the comments, oldest first. For a
session that looks at a document every few minutes,

```bash
./watch-doc DOCUMENT-ID --snapshot ~/looks/my-book.snapshot
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

    read-doc DOC [--title] [--highlights] [--timeout SECONDS]

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
| `--timeout SECONDS` | How long to wait for each answer from Google. Default 30. |

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

The first line is always one summary line, with the time of the look: `2026-11-01 19:45 UTC: nothing
new`, or a count of each kind of thing that is new. Every call to Google is a read. Scheduling the
looks is up to whoever runs it.

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

### `google-sign-in`: the one-time sign-in

    google-sign-in --account EMAIL --env-file FILE [--port N] [--timeout SECONDS] [--dry-run]

See "One-time set-up". It listens on 127.0.0.1 for the browser to bring Google's answer back,
checks that the account that signed in is the one named, and stores the refresh token in the env
file as `GOOGLE_OAUTH_REFRESH_TOKEN`, keeping every other line and leaving the file mode 600. Unless
its exit code is 0, nothing was stored. `--dry-run` checks the arguments, the environment and the
file and contacts nothing.

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
print: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `GOOGLE_OAUTH_REFRESH_TOKEN`. They
live in `google-docs-tools-secrets/env.sh` beside this checkout's outer folder; source it in the
same command as the tool. A missing one stops the command with exit 3 and the line to source.

## Errors and exit codes

| Code | Meaning |
|---|---|
| 0 | Done (or, with `--dry-run`, checked). For `watch-doc`, the look worked, whether or not anything is new: the summary line says which. |
| 2 | Bad arguments or settings: a `DOC` that is not an id or an address, flags that do not go together, an address not in `COMMENT_RECIPIENTS`, an unreadable `--settings` file, an empty marker. For `watch-doc`, also a `--snapshot` file that is not its snapshot of this document, or no folder to make it in; the file is left as it was. |
| 2, for the picture commands | Also: a picture file that is not a PNG, JPEG or GIF, is empty, over 50 MB or over 25 megapixels; no upload folder; `--list` with other flags. Nothing is contacted. |
| 3 | Cannot sign in to Google: a secret is not set or empty, or Google refused the stored token (run `google-sign-in` again). |
| 4 | Google could not be reached, or answered with an error; the message names the step and Google's own words. For the picture commands, also a picture Google could not fetch, a document changed by someone while the command ran (run it again), or a sharing that could not be taken back (`STILL SHARED`, see above). When Google stopped answering partway, the message says what may or may not have happened. |
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
invented. 636 tests; coverage of `googledocstools/` 99% (the five statements not run build the
picture-and-caption requests that no command here makes yet). `tests/tier1/` are pure functions,
`tests/tier2/` the commands against the stand-in.

**Checks to make by hand against Google**, read-only but for one comment: `read-doc` on a real
document you have shared with the account, with `--title`; `comment-doc --list` on it; `comment-doc
--add … --dry-run` on words in it; then one real `--add` and `--list` again to see it; `read-doc` on
a document with a nested bullet list and a numbered list; `watch-doc` twice on a document, editing
it between the two; `insert-picture --dry-run`, then for real, on a scratch document, from a file
and from an address, then `replace-picture --list` and `--picture 1` on it, checking each time that
the uploaded copy is in the folder and no longer shared. As of 1 November 2026, `read-doc` and `comment-doc --list` have been run on a
real document, and `watch-doc` twice on a public sample document with nothing changed between (sign
in, reading, comments, the snapshot). On 2 November 2026 the picture commands ran on scratch
documents: `insert-picture` from a file, with a caption, a link and a width; `replace-picture --list`;
`--picture 1` from a file of another shape (its link, width and caption kept) and `--picture 2` from
an address; each uploaded copy was left shared with its owner alone. A real `--add` and real lists
are still to come.

## Known limitations

- `read-doc` writes the body only: not headers, footers or footnotes' text (a footnote's place is
  marked), and not pictures (a paragraph that is only a picture is left out).
- A numbered list is written in figures whatever the document shows: an item shown as `b.` or
  `ii.` comes out as `2. `. A numbered heading has its number first (`1. ## Heading`).
- `watch-doc` does not see a highlight, an underline, a font or a picture changing, a comment
  edited or a comment deleted. It does not retry; if Google fails, run it again. It keeps no history:
  each look is compared with the one before.
- A comment goes on words that are in the document exactly once, within one paragraph; Google
  shows it under All comments rather than anchored on the words.
- Nothing here changes a document's words. Filling in text or making links, which
  `online-publishing-tools` does for the weekly email, is not here until a project asks for it.
- A picture's height is left to Google, which keeps the picture's own proportions.

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

## Contributing

Development is test-first: every piece of behaviour starts as a failing test. The test runner and
linter (`pytest`, `pytest-cov`, `ruff`) are in `requirements-dev.txt` and are needed only for
development, never to run the commands.

## Licence

MIT. See [LICENSE](LICENSE).
