"""
Lynx CLI entry point. Provides commands for initializing projects,
generating documentation, and containerizing Lynx services.
"""

try:
    import typer
except ImportError:
    raise SystemExit(
        "CLI dependencies not installed. Run: pip install lynx-sdk[cli]"
    )

from lynx_sdk.cli.init.command import init_cmd
from lynx_sdk.cli.docs.command import docs_cmd
from lynx_sdk.cli.docker.command import docker_app

app = typer.Typer(
    name="lynx",
    help="Lynx SDK CLI — tools for building, documenting, and packaging Lynx services.",
    no_args_is_help=True,
)

app.command("init")(init_cmd)
app.command("docs")(docs_cmd)
app.add_typer(docker_app, name="docker")


if __name__ == "__main__":
    app()
