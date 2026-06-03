from pathlib import Path
from types import SimpleNamespace

from app.renderers.png_exporter import export_pdf


def test_export_pdf_uses_full_page_height(monkeypatch, tmp_path: Path) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body>report</body></html>", encoding="utf-8")
    pdf_options = {}

    class FakePage:
        def goto(self, url: str, wait_until: str) -> None:
            assert url == html_path.resolve().as_uri()
            assert wait_until == "networkidle"

        def evaluate(self, script: str) -> int:
            assert "scrollHeight" in script
            return 3456

        def pdf(self, **kwargs) -> None:
            pdf_options.update(kwargs)

    class FakeBrowser:
        def new_page(self, **kwargs):
            assert kwargs["viewport"] == {"width": 720, "height": 1280}
            return FakePage()

        def close(self) -> None:
            pass

    class FakePlaywright:
        chromium = SimpleNamespace(launch=lambda: FakeBrowser())

    class FakeSyncPlaywright:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, traceback) -> None:
            pass

    monkeypatch.setattr("app.renderers.png_exporter.sync_playwright", lambda: FakeSyncPlaywright())

    export_pdf(html_path, pdf_path)

    assert pdf_options["path"] == str(pdf_path)
    assert pdf_options["print_background"] is True
    assert pdf_options["width"] == "720px"
    assert pdf_options["height"] == "3456px"
