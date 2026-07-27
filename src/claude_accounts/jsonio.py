"""Reading and writing the JSON files this tool owns."""

import json
import os
import stat

from .term import CliError


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        raise CliError(f"cannot read {path}: {exc}")


def write_json(path: str, data, private: bool = False) -> None:
    """Atomic write. `private` chmods the result to 0600 (no-op on Windows)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    if private:
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    os.replace(tmp, path)
