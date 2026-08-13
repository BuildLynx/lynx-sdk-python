"""
Service discovery — imports a user's Python module and resolves
the Service instance for CLI introspection.

Generative AI was used in the Creation/Modification of this file.
"""

import importlib.util
import sys
from pathlib import Path

from lynx_sdk import Service


def load_service(target: str) -> Service:
    """
    Load a Service from a target string.

    Accepts:
      - "path/to/file.py"           -> import module, find first Service instance
      - "path/to/file.py:varname"   -> import module, get specific attribute
      - "my_package.module:varname"  -> dotted import path
    """
    if ":" in target:
        module_path, var_name = target.rsplit(":", 1)
    else:
        module_path, var_name = target, None

    module = _import_module(module_path)

    if var_name:
        obj = getattr(module, var_name, None)
        if obj is None:
            raise AttributeError(
                f"Module has no attribute '{var_name}'"
            )
        if not isinstance(obj, Service):
            raise TypeError(
                f"'{var_name}' is a {type(obj).__name__}, not a Service instance"
            )
        return obj

    return _auto_discover(module, module_path)


def _import_module(module_path: str):
    """Import a module from a file path or dotted module name."""
    path = Path(module_path)
    if path.suffix == ".py" and path.exists():
        path = path.resolve()
        spec = importlib.util.spec_from_file_location("_lynx_user_module", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {path}")

        # Ensure the file's directory is importable (for relative imports in user code)
        parent_dir = str(path.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return importlib.import_module(module_path)


def _auto_discover(module, module_path: str) -> Service:
    """Scan a module's attributes and return the single Service instance found."""
    services = {
        name: obj
        for name, obj in vars(module).items()
        if isinstance(obj, Service)
    }

    if len(services) == 0:
        raise RuntimeError(
            f"No Service instance found in '{module_path}'"
        )

    if len(services) == 1:
        return next(iter(services.values()))

    names = ", ".join(sorted(services.keys()))
    raise RuntimeError(
        f"Multiple Service instances found in '{module_path}': {names}. "
        f"Specify one with: {module_path}:<name>"
    )
