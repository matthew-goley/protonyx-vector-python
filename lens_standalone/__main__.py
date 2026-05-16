"""CLI entry point — only runs when invoked as `python -m lens_standalone`.

If the package is imported back into the Vector app, this module is never
executed; the app imports `lens_standalone.lens.lens_output` directly.
"""

from __future__ import annotations

import sys

from .runner import run


if __name__ == '__main__':
    sys.exit(run())
