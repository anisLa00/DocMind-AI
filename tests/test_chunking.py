import pytest

from src.services.chunking import chunk_pages, chunk_text, estimate_tokens
from src.services.extraction import ExtractedPage


def test_chunks_are_numbered_consecutively():
    chunks = chunk_text("word " * 2000, chunk_size=300, chunk_overlap=50)

    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunks_respect_the_size_limit():
    chunks = chunk_text("word " * 2000, chunk_size=300, chunk_overlap=50)

    assert all(len(chunk.content) <= 300 for chunk in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(
        " ".join(f"token{i}" for i in range(400)), chunk_size=300, chunk_overlap=100
    )

    tail = chunks[0].content[-50:]
    assert tail.strip() and tail.strip().split()[-1] in chunks[1].content


def test_short_text_produces_a_single_chunk():
    chunks = chunk_text("Just a short note.", chunk_size=500, chunk_overlap=50)

    assert len(chunks) == 1
    assert chunks[0].content == "Just a short note."
    assert chunks[0].page_number == 1


def test_blank_text_produces_no_chunks():
    assert chunk_text("      \n\n  ") == []


def test_chunks_break_on_paragraph_boundaries():
    # Break points are searched for in the last third of the window, so the
    # size is chosen to put the paragraph break inside that range.
    text = "First paragraph here.\n\n" + "x" * 50 + "\n\nThird paragraph."
    chunks = chunk_text(text, chunk_size=30, chunk_overlap=0)

    assert chunks[0].content == "First paragraph here."
    assert chunks[1].content.startswith("x")


def test_page_numbers_follow_the_source_pages():
    pages = [
        ExtractedPage(number=1, text="alpha " * 60),
        ExtractedPage(number=2, text="beta " * 60),
        ExtractedPage(number=3, text="gamma " * 60),
    ]

    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=20)
    by_page = {chunk.page_number for chunk in chunks}

    assert by_page == {1, 2, 3}
    assert chunks[0].page_number == 1
    assert chunks[-1].page_number == 3


def test_blank_pages_are_skipped():
    pages = [
        ExtractedPage(number=1, text="real content here"),
        ExtractedPage(number=2, text="   "),
        ExtractedPage(number=3, text="more real content"),
    ]

    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=0)

    assert {chunk.page_number for chunk in chunks} == {1}
    assert "more real content" in chunks[0].content


def test_text_with_no_break_points_still_terminates():
    chunks = chunk_text("x" * 1000, chunk_size=100, chunk_overlap=90)

    assert len(chunks) > 1
    assert "".join(dict.fromkeys(chunk.content for chunk in chunks))


def test_token_estimate_is_recorded():
    chunks = chunk_text("word " * 200, chunk_size=400, chunk_overlap=0)

    assert all(chunk.token_estimate > 0 for chunk in chunks)
    assert chunks[0].token_estimate == estimate_tokens(chunks[0].content)


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (-5, 0), (100, 100), (100, 150), (100, -1)],
)
def test_invalid_parameters_are_rejected(chunk_size, chunk_overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=chunk_size, chunk_overlap=chunk_overlap)
