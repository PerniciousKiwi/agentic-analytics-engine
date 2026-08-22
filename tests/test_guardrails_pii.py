import pytest

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.pii_check import check_pii


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load(
        manifest_path="warehouse/target/manifest.json",
        catalog_path="warehouse/target/catalog.json",
        metrics_path="warehouse/semantic/metrics.yml",
        glossary_path="warehouse/semantic/glossary.yml",
    )


def test_pii_column_rejected_for_analyst(catalog):
    r = check_pii(
        "SELECT customer_id FROM dim_customer",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert "PII_COLUMN_FORBIDDEN: customer_id" in r.reasons


def test_customer_unique_id_rejected_for_analyst(catalog):
    r = check_pii(
        "SELECT customer_unique_id FROM dim_customer",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert "PII_COLUMN_FORBIDDEN: customer_unique_id" in r.reasons


def test_non_pii_column_allowed_for_analyst(catalog):
    r = check_pii(
        "SELECT customer_city FROM dim_customer",
        catalog,
        role="analyst",
    )
    assert r.allowed is True
    assert r.reasons == []


def test_multiple_pii_columns_rejected(catalog):
    r = check_pii(
        "SELECT customer_id, customer_unique_id FROM dim_customer",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert "PII_COLUMN_FORBIDDEN: customer_id" in r.reasons
    assert "PII_COLUMN_FORBIDDEN: customer_unique_id" in r.reasons


def test_pii_column_in_expression_rejected(catalog):
    r = check_pii(
        "SELECT COUNT(customer_id) FROM dim_customer",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert "PII_COLUMN_FORBIDDEN: customer_id" in r.reasons


def test_pii_column_in_where_clause_rejected(catalog):
    r = check_pii(
        "SELECT customer_city FROM dim_customer WHERE customer_id = 'abc'",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert "PII_COLUMN_FORBIDDEN: customer_id" in r.reasons


def test_privileged_role_can_access_pii(catalog):
    r = check_pii(
        "SELECT customer_id, customer_unique_id FROM dim_customer",
        catalog,
        role="privileged",
    )
    assert r.allowed is True
    assert r.reasons == []


def test_invalid_sql_rejected(catalog):
    r = check_pii(
        "SELECT FROM WHERE",
        catalog,
        role="analyst",
    )
    assert r.allowed is False
    assert any(reason.startswith("SQL_PARSE_ERROR:") for reason in r.reasons)
