from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Mapping, Sequence

from langchain_core.tools import tool


MAX_PREVIEW_ROWS = 50
FORBIDDEN_PATTERN = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b", re.IGNORECASE)
TABLE_PATTERN = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w\.\"']*)", re.IGNORECASE)
ALLOWED_TABLES: frozenset[str] = frozenset({"employees", "expertise_areas", "employee_expertise"})
DATABASE_PATH = Path(__file__).resolve().parents[3] / "data" / "team_mock.db"


@tool("sql")
def sql_tool(query: str) -> str:
    """
    Execute a read-only SQL SELECT query against the product team SQLite database.

    Available tables:
    - employees(id, first_name, last_name, email, role, years_of_experience)
    - expertise_areas(id, name, description)
    - employee_expertise(employee_id, expertise_id)
    """
    cleaned_query = _prepare_query(query)
    if not cleaned_query:
        return "Please provide a SQL SELECT query to run against the product team data."

    lowered = cleaned_query.lower()
    if not lowered.startswith("select"):
        return "Only SELECT queries are permitted."

    if FORBIDDEN_PATTERN.search(cleaned_query):
        return "Only read-only queries are allowed for the product team data."

    if not _query_targets_allowed_tables(cleaned_query):
        allowed = ", ".join(sorted(ALLOWED_TABLES))
        return f"Queries may reference only these tables: {allowed}."

    if not DATABASE_PATH.exists():
        return f"SQLite source database not found at {DATABASE_PATH}."

    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return _run_query(conn, cleaned_query)
    except Exception as exc:
        return f"SQL execution error: {exc}"


def _prepare_query(query: str | None) -> str:
    if not query:
        return ""
    return query.strip().rstrip(";")


def _run_query(conn: sqlite3.Connection, query: str) -> str:
    cursor = conn.execute(query)
    rows = cursor.fetchmany(MAX_PREVIEW_ROWS + 1)
    if not rows:
        return "Query returned no results."

    truncated = len(rows) > MAX_PREVIEW_ROWS
    display_rows = rows[:MAX_PREVIEW_ROWS]
    formatted = _format_rows(display_rows)
    if truncated:
        formatted += f"\n... (showing first {MAX_PREVIEW_ROWS} rows)"
    return formatted


def _format_rows(rows: Sequence[Mapping]) -> str:
    columns = list(rows[0].keys())
    header = " | ".join(columns)
    lines = [header, "-" * len(header)]
    for row in rows:
        line = " | ".join(_format_value(row[col]) for col in columns)
        lines.append(line)
    return "\n".join(lines)


def _format_value(value) -> str:
    if value is None:
        return "NULL"
    return str(value)


def _query_targets_allowed_tables(query: str) -> bool:
    tables = _extract_tables(query)
    if not tables:
        return True
    return all(table in ALLOWED_TABLES for table in tables)


def _extract_tables(query: str) -> Sequence[str]:
    table_refs = TABLE_PATTERN.findall(query)
    return [_normalize_table_reference(ref) for ref in table_refs]


def _normalize_table_reference(ref: str) -> str:
    token = ref.strip().strip(",")
    parts = [part.strip('"').strip("'") for part in token.split(".")]
    return parts[-1].lower()
