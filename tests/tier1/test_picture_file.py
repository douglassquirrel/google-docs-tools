"""A picture file: its kind and size from its own bytes, and every refusal."""
import struct

import pytest

from googledocstools.picture_file import LARGEST, NotAPicture, Picture, read_picture
from tests.conftest import invented_gif, invented_jpeg, invented_png


@pytest.mark.parametrize("data,kind,mime,size", [
    (invented_png(16, 12), "PNG", "image/png", (16, 12)),
    (invented_gif(10, 8), "GIF", "image/gif", (10, 8)),
    (invented_jpeg(20, 15), "JPEG", "image/jpeg", (20, 15)),
])
def test_a_png_a_gif_and_a_jpeg_are_known_by_their_bytes_with_their_size(
        tmp_path, data, kind, mime, size):
    path = tmp_path / "named wrongly.txt"
    path.write_bytes(data)
    assert read_picture(str(path)) == Picture(kind, mime, size[0], size[1], data)


def test_a_progressive_jpeg_gives_its_size_too(tmp_path):
    data = invented_jpeg(30, 25).replace(b"\xff\xc0", b"\xff\xc2")
    path = tmp_path / "p.jpg"
    path.write_bytes(data)
    assert read_picture(str(path))[2:4] == (30, 25)


def _refused(tmp_path, data, name="x.png"):
    path = tmp_path / name
    path.write_bytes(data)
    with pytest.raises(NotAPicture) as raised:
        read_picture(str(path))
    return str(raised.value)


def test_an_empty_file_is_refused(tmp_path):
    assert "is empty" in _refused(tmp_path, b"")


@pytest.mark.parametrize("data", [
    b"Just some words.\n", b"\x89PNG\r\n\x1a\n", b"GIF89a\x01", b"\xff\xd8\xff\xd9",
    b"\xff\xd8\x00\x00\x00\x00", b"%PDF-1.4 not a picture", invented_png()[:20],
    b"\xff\xd8\xff\xe0\x00\x10JFIF",
])
def test_anything_that_is_not_a_whole_enough_png_jpeg_or_gif_is_refused(tmp_path, data):
    assert "not a PNG, JPEG or GIF" in _refused(tmp_path, data)


def test_a_picture_with_no_width_is_refused(tmp_path):
    assert "not a PNG, JPEG or GIF" in _refused(tmp_path, invented_gif(0, 8))


def test_a_picture_over_25_megapixels_is_refused(tmp_path):
    data = invented_png(1, 1).replace(struct.pack(">II", 1, 1), struct.pack(">II", 6000, 4200))
    told = _refused(tmp_path, data)
    assert "25 megapixels" in told and "6000 x 4200" in told


def test_a_file_over_50_mb_is_refused_without_being_read(tmp_path):
    path = tmp_path / "huge.png"
    with open(str(path), "wb") as handle:
        handle.truncate(LARGEST + 1)
    with pytest.raises(NotAPicture) as raised:
        read_picture(str(path))
    assert "50 MB" in str(raised.value)


def test_a_file_that_is_not_there_or_is_a_folder_is_refused(tmp_path):
    with pytest.raises(NotAPicture) as raised:
        read_picture(str(tmp_path / "not there.png"))
    assert "could not be read" in str(raised.value)
    with pytest.raises(NotAPicture) as raised:
        read_picture(str(tmp_path))
    assert "could not be read" in str(raised.value)
