"""A picture file to put into a document: what kind it is and how big, from its own bytes.

Google takes a PNG, a JPEG or a GIF, under 50 MB and of at most 25 megapixels (its page for
insertInlineImage), so nothing else is sent to it."""
import os
import struct
from collections import namedtuple

LARGEST = 50 * 1024 * 1024  # bytes
MOST_PIXELS = 25 * 1000 * 1000
PNG = b"\x89PNG\r\n\x1a\n"
# The JPEG markers that start a frame header, which gives the picture's size.
FRAMES = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}

Picture = namedtuple("Picture", "kind mime width height data")


class NotAPicture(Exception):
    """The file cannot be put into a document. Worded for the person."""


def _jpeg_size(data):
    """(width, height) from a JPEG's frame header, or None if none is found."""
    at = 2
    while at + 4 <= len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker == 0xFF:  # a fill byte
            at += 1
            continue
        length = struct.unpack(">H", data[at + 2:at + 4])[0]
        if marker in FRAMES and at + 9 <= len(data):
            height, width = struct.unpack(">HH", data[at + 5:at + 9])
            return width, height
        at += 2 + length
    return None


def _kind(data):
    """(kind, mime type, width, height) from a picture's first bytes, or None."""
    if data.startswith(PNG) and len(data) >= 24 and data[12:16] == b"IHDR":
        return ("PNG", "image/png") + struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return ("GIF", "image/gif") + struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        size = _jpeg_size(data)
        if size is not None:
            return ("JPEG", "image/jpeg") + size
    return None


def read_picture(path):
    """The picture in a file, as a Picture; or NotAPicture saying why it cannot be put in."""
    try:
        if os.path.getsize(path) > LARGEST:
            raise NotAPicture("%s is over 50 MB, more than Google takes for a picture." % path)
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise NotAPicture("%s could not be read: %s." % (path, error.strerror))
    if not data:
        raise NotAPicture("%s is empty." % path)
    found = _kind(data)
    if found is None or not found[2] or not found[3]:
        raise NotAPicture("%s is not a PNG, JPEG or GIF (by its first bytes, whatever its name), "
                          "the kinds of picture Google takes." % path)
    kind, mime, width, height = found
    if width * height > MOST_PIXELS:
        raise NotAPicture("%s is %d x %d pixels, over the 25 megapixels Google takes for a "
                          "picture. Make it smaller first." % (path, width, height))
    return Picture(kind, mime, width, height, data)
