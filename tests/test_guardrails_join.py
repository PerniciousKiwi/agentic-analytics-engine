import pytest

from cardinal.guardrails.join_check import check_cartesian_join


def test_true_cartesian_rejected():
    r = check_cartesian_join(
        "SELECT * FROM dim_customer CROSS JOIN dim_products",
    )
    assert r.allowed is False
    assert any("CARTESIAN_JOIN" in reason for reason in r.reasons)


def test_comma_join_with_correlating_predicate_ok():
    sql = (
        "SELECT * FROM dim_customer c, "
        "fct_orders o WHERE c.customer_unique_id = o.customer_unique_id"
    )
    r = check_cartesian_join(sql)
    assert r.allowed is True


def test_explicit_join_with_on_ok():
    sql = (
        "SELECT * FROM dim_customer c "
        "JOIN fct_orders o ON c.customer_unique_id = o.customer_unique_id"
    )
    r = check_cartesian_join(sql)
    assert r.allowed is True


def test_comma_join_with_unrelated_where_still_rejected():
    sql = "SELECT * FROM dim_customer c, dim_products p WHERE c.customer_state = 'SP'"
    r = check_cartesian_join(sql)
    assert r.allowed is False


def test_three_table_mixed_join_with_one_cartesian_rejected():
    sql = """
    SELECT *
    FROM dim_customer c
    JOIN fct_orders o
        ON c.customer_unique_id = o.customer_unique_id,
    dim_products p
    """
    r = check_cartesian_join(sql)
    assert r.allowed is False


def test_allow_cartesian_override_passes():
    r = check_cartesian_join(
        "SELECT * FROM dim_customer, dim_products",
        allow_cartesian=True,
    )
    assert r.allowed is True


@pytest.mark.xfail(
    reason="ON TRUE is currently treated as a valid ON condition",
)
def test_left_join_on_true_is_a_known_gap():
    r = check_cartesian_join("SELECT * FROM dim_customer LEFT JOIN dim_products ON true")
    assert r.allowed is False
