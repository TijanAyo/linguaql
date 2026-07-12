"""Dialect detection + MySQL adapter pieces (TSD: asyncpg + aiomysql)."""
import pytest

from app.agents.llm import _DIALECT_NAMES, _SYSTEM_TEMPLATE
from app.utils.db_connections import _my_explain_cost, dialect_of
from app.utils.sql_parser import complexity_score, validate_sql

CATALOG = {
    "orders": ["id", "user_id", "amount", "created_at"],
    "users": ["id", "name"],
}


@pytest.mark.parametrize(
    "url,expected",
    [
        ("postgresql://u:p@h:5432/db", "postgres"),
        ("postgres://u:p@h/db", "postgres"),
        ("postgresql+asyncpg://u:p@h/db", "postgres"),
        ("mysql://u:p@h:3306/db", "mysql"),
        ("mariadb://u:p@h/db", "mysql"),
        ("mysql+aiomysql://u:p@h/db", "mysql"),
    ],
)
def test_dialect_of(url, expected):
    assert dialect_of(url) == expected


def test_mysql_explain_cost_parsed():
    payload = {"query_block": {"select_id": 1, "cost_info": {"query_cost": "42.7"}}}
    assert _my_explain_cost(payload) == pytest.approx(42.7)


def test_mysql_explain_cost_missing_is_zero():
    assert _my_explain_cost({"query_block": {"select_id": 1}}) == 0.0


def test_validate_mysql_backtick_identifiers():
    sql = "SELECT `amount` FROM `orders` WHERE `user_id` = 1"
    assert validate_sql(sql, CATALOG, dialect="mysql") == []


def test_validate_mysql_still_catches_unknown_column():
    errors = validate_sql("SELECT bogus FROM orders", CATALOG, dialect="mysql")
    assert any("Unknown column" in e for e in errors)


def test_validate_mysql_rejects_destructive():
    errors = validate_sql("DROP TABLE orders", CATALOG, dialect="mysql")
    assert errors and "Rejected" in errors[0]


def test_complexity_score_mysql_dialect():
    # DATE_FORMAT is MySQL-specific; still parses under the mysql dialect.
    sql = "SELECT DATE_FORMAT(created_at, '%Y-%m') m, SUM(amount) FROM orders GROUP BY 1"
    score, _ = complexity_score(sql, dialect="mysql")  # no WHERE(+20) + no LIMIT(+15)
    assert score == 35


def test_generator_prompt_is_dialect_specific():
    assert _DIALECT_NAMES["mysql"] == "MySQL"
    assert "MySQL" in _SYSTEM_TEMPLATE.format(dialect="MySQL")
    assert "PostgreSQL" in _SYSTEM_TEMPLATE.format(dialect="PostgreSQL")
