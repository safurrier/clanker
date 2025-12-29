#!/usr/bin/env python3
"""Fix sqlc-generated Python files to use SQLAlchemy-compatible placeholders.

sqlc-gen-python generates SQL with ? placeholders (SQLite positional style),
but SQLAlchemy's text() requires named parameters (:p1, :p2, etc.).

This script converts ? to :pN format in the generated files.

Usage:
    python scripts/fix_sqlc_placeholders.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def convert_placeholders_in_sql(content: str) -> str:
    """Convert ? placeholders to :pN format in SQL string literals."""

    def convert_sql_string(match: re.Match[str]) -> str:
        sql = match.group(0)
        count = [0]

        def replace(_: re.Match[str]) -> str:
            count[0] += 1
            return f":p{count[0]}"

        return re.sub(r"\?", replace, sql)

    # Match triple-quoted strings that appear to be SQL
    pattern = r'"""[^"]*?(?:SELECT|INSERT|UPDATE|DELETE|--)[^"]*?"""'
    return re.sub(pattern, convert_sql_string, content, flags=re.IGNORECASE | re.DOTALL)


def main() -> int:
    """Process all generated files."""
    generated_dir = Path(__file__).parent.parent / "src/clanker_bot/persistence/generated"

    if not generated_dir.exists():
        print(f"Error: Generated directory not found: {generated_dir}")
        return 1

    files_fixed = 0
    for filepath in generated_dir.glob("*.py"):
        if filepath.name == "__init__.py":
            continue

        content = filepath.read_text()
        new_content = convert_placeholders_in_sql(content)

        if content != new_content:
            filepath.write_text(new_content)
            print(f"Fixed: {filepath.name}")
            files_fixed += 1
        else:
            print(f"No changes: {filepath.name}")

    print(f"\nDone! {files_fixed} file(s) updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
