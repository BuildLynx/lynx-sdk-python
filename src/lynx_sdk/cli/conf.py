"""
Reader/writer for lynxConf.json — the project-level configuration file
that all CLI commands use to locate the user's service.
"""

import json
from pathlib import Path
from typing import Optional

CONF_FILENAME = "lynxConf.json"

REQUIRED_KEYS = {"ServiceFile", "ServiceObject", "UpstreamNodeHost", "UpstreamNodePort"}


class LynxConf:
    """Parsed representation of a lynxConf.json file."""

    def __init__(
        self,
        service_file: str,
        service_object: str,
        upstream_node_host: str,
        upstream_node_port: int,
    ):
        self.service_file = service_file
        self.service_object = service_object
        self.upstream_node_host = upstream_node_host
        self.upstream_node_port = upstream_node_port

    def to_dict(self) -> dict:
        return {
            "ServiceFile": self.service_file,
            "ServiceObject": self.service_object,
            "UpstreamNodeHost": self.upstream_node_host,
            "UpstreamNodePort": self.upstream_node_port,
        }


def find_conf(start_dir: Optional[Path] = None) -> Path:
    """
    Locate lynxConf.json in the given directory (defaults to cwd).
    Raises FileNotFoundError if not found.
    """
    directory = start_dir or Path.cwd()
    conf_path = directory / CONF_FILENAME
    if not conf_path.exists():
        raise FileNotFoundError(
            f"{CONF_FILENAME} not found in {directory}. Run 'lynx init' first."
        )
    return conf_path


def read_conf(conf_path: Optional[Path] = None) -> LynxConf:
    """
    Read and validate a lynxConf.json file. If no path is given,
    searches the current working directory.
    """
    if conf_path is None:
        conf_path = find_conf()

    with open(conf_path, "r") as f:
        data = json.load(f)

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(
            f"{CONF_FILENAME} is missing required keys: {', '.join(sorted(missing))}"
        )

    return LynxConf(
        service_file=data["ServiceFile"],
        service_object=data["ServiceObject"],
        upstream_node_host=data["UpstreamNodeHost"],
        upstream_node_port=int(data["UpstreamNodePort"]),
    )


def write_conf(conf: LynxConf, directory: Optional[Path] = None) -> Path:
    """Write a LynxConf to lynxConf.json in the given directory (defaults to cwd)."""
    directory = directory or Path.cwd()
    conf_path = directory / CONF_FILENAME
    with open(conf_path, "w") as f:
        json.dump(conf.to_dict(), f, indent=4)
    return conf_path
