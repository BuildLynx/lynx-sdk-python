"""
`lynx docs` — generate markdown documentation from a Lynx Service,
with optional HTML and PDF output.
"""

from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from jinja2 import Environment, FileSystemLoader

from lynx_sdk.cli.conf import read_conf
from lynx_sdk.cli.discovery import load_service
from lynx_sdk.cli.docs.schema_renderer import render_schema

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _resolve_service(target: Optional[str]):
    """
    Resolve a Service instance using the discovery priority:
      1. Explicit CLI arg  (file.py:var or file.py)
      2. lynxConf.json
    """
    if target:
        return load_service(target)

    conf = read_conf()
    return load_service(f"{conf.service_file}:{conf.service_object}")


def docs_cmd(
    target: Optional[str] = typer.Argument(
        None,
        help="Path to service file, optionally with :variable (e.g. my_service.py:service). "
             "If omitted, reads from lynxConf.json.",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output file path (without extension). Defaults to <service_id> in the current directory.",
    ),
    html: bool = typer.Option(
        False, "--html",
        help="Also generate a styled HTML file.",
    ),
    pdf: bool = typer.Option(
        False, "--pdf",
        help="Also generate a PDF file (requires weasyprint).",
    ),
):
    """Generate markdown documentation for a Lynx Service."""
    service = _resolve_service(target)
    service.freeze_interface()
    about = service.produce_about()
    service_id = about["docs"]["id"]
    title = about["docs"].get("title") or service_id

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
    )
    env.filters["render_schema"] = render_schema
    template = env.get_template("service.md.j2")
    md_content = template.render(service=about)

    base_path = output if output else Path.cwd() / service_id

    md_path = base_path.with_suffix(".md")
    md_path.write_text(md_content, encoding="utf-8", newline="\n")
    rprint(f"[green]Markdown written to {md_path}[/green]")

    if html or pdf:
        from lynx_sdk.cli.docs.html_renderer import md_to_html, html_to_pdf

        html_content = md_to_html(md_content, title=title)

        if html:
            html_path = base_path.with_suffix(".html")
            html_path.write_text(html_content, encoding="utf-8", newline="\n")
            rprint(f"[green]HTML written to {html_path}[/green]")

        if pdf:
            pdf_path = base_path.with_suffix(".pdf")
            html_to_pdf(html_content, pdf_path)
            rprint(f"[green]PDF written to {pdf_path}[/green]")
