# Persistence Layer

SQL-based persistence using sqlc-generated queries with SQLAlchemy async.

## Architecture

```
persistence/
├── db/
│   ├── schema.sql          # Database schema (tables, indexes)
│   └── queries/
│       ├── interactions.sql # Interaction CRUD queries
│       └── user_prefs.sql   # User preferences queries
├── generated/              # sqlc-generated Python code (DO NOT EDIT)
│   ├── models.py           # Dataclasses for table rows
│   ├── interactions.py     # AsyncQuerier for interactions
│   └── user_prefs.py       # AsyncQuerier for user prefs
├── connection.py           # SQLAlchemy async engine management
└── sql_feedback.py         # FeedbackStore implementation
```

## Regenerating Queries

After editing SQL files in `db/queries/`, regenerate the Python code:

```bash
# 1. Generate Python code from SQL
sqlc generate

# 2. Fix placeholders for SQLAlchemy compatibility
python3 scripts/fix_sqlc_placeholders.py

# 3. Fix imports (if needed)
sed -i '' 's/from queries import models/from . import models/g' \
    src/clanker_bot/persistence/generated/*.py

# 4. Run linter
uv run ruff check src/clanker_bot/persistence/generated/ --fix
uv run ruff format src/clanker_bot/persistence/generated/
```

## Why the placeholder fix?

sqlc-gen-python generates SQL with `?` placeholders (SQLite positional style),
but SQLAlchemy's `text()` requires named parameters (`:p1`, `:p2`, etc.).
The fix script converts `?` → `:pN` to match the parameter dictionaries.

## Adding New Queries

1. Add SQL to the appropriate file in `db/queries/`
2. Use sqlc annotations: `-- name: query_name :one|:many|:exec`
3. Run the regeneration steps above
4. Use the generated `AsyncQuerier` methods in your code

## Configuration

- `sqlc.yaml` in project root defines generation settings
- Uses `sqlc-gen-python` v1.3.0 WASM plugin
- Targets SQLite engine (works with aiosqlite)
