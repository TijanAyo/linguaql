from app.utils.sql_parser import validate_sql

CATALOG = {
    "orders": ["id", "user_id", "product_id", "amount", "created_at"],
    "users": ["id", "name", "country"],
    "products": ["id", "name", "price"],
}


def test_valid_select_passes():
    sql = "SELECT date_trunc('month', created_at) AS m, SUM(amount) AS revenue " \
          "FROM orders GROUP BY 1 ORDER BY 1"
    assert validate_sql(sql, CATALOG) == []


def test_valid_join_with_alias_passes():
    sql = (
        "SELECT u.country, SUM(o.amount) AS revenue "
        "FROM orders o JOIN users u ON o.user_id = u.id "
        "GROUP BY u.country"
    )
    assert validate_sql(sql, CATALOG) == []


def test_unknown_column_rejected():
    errors = validate_sql("SELECT nonexistent_col FROM orders", CATALOG)
    assert any("Unknown column" in e for e in errors)


def test_unknown_table_rejected():
    errors = validate_sql("SELECT id FROM ghosts", CATALOG)
    assert any("Unknown table" in e for e in errors)


def test_destructive_hard_rejected():
    for sql in [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET amount = 0",
        "INSERT INTO orders (id) VALUES (1)",
        "TRUNCATE orders",
    ]:
        errors = validate_sql(sql, CATALOG)
        assert errors and "Rejected" in errors[0], sql


def test_multiple_statements_rejected():
    errors = validate_sql("SELECT 1 FROM orders; DROP TABLE orders", CATALOG)
    assert errors


def test_cte_and_alias_allowed():
    sql = (
        "WITH monthly AS (SELECT amount FROM orders) "
        "SELECT SUM(amount) AS total FROM monthly"
    )
    assert validate_sql(sql, CATALOG) == []
