import pytest

from src.services.extraction import extract_pages, extract_text
from src.utils.errors import UnsupportedFileTypeError, ValidationError
from tests.factories import build_docx, build_pdf


def test_extracts_each_pdf_page_separately(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(build_pdf([["Page one about revenue."], ["Page two about headcount."]]))

    pages = extract_pages(path)

    assert [page.number for page in pages] == [1, 2]
    assert "revenue" in pages[0].text
    assert "headcount" in pages[1].text


def test_skips_pdf_pages_with_no_text(tmp_path):
    path = tmp_path / "gappy.pdf"
    path.write_bytes(build_pdf([["Only this page has words."], []]))

    pages = extract_pages(path)

    assert len(pages) == 1
    assert pages[0].number == 1


def test_extracts_docx_paragraphs_and_tables(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_bytes(build_docx(["First paragraph.", "Second paragraph."], table=[["Q1", "100"]]))

    text = extract_text(path)

    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "Q1 | 100" in text


def test_extracts_plain_text(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Line one\n\n\n\nLine two", encoding="utf-8")

    pages = extract_pages(path)

    assert len(pages) == 1
    # Runs of blank lines collapse to a single separator.
    assert pages[0].text == "Line one\n\nLine two"


def test_extracts_markdown(tmp_path):
    path = tmp_path / "readme.md"
    path.write_text("# Title\n\nSome content.", encoding="utf-8")

    assert "Some content." in extract_text(path)


def test_decodes_non_utf8_text(tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes("café pörköl".encode("latin-1"))

    assert extract_text(path)


def test_empty_file_yields_no_pages(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n", encoding="utf-8")

    assert extract_pages(path) == []


def test_rejects_an_unsupported_extension(tmp_path):
    path = tmp_path / "archive.zip"
    path.write_bytes(b"PK\x03\x04")

    with pytest.raises(UnsupportedFileTypeError):
        extract_pages(path)


def test_rejects_a_missing_file(tmp_path):
    with pytest.raises(ValidationError):
        extract_pages(tmp_path / "nope.txt")


def test_rejects_a_corrupt_docx(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"this is not a docx")

    with pytest.raises(ValidationError):
        extract_pages(path)
