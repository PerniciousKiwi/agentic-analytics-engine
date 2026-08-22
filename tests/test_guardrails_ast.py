from cardinal.guardrails.ast_checks import check_read_only


def test_select_is_allowed() -> None:
    result = check_read_only("SELECT * FROM marts.fct_orders")

    assert result.allowed is True
    assert result.reasons == []


def test_delete_is_rejected() -> None:
    result = check_read_only("DELETE FROM marts.fct_orders")

    assert result.allowed is False
    assert "READ_ONLY_VIOLATION: DELETE" in result.reasons


def test_invalid_sql_is_rejected() -> None:
    result = check_read_only("SELECT * FROM")

    assert result.allowed is False
    assert result.reasons[0].startswith("SQL_PARSE_ERROR:")
