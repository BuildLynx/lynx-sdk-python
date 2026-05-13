"""
`lynx docker init`   — generate a Dockerfile for a Lynx Service.
`lynx docker build`  — generate (if needed) and build the Docker image.
`lynx docker export` — write commit-ready build artifacts for standalone docker build.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich import print as rprint
from jinja2 import Environment, FileSystemLoader

from lynx_sdk.cli.conf import read_conf

TEMPLATES_DIR = Path(__file__).parent / "templates"

_GIT_LINE_RE = re.compile(r"^\s*(-e\s+)?([\w._-]+\s*@\s*)?git\+", re.IGNORECASE)
_LOCAL_LINE_RE = re.compile(r"^\s*[\w._-]+\s*@\s*file:///", re.IGNORECASE)

docker_app = typer.Typer(
    help="Docker commands for packaging a Lynx Service.",
    no_args_is_help=True,
)


def _find_venv() -> Path | None:
    """Look for a virtual environment directory in the cwd."""
    cwd = Path.cwd()
    for name in ("venv", ".venv"):
        candidate = cwd / name
        if candidate.is_dir():
            return candidate
    return None


def _pip_freeze_path(venv_path: Path) -> Path:
    """Return the pip executable path inside a venv."""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "pip.exe"
    return venv_path / "bin" / "pip"


def _is_non_portable_line(line: str) -> bool:
    """Return True if the line is a git+ VCS ref or a local file:/// path."""
    return bool(_GIT_LINE_RE.match(line) or _LOCAL_LINE_RE.match(line))


def _filter_non_portable(text: str) -> str:
    """Remove git+ and local file:/// lines from requirements text."""
    return "\n".join(
        line for line in text.splitlines()
        if not _is_non_portable_line(line)
    ) + "\n"


def _has_non_portable_lines(text: str) -> bool:
    return any(_is_non_portable_line(line) for line in text.splitlines())


def _find_sdk_source() -> Path | None:
    """
    Locate the SDK project root (containing pyproject.toml + src/lynx_sdk/).
    Checks cwd first, then falls back to the installed package location.
    """
    cwd = Path.cwd()
    if (cwd / "src" / "lynx_sdk").is_dir() and (cwd / "pyproject.toml").is_file():
        return cwd

    import lynx_sdk as _sdk
    pkg_dir = Path(_sdk.__path__[0])
    # Editable install: pkg_dir is <project>/src/lynx_sdk
    project_root = pkg_dir.parent.parent
    if (project_root / "pyproject.toml").is_file() and (project_root / "src" / "lynx_sdk").is_dir():
        return project_root

    return None


