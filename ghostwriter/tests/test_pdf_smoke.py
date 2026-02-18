"""Smoke test for WeasyPrint PDF rendering."""

from pathlib import Path

import pytest


def test_weasyprint_can_render_basic_pdf(tmp_path: Path) -> None:
    weasyprint = pytest.importorskip("weasyprint")

    html = weasyprint.HTML(
        string="""
        <html>
          <body>
            <h1>Epilogue PDF Smoke Test</h1>
            <p>This verifies WeasyPrint is functional in runtime.</p>
          </body>
        </html>
        """
    )

    output_path = tmp_path / "smoke.pdf"
    html.write_pdf(str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 100
    assert output_path.read_bytes().startswith(b"%PDF")
