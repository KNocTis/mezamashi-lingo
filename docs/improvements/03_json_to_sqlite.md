# Transition from JSON to SQLite

**Rank:** Medium

Currently, `history.json` and `latest_selection.json` serve as a lightweight datastore. As your language learning history expands, loading and saving large JSON files into memory during every invocation could cause slight delays and risks data corruption if interrupted. Transitioning the `Repository` class to use SQLite (via `sqlite3` or an ORM like `SQLAlchemy`/`SQLModel`) would provide atomic transactions, query flexibility, and scalability.