def _ensure_requirements() -> Path:
    """
    Ensure requirements.txt exists. If not, offer to generate
    from a local venv via pip freeze.
    """
    reqs = Path.cwd() / "requirements.txt"
    if reqs.exists():
        return reqs

    venv_path = _find_venv()
    if venv_path is None:
        rprint("[red]requirements.txt not found and no venv/ or .venv/ detected.[/red]")
        rprint("Create a requirements.txt and try again.")
        raise typer.Exit(code=1)

    generate = typer.confirm(
        f"requirements.txt not found. Generate from {venv_path.name}/?",
        default=True,
    )
    if not generate:
        rprint("Aborted. Create a requirements.txt and try again.")
        raise typer.Exit(code=1)

    pip_path = _pip_freeze_path(venv_path)
    if not pip_path.exists():
        rprint(f"[red]pip not found at {pip_path}[/red]")
        raise typer.Exit(code=1)

    result = subprocess.run(
        [str(pip_path), "freeze"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        rprint(f"[red]pip freeze failed: {result.stderr}[/red]")
        raise typer.Exit(code=1)

    reqs.write_text(result.stdout, encoding="utf-8")
    rprint(f"[green]Generated requirements.txt ({len(result.stdout.splitlines())} packages)[/green]")
    return reqs


@dataclass
class _BuildContext:
    """Tracks artifacts written by _prepare_build_context()."""
    dockerfile: Path
    docker_reqs: Path | None = None
    copied_sdk: bool = False
    written: list[str] = field(default_factory=list)


def _prepare_build_context() -> _BuildContext:
    """
    Write all files needed for ``docker build .`` into the cwd:
    Dockerfile, filtered requirements, and (if local) SDK source.
    """
    conf = read_conf()

    reqs_path = _ensure_requirements()
    reqs_text = reqs_path.read_text(encoding="utf-8")
    needs_filter = _has_non_portable_lines(reqs_text)
    sdk_source = _find_sdk_source()

    ctx = _BuildContext(dockerfile=Path.cwd() / "Dockerfile")

    # Filtered requirements (strip git+ and file:/// lines)
    if needs_filter:
        ctx.docker_reqs = Path.cwd() / "requirements.docker.txt"
        ctx.docker_reqs.write_text(_filter_non_portable(reqs_text), encoding="utf-8")
        ctx.written.append("requirements.docker.txt")

    # Copy SDK source into build context if not already in cwd
    if sdk_source is not None and sdk_source != Path.cwd():
        shutil.copytree(sdk_source / "src", Path.cwd() / "src", dirs_exist_ok=True)
        shutil.copy2(sdk_source / "pyproject.toml", Path.cwd() / "pyproject.toml")
        ctx.copied_sdk = True
        ctx.written.extend(["pyproject.toml", "src/"])

    # Render Dockerfile from template
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("Dockerfile.j2")
    rendered = template.render(
        service_file=conf.service_file,
        has_git_deps=needs_filter,
        sdk_local=sdk_source is not None,
    )
    ctx.dockerfile.write_text(rendered, encoding="utf-8")
    ctx.written.append("Dockerfile")

    return ctx


def _cleanup_build_context(ctx: _BuildContext) -> None:
    """Remove temporary artifacts created by _prepare_build_context()."""
    if ctx.docker_reqs is not None and ctx.docker_reqs.exists():
        ctx.docker_reqs.unlink()
    if ctx.copied_sdk:
        shutil.rmtree(Path.cwd() / "src", ignore_errors=True)
        (Path.cwd() / "pyproject.toml").unlink(missing_ok=True)


# ── Commands ─────────────────────────────────────────────────────────


@docker_app.command("init")
def docker_init_cmd():
    """Generate a Dockerfile for a Lynx Service."""
    dockerfile_path = Path.cwd() / "Dockerfile"
    if dockerfile_path.exists():
        overwrite = typer.confirm("Dockerfile already exists. Overwrite?", default=False)
        if not overwrite:
            raise typer.Abort()

    ctx = _prepare_build_context()
    _cleanup_build_context(ctx)
    rprint(f"[green]Generated {ctx.dockerfile}[/green]")


@docker_app.command("export")
def docker_export_cmd():
    """Write commit-ready build artifacts for a standalone docker build."""
    ctx = _prepare_build_context()

    rprint("[green]Exported build context:[/green]")
    for name in ctx.written:
        rprint(f"  - {name}")
    rprint(
        "\nAnyone can now build with:\n"
        "  [bold]docker build -t <tag> .[/bold]"
    )


@docker_app.command("build")
def docker_build_cmd(
    tag: str = typer.Option(
        None, "--tag", "-t",
        help="Image tag. Defaults to the service id from lynxConf.json.",
    ),
):
    """Build a Docker image for a Lynx Service."""
    conf = read_conf()
    ctx = _prepare_build_context()

    if tag is None:
        tag = conf.service_file.replace(".py", "").replace("/", "-").replace("\\", "-")

    rprint(f"Building image [bold]{tag}[/bold]...")
    try:
        result = subprocess.run(
            ["docker", "build", "-t", tag, "."],
            cwd=str(Path.cwd()),
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        _cleanup_build_context(ctx)
        rprint("[red]Docker CLI not found.[/red] Install Docker Desktop: https://docs.docker.com/get-docker/")
        raise typer.Exit(code=1)

    _cleanup_build_context(ctx)

    if result.returncode != 0:
        combined = result.stdout + result.stderr
        if "//./pipe/docker" in combined or "Is the docker daemon running" in combined:
            rprint(
                "[red]Docker engine is not running.[/red]\n"
                "Start [bold]Docker Desktop[/bold] and wait for it to finish "
                "initialising, then try again."
            )
            raise typer.Exit(code=1)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        rprint("[red]Docker build failed. See output above.[/red]")
        raise typer.Exit(code=1)

    rprint(f"[green]Successfully built image: {tag}[/green]")
