"""
`lynx docker init`  — generate a Dockerfile for a Lynx Service.
`lynx docker build` — generate (if needed) and build the Docker image.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich import print as rprint
from jinja2 import Environment, FileSystemLoader

from lynx_sdk.cli.conf import read_conf

TEMPLATES_DIR = Path(__file__).parent / "templates"

_GIT_LINE_RE = re.compile(r"^\s*(-e\s+)?([\w._-]+\s*@\s*)?git\+", re.IGNORECASE)

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


def _filter_git_lines(text: str) -> str:
    """Remove all git+ VCS lines from requirements text."""
    return "\n".join(
        line for line in text.splitlines()
        if not _GIT_LINE_RE.match(line)
    ) + "\n"


def _has_git_lines(text: str) -> bool:
    """Return True if the requirements text contains any git+ lines."""
    return any(_GIT_LINE_RE.match(line) for line in text.splitlines())


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


@docker_app.command("init")
def docker_init_cmd():
    """Generate a Dockerfile for a Lynx Service."""
    conf = read_conf()

    dockerfile_path = Path.cwd() / "Dockerfile"
    if dockerfile_path.exists():
        overwrite = typer.confirm("Dockerfile already exists. Overwrite?", default=False)
        if not overwrite:
            raise typer.Abort()

    reqs_path = _ensure_requirements()
    reqs_text = reqs_path.read_text(encoding="utf-8")
    has_git = _has_git_lines(reqs_text)
    sdk_source = _find_sdk_source()

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("Dockerfile.j2")
    rendered = template.render(
        service_file=conf.service_file,
        has_git_deps=has_git,
        sdk_local=sdk_source is not None,
    )

    dockerfile_path.write_text(rendered, encoding="utf-8")
    rprint(f"[green]Generated {dockerfile_path}[/green]")


@docker_app.command("build")
def docker_build_cmd(
    tag: str = typer.Option(
        None, "--tag", "-t",
        help="Image tag. Defaults to the service id from lynxConf.json.",
    ),
):
    """Build a Docker image for a Lynx Service."""
    conf = read_conf()

    reqs_path = _ensure_requirements()
    reqs_text = reqs_path.read_text(encoding="utf-8")
    has_git = _has_git_lines(reqs_text)
    sdk_source = _find_sdk_source()

    # Write a filtered requirements file for Docker (no git+ lines)
    docker_reqs = Path.cwd() / "requirements.docker.txt"
    if has_git:
        docker_reqs.write_text(_filter_git_lines(reqs_text), encoding="utf-8")

    # Copy SDK source into build context if not already in cwd
    copied_sdk = False
    if sdk_source is not None and sdk_source != Path.cwd():
        shutil.copytree(sdk_source / "src", Path.cwd() / "src", dirs_exist_ok=True)
        shutil.copy2(sdk_source / "pyproject.toml", Path.cwd() / "pyproject.toml")
        copied_sdk = True

    # Always (re)generate Dockerfile to reflect current state
    dockerfile_path = Path.cwd() / "Dockerfile"
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("Dockerfile.j2")
    rendered = template.render(
        service_file=conf.service_file,
        has_git_deps=has_git,
        sdk_local=sdk_source is not None,
    )
    dockerfile_path.write_text(rendered, encoding="utf-8")

    if tag is None:
        tag = conf.service_file.replace(".py", "").replace("/", "-").replace("\\", "-")

    rprint(f"Building image [bold]{tag}[/bold]...")
    result = subprocess.run(
        ["docker", "build", "-t", tag, "."],
        cwd=str(Path.cwd()),
    )

    # Cleanup temporary build artifacts
    if docker_reqs.exists():
        docker_reqs.unlink()
    if copied_sdk:
        shutil.rmtree(Path.cwd() / "src", ignore_errors=True)
        (Path.cwd() / "pyproject.toml").unlink(missing_ok=True)

    if result.returncode != 0:
        rprint("[red]Docker build failed. See output above.[/red]")
        raise typer.Exit(code=1)

    rprint(f"[green]Successfully built image: {tag}[/green]")
