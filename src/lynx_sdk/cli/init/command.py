"""
`lynx init` — interactively generate a lynxConf.json file.
"""

from pathlib import Path

import typer
from rich import print as rprint

from lynx_sdk.cli.conf import CONF_FILENAME, LynxConf, write_conf


def init_cmd():
    """Initialize a new Lynx project by creating a lynxConf.json file."""
    conf_path = Path.cwd() / CONF_FILENAME

    if conf_path.exists():
        overwrite = typer.confirm(
            f"{CONF_FILENAME} already exists. Overwrite?", default=False
        )
        if not overwrite:
            raise typer.Abort()

    service_file = typer.prompt("Service file", default="main.py")
    service_object = typer.prompt("Service variable name", default="service")
    upstream_node_host = typer.prompt("Upstream node host", default="localhost")
    upstream_node_port = typer.prompt("Upstream node port", default=1883, type=int)

    conf = LynxConf(
        service_file=service_file,
        service_object=service_object,
        upstream_node_host=upstream_node_host,
        upstream_node_port=upstream_node_port,
    )

    output_path = write_conf(conf)
    rprint(f"[green]Created {output_path}[/green]")
