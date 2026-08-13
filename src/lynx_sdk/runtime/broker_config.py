"""
Resolve the MQTT broker host and port from the process environment.

Generative AI was used in the Creation/Modification of this file.
"""

import json
import os
from pathlib import Path
from typing import Tuple

_CONF_FILENAME = "lynxConf.json"


def resolve_broker_socket() -> Tuple[str, int]:
    """
    Resolve the MQTT broker (host, port) using the following priority:
      1. UPSTREAM_NODE_HOST / UPSTREAM_NODE_PORT environment variables
      2. UpstreamNodeHost / UpstreamNodePort from lynxConf.json (searched in cwd)
      3. ("localhost", 1883)
    """
    env_host = os.environ.get("UPSTREAM_NODE_HOST")
    if env_host is not None:
        port = int(os.environ.get("UPSTREAM_NODE_PORT", "1883"))
        return (env_host, port)

    conf_path = Path.cwd() / _CONF_FILENAME
    if conf_path.is_file():
        try:
            with open(conf_path, "r") as f:
                data = json.load(f)
            host = data.get("UpstreamNodeHost")
            if host is not None:
                port = int(data.get("UpstreamNodePort", 1883))
                return (host, port)
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    return ("localhost", 1883)
