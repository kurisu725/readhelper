from .history import init_schema, handle, markdown
from .research import labels, instruction


def has_data(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='history_records'").fetchone())
