"""Strict file-signature checks for staff content uploads (content/media.py)."""

from app.modules.content import media


def test_media_signatures_are_strict() -> None:
    assert media._mp3(b"ID3\x04\x00\x00\x00\x00\x01\x00")
    assert not media._mp3(b"ID3\x09\x00\x00\x00\x00\x01\x00")  # unknown ID3 version
    assert media._mp3(bytes([0xFF, 0xFB, 0x90, 0x64]))  # MPEG-1 Layer III, 128 kbps
    assert not media._mp3(bytes([0xFF, 0xFF, 0xF0, 0x00]))  # reserved/invalid fields
    assert not media._mp3(b"<html><script>")
    assert media._m4a(b"\x00\x00\x00\x20ftypM4A \x00")
    assert not media._m4a(b"\x00\x00\x00\x20ftypqt  \x00")  # QuickTime video brand
    assert media._png(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR")
    assert not media._png(b"\x89PNG\r\n\x1a\n<svg onload=x>")
    assert media._jpeg(b"\xff\xd8\xff\xe0")
    assert not media._jpeg(b"\xff\xd8\xff\x00")
    assert media._webp(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert not media._wav(b"RIFF\x00\x00\x00\x00WAVE<htm")
