"""Allow ``python -m knowledge_capture`` to invoke the CLI."""

from __future__ import annotations

from knowledge_capture.cli import app

if __name__ == "__main__":
    app()
