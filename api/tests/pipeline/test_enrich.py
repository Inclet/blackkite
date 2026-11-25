"""Enrich: detail page text, linked PDFs, size cap, failures kept per item."""

from pathlib import Path

from blackkite.pipeline.enrich import enrich, html_to_text, pdf_to_text
from tests.pipeline.fakes import FakeFetcher
from tests.pipeline.pdfgen import make_pdf

DETAIL = b"""<html><head><title>x</title><script>var a = 1;</script></head>
<body><nav>Menu</nav><h1>Supply of cold chain transport</h1>
<p>Bids close on 30 November 2026.</p>
<a href="/files/bid-document.pdf">Bidding document</a>
<a href="docs/annex?id=2" type="application/pdf">Annex</a>
<a href="mailto:x@example.org">mail</a>
<a href="javascript:void(0)">js</a>
</body></html>"""


def test_html_to_text_drops_scripts_and_keeps_blocks():
    text, links = html_to_text(DETAIL)
    assert "var a" not in text
    assert "Supply of cold chain transport\nBids close on 30 November 2026." in text
    assert len(links) == 4


def test_pdf_to_text():
    assert "Lot 2 refrigerated trucks" in pdf_to_text(
        make_pdf("Lot 2 refrigerated trucks")
    )


def test_enrich_follows_detail_and_pdf_links(tmp_path: Path):
    pdf = make_pdf("Annex A: minimum 10 refrigerated trucks")
    f = FakeFetcher(
        {
            "https://example.org/t/1": ("text/html; charset=utf-8", DETAIL),
            "https://example.org/files/bid-document.pdf": ("application/pdf", pdf),
            "https://example.org/t/docs/annex?id=2": ("application/octet-stream", pdf),
        }
    )
    out = enrich(
        f,
        "https://example.org/t/1",
        data_dir=tmp_path,
        max_bytes=1_000_000,
        max_attachments=3,
    )
    assert out.errors == []
    assert [d.url for d in out.documents] == [
        "https://example.org/t/1",
        "https://example.org/files/bid-document.pdf",
        "https://example.org/t/docs/annex?id=2",
    ]
    assert "minimum 10 refrigerated trucks" in out.text()
    for d in out.documents:
        assert Path(d.file_path).is_file()
        assert Path(d.file_path).is_relative_to(tmp_path / "documents")
    # Same bytes stored once.
    assert out.attachments[0].file_path == out.attachments[1].file_path
    # mailto/javascript links are never requested.
    assert not any(u.startswith(("mailto", "javascript")) for u in f.requested)


def test_enrich_respects_size_cap_and_attachment_limit(tmp_path: Path):
    big = make_pdf("x" * 50)
    f = FakeFetcher(
        {
            "https://example.org/t/1": ("text/html", DETAIL),
            "https://example.org/files/bid-document.pdf": ("application/pdf", big),
        }
    )
    out = enrich(
        f,
        "https://example.org/t/1",
        data_dir=tmp_path,
        max_bytes=len(DETAIL),
        max_attachments=1,
    )
    assert out.detail is not None
    assert out.attachments == []
    assert any("over" in e for e in out.errors)
    assert len(f.requested) == 2  # the second PDF link was not followed


def test_enrich_failures_are_recorded_not_raised(tmp_path: Path):
    out = enrich(
        FakeFetcher({}),
        "https://example.org/missing",
        data_dir=tmp_path,
        max_bytes=10,
        max_attachments=1,
    )
    assert out.detail is None and out.errors
    out = enrich(
        None,
        "https://example.org/x",
        data_dir=tmp_path,
        max_bytes=10,
        max_attachments=1,
    )
    assert "no fetcher" in out.errors[0]
    out = enrich(
        FakeFetcher({}),
        "file:///etc/passwd",
        data_dir=tmp_path,
        max_bytes=10,
        max_attachments=1,
    )
    assert "scheme" in out.errors[0]
