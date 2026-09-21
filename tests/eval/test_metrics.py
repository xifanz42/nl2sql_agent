from app.eval.metrics import canonical_rows, execution_match, exact_match, schema_adherence

# Synthetic schema: never reference real tables/columns in public test code.
SCHEMA = {"orders": {}, "customers": {}}


def test_exact_match_ignores_formatting():
    assert exact_match("select a from t;", "SELECT a FROM t")


def test_execution_match_is_order_insensitive():
    assert execution_match([{"n": 1}, {"n": 2}], [{"n": 2}, {"n": 1}])
    assert not execution_match([{"n": 1}], [{"n": 2}])


def test_execution_match_accepts_cached_tuples():
    assert execution_match([{"n": 1}], [(1,)])


def test_canonical_rows_normalizes_float_noise():
    assert canonical_rows([{"v": 1.000000001}]) == canonical_rows([{"v": 1.0}])


def test_schema_adherence_rejects_unknown_table():
    assert schema_adherence("SELECT * FROM orders", SCHEMA)
    assert not schema_adherence("SELECT * FROM unknown_table", SCHEMA)


def test_parsing_prose_does_not_raise():
    """Regression: sqlglot raises TokenError (not just ParseError) on prose."""
    from app.eval.metrics import is_read_only_select

    assert not is_read_only_select("I can't write that query")
    assert not schema_adherence("the answer is 5 rows, isn't it", SCHEMA)
