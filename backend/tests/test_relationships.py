from app.core.relationships import FKEdge, RelationshipGraph, infer_fk_edges


def _graph():
    g = RelationshipGraph()
    g.add_edge(FKEdge("orders", "user_id", "users", "id"))
    g.add_edge(FKEdge("orders", "product_id", "products", "id"))
    return g


def test_direct_join_path():
    g = _graph()
    ctx = g.resolve_join_path(["orders", "users"])
    assert ctx == "orders.user_id = users.id"


def test_multi_table_join_path():
    g = _graph()
    ctx = g.resolve_join_path(["orders", "users", "products"])
    lines = ctx.split("\n")
    assert "orders.user_id = users.id" in lines
    assert "orders.product_id = products.id" in lines
    assert len(lines) == 2


def test_transitive_path_via_bfs():
    # users and products are only connected THROUGH orders
    g = _graph()
    ctx = g.resolve_join_path(["users", "products"])
    lines = set(ctx.split("\n"))
    assert "orders.user_id = users.id" in lines
    assert "orders.product_id = products.id" in lines


def test_single_table_no_joins():
    assert _graph().resolve_join_path(["orders"]) == ""


def test_json_round_trip():
    g = _graph()
    g2 = RelationshipGraph.from_json(g.to_json())
    assert g2.resolve_join_path(["orders", "users"]) == "orders.user_id = users.id"


# --- 1-hop neighbours (join expansion) ---------------------------------- #
def test_neighbors_one_hop():
    g = _graph()
    assert g.neighbors(["orders"]) == {"users", "products"}
    assert g.neighbors(["users"]) == {"orders"}
    assert g.neighbors(["users", "orders"]) == {"products"}  # excludes given set


def test_neighbors_of_unconnected_table():
    g = _graph()
    assert g.neighbors(["nonexistent"]) == set()


# --- Heuristic FK inference (TSD §3b) ----------------------------------- #
def _tables_no_fk():
    return {
        "orders": [
            {"name": "id", "type": "integer"},
            {"name": "user_id", "type": "integer"},
            {"name": "product_id", "type": "integer"},
        ],
        "users": [{"name": "id", "type": "integer"}],
        "products": [{"name": "id", "type": "integer"}],
    }


def test_infer_edges_when_no_explicit_fks():
    edges = infer_fk_edges(_tables_no_fk(), explicit=[])
    pairs = {(e.source_table, e.source_column, e.target_table, e.target_column) for e in edges}
    assert ("orders", "user_id", "users", "id") in pairs
    assert ("orders", "product_id", "products", "id") in pairs
    assert all(e.confidence == "inferred" for e in edges)


def test_infer_skips_columns_with_explicit_fk():
    explicit = [FKEdge("orders", "user_id", "users", "id")]
    edges = infer_fk_edges(_tables_no_fk(), explicit=explicit)
    srcs = {(e.source_table, e.source_column) for e in edges}
    assert ("orders", "user_id") not in srcs        # already explicit
    assert ("orders", "product_id") in srcs         # still inferred


def test_infer_rejects_type_mismatch():
    tables = {
        "orders": [{"name": "user_id", "type": "uuid"}],   # uuid
        "users": [{"name": "id", "type": "integer"}],       # int -> no match
    }
    assert infer_fk_edges(tables, explicit=[]) == []


def test_infer_requires_target_table_and_id():
    tables = {"orders": [{"name": "widget_id", "type": "integer"}]}  # no widgets table
    assert infer_fk_edges(tables, explicit=[]) == []


def test_inferred_edges_feed_join_resolution():
    g = RelationshipGraph()
    for e in infer_fk_edges(_tables_no_fk(), explicit=[]):
        g.add_edge(e)
    assert g.resolve_join_path(["orders", "users"]) == "orders.user_id = users.id"
