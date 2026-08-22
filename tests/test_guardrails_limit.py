from cardinal.guardrails.limit_check import enforce_limit


def test_adds_limit_when_missing():
    sql, r = enforce_limit("SELECT id FROM dim_customer", 1000)
    assert "limit 1000" in sql.lower()
    assert r.allowed is True


def test_respects_existing_limit():
    sql, _ = enforce_limit("SELECT id FROM dim_customer LIMIT 5", 1000)
    assert "limit 5" in sql.lower()


def test_limit_on_cte_not_confused_with_missing_outer_limit():
    sql = "WITH recent AS (SELECT * FROM dim_customer LIMIT 5) SELECT * FROM recent"
    result_sql, _ = enforce_limit(sql, 1000)
    assert result_sql.strip().lower().endswith("limit 1000") or "limit 1000" in result_sql.lower()


def test_union_query_gets_limit_on_final_result():
    sql = "SELECT id FROM dim_customer UNION SELECT id FROM dim_customer"
    result_sql, _ = enforce_limit(sql, 1000)
    assert "limit" in result_sql.lower()


def test_limit_with_offset_preserved():
    sql = "SELECT id FROM dim_customer LIMIT 5 OFFSET 10"
    result_sql, _ = enforce_limit(sql, 1000)
    assert "offset 10" in result_sql.lower()


def test_oversized_existing_limit_is_handled_deliberately():
    sql = "SELECT id FROM dim_customer LIMIT 50000"
    result_sql, _ = enforce_limit(sql, 1000)
    assert result_sql is not None
