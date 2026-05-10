"""
Converts Lynx markdown documentation into styled HTML and PDF.

Pipeline:  Markdown string  ->  HTML body (via markdown lib)  ->  styled page (via Jinja template)
           styled page  ->  PDF (via weasyprint)
"""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
import markdown

TEMPLATES_DIR = Path(__file__).parent / "templates"


def md_to_html(md_content: str, title: str = "Lynx Service Documentation") -> str:
    """
    Convert a markdown string into a full styled HTML page.
    Uses the page.html.j2 template for styling and collapsible headers.
    """
    body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "md_in_html"],
    )

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("page.html.j2")
    return template.render(title=title, body=body)


def _prepare_html_for_pdf(html_content: str) -> str:
    """
    Prepare HTML for PDF rendering by weasyprint.
    Since weasyprint doesn't execute JS, we force all <details> open
    and strip the collapsible-header script.
    """
    result = html_content.replace("<details", "<details open")
    result = re.sub(
        r"<script>.*?</script>",
        "",
        result,
        flags=re.DOTALL,
    )
    return result


def html_to_pdf(html_content: str, output_path: Path):
    """
    Render a styled HTML string to a PDF file using weasyprint.
    All <details> sections are forced open for the PDF.
    """
    try:
        import weasyprint
    except ImportError:
        raise SystemExit(
            "weasyprint is not installed. Run: pip install lynx-sdk[cli]"
        )
    except OSError as e:
        raise SystemExit(
            f"weasyprint failed to load system libraries: {e}\n"
            "On Windows, install GTK3 runtime: "
            "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"
        )

    pdf_html = _prepare_html_for_pdf(html_content)
    doc = weasyprint.HTML(string=pdf_html)
    doc.write_pdf(str(output_path))
