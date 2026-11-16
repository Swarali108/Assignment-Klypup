"""Printed page numbers. No PDF bytes and no network."""

from __future__ import annotations

import logging

from tools.pdf import PARSER_VERSION, printed_page_from_text, validate_printed_pages
from tools import pdf as pdf_tools


def test_roman_numeral_is_kept_as_printed():
    assert printed_page_from_text("Contents\n\nIV\n") == "IV"
    pages = [
        {"pdf_index": 1, "printed_page": "iv", "text": "iv"},
        {"pdf_index": 2, "printed_page": "2", "text": "2"},
    ]
    validate_printed_pages(pages)
    assert pages[0]["printed_page"] == "iv"
    assert pages[1]["printed_page"] == "2"


def test_stray_footer_on_a_table_page_is_nulled(caplog):
    """A table total of 125 is not the page number when neighbours use offset 0."""
    caplog.set_level(logging.WARNING, logger="tools.pdf")
    pages = []
    for index in range(1, 12):
        if index == 6:
            text = "Particulars 10 20 30\n125"
        else:
            text = f"Body of the page\n{index}"
        pages.append(
            {
                "pdf_index": index,
                "printed_page": printed_page_from_text(text),
                "text": text,
            }
        )
    validate_printed_pages(pages)
    assert pages[5]["printed_page"] is None
    assert pages[0]["printed_page"] == "1"
    assert pages[6]["printed_page"] == "7"
    assert "125" in caplog.text


def test_page_cache_name_includes_parser_version(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGES_CACHE_DIR", str(tmp_path))
    path = pdf_tools._page_cache_path("abc123")
    assert path.parent == tmp_path
    assert path.name == f"abc123.v{PARSER_VERSION}.json"


def test_max_workers_reads_the_environment(monkeypatch):
    monkeypatch.delenv("MAX_WORKERS", raising=False)
    assert pdf_tools.max_workers() == pdf_tools.DEFAULT_MAX_WORKERS == 8
    monkeypatch.setenv("MAX_WORKERS", "2")
    assert pdf_tools.max_workers() == 2
    monkeypatch.setenv("MAX_WORKERS", "zero")
    assert pdf_tools.max_workers() == 8
