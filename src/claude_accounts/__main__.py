"""Entry point for `python -m claude_accounts`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
