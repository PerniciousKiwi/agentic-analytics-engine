from __future__ import annotations

from cardinal.agent.repair import (
    FailureClass,
    classify_failure,
    identifier_candidates,
    run_with_repair,
)
from cardinal.catalog.catalog import Catalog
from cardinal.catalog.manifest import Column, Manifest, Relation
from cardinal.catalog.models import Glossary
from cardinal.guardrails.ast_checks import GuardResult
from cardinal.guardrails.pipeline import GuardrailResult


def make_catalog() -> Catalog:
    relation = Relation(
        unique_id="model.orders",
        name="orders",
        schema_name="marts",
        database=None,
        resource_type="model",
        columns={
            "order_id": Column(
                name="order_id",
                data_type="integer",
            ),
            "customer_id": Column(
                name="customer_id",
                data_type="integer",
            ),
            "order_date": Column(
                name="order_date",
                data_type="date",
            ),
        },
    )

    manifest = Manifest(
        relations={
            relation.unique_id: relation,
        }
    )

    glossary = Glossary(
        version=1,
        glossary={},
        pii_columns=[],
    )

    return Catalog(
        manifest=manifest,
        metrics=[],
        glossary=glossary,
    )


def test_unknown_column_guard_result() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["UNKNOWN_COLUMN: fake_column"],
    )

    assert classify_failure(result) == FailureClass.UNKNOWN_COLUMN


def test_unknown_table_guard_result() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["UNKNOWN_TABLE: fake_table"],
    )

    assert classify_failure(result) == FailureClass.UNKNOWN_TABLE


def test_ambiguous_column_guard_result() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["AMBIGUOUS_COLUMN: order_id"],
    )

    assert classify_failure(result) == FailureClass.AMBIGUOUS_COLUMN


def test_sql_parse_error_guard_result() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["SQL_PARSE_ERROR: invalid SQL"],
    )

    assert classify_failure(result) == FailureClass.SYNTAX


def test_guardrail_result_classification() -> None:
    result = GuardrailResult(
        sql="SELECT fake_column FROM marts.orders",
        result=GuardResult(
            allowed=False,
            reasons=["UNKNOWN_COLUMN: fake_column"],
        ),
    )

    assert classify_failure(result) == FailureClass.UNKNOWN_COLUMN


def test_database_sqlstate_classification() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "42703"

    assert classify_failure(FakeDatabaseError("undefined column")) == (FailureClass.UNKNOWN_COLUMN)


def test_database_diag_sqlstate_classification() -> None:
    class FakeDiag:
        sqlstate = "42P01"

    class FakeDatabaseErrorWithDiagError(Exception):
        diag = FakeDiag()

    assert (
        classify_failure(FakeDatabaseErrorWithDiagError("undefined table"))
        == FailureClass.UNKNOWN_TABLE
    )


def test_unknown_sqlstate_maps_to_other() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "99999"

    assert classify_failure(FakeDatabaseError("unknown")) == FailureClass.OTHER


def test_missing_sqlstate_maps_to_other() -> None:
    class FakeDatabaseError(Exception):
        pass

    assert classify_failure(FakeDatabaseError("unknown")) == FailureClass.OTHER


def test_sqlstate_type_mismatch() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "22P02"

    assert classify_failure(FakeDatabaseError("invalid input syntax")) == (
        FailureClass.TYPE_MISMATCH
    )


def test_sqlstate_type_mismatch_42804() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "42804"

    assert classify_failure(FakeDatabaseError("datatype mismatch")) == (FailureClass.TYPE_MISMATCH)


def test_sqlstate_syntax_error() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "42601"

    assert classify_failure(FakeDatabaseError("syntax error")) == FailureClass.SYNTAX


def test_sqlstate_aggregation_error() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "42803"

    assert classify_failure(FakeDatabaseError("grouping error")) == (FailureClass.AGGREGATION_ERROR)


def test_sqlstate_timeout() -> None:
    class FakeDatabaseError(Exception):
        sqlstate = "57014"

    assert classify_failure(FakeDatabaseError("statement timeout")) == (FailureClass.TIMEOUT)


def test_identifier_candidates_for_unknown_table() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT * FROM marts.ordres",
        FailureClass.UNKNOWN_TABLE,
        "ordres",
        catalog,
    )

    assert candidates[0] == "orders"


def test_identifier_candidates_for_unknown_column() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT custmer_id FROM marts.orders",
        FailureClass.UNKNOWN_COLUMN,
        "custmer_id",
        catalog,
    )

    assert candidates[0] == "orders.customer_id"


def test_identifier_candidates_for_qualified_unknown_column() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT o.custmer_id FROM marts.orders AS o",
        FailureClass.UNKNOWN_COLUMN,
        "o.custmer_id",
        catalog,
    )

    assert candidates[0] == "customer_id"


def test_identifier_candidates_for_ambiguous_column() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT order_i FROM marts.orders",
        FailureClass.AMBIGUOUS_COLUMN,
        "order_i",
        catalog,
    )

    assert "orders.order_id" in candidates


def test_identifier_candidates_return_empty_for_other_failure() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT * FROM marts.orders",
        FailureClass.SYNTAX,
        "orders",
        catalog,
    )

    assert candidates == []


def test_identifier_candidates_are_unique() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT custmer_id FROM marts.orders",
        FailureClass.UNKNOWN_COLUMN,
        "custmer_id",
        catalog,
    )

    assert len(candidates) == len(set(candidates))


def test_identifier_candidates_are_limited_to_five() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT custmer_id FROM marts.orders",
        FailureClass.UNKNOWN_COLUMN,
        "custmer_id",
        catalog,
        limit=5,
    )

    assert len(candidates) <= 5


def test_identifier_candidates_for_unqualified_column() -> None:
    catalog = make_catalog()

    candidates = identifier_candidates(
        "SELECT custmer_id FROM marts.orders",
        FailureClass.UNKNOWN_COLUMN,
        "custmer_id",
        catalog,
    )

    assert "orders.customer_id" in candidates


def test_repair_loop_bad_bad_good() -> None:
    generated_sql = "SELECT bad_column FROM marts.orders;"
    repaired_sql_1 = "SELECT still_bad FROM marts.orders;"
    repaired_sql_2 = "SELECT order_id FROM marts.orders;"

    generated = iter([generated_sql])
    repairs = iter([repaired_sql_1, repaired_sql_2])

    catalog = make_catalog()

    def generate_fn(question: str) -> str:
        return next(generated)

    def guard_fn(
        sql: str,
        catalog: object,
        cost_budget: float,
    ) -> GuardrailResult:
        if sql == repaired_sql_2:
            return GuardrailResult(
                sql=sql,
                result=GuardResult(allowed=True),
            )

        return GuardrailResult(
            sql=sql,
            result=GuardResult(
                allowed=False,
                reasons=["UNKNOWN_COLUMN: bad_column"],
            ),
        )

    def execute_fn(sql: str) -> None:
        return None

    repair_calls: list[tuple[str, FailureClass]] = []

    def repair_fn(
        question: str,
        failed_sql: str,
        failure_class: FailureClass,
        error_message: str,
        candidates: list[str],
        cost_budget: float,
    ) -> str:
        repair_calls.append((failed_sql, failure_class))
        return next(repairs)

    result = run_with_repair(
        "How many orders are there?",
        catalog,
        generate_fn,
        guard_fn,
        execute_fn,
        repair_fn,
        max_attempts=3,
        cost_budget=100.0,
    )

    assert result.succeeded is True
    assert result.sql == repaired_sql_2
    assert len(result.attempts) == 3

    assert result.attempts[0].failure_class == FailureClass.UNKNOWN_COLUMN
    assert result.attempts[1].failure_class == FailureClass.UNKNOWN_COLUMN
    assert result.attempts[2].failure_class is None

    assert len(repair_calls) == 2


def test_repair_loop_rejects_identical_query() -> None:
    sql = "SELECT bad_column FROM marts.orders;"

    catalog = make_catalog()

    def generate_fn(question: str) -> str:
        return sql

    def guard_fn(
        sql: str,
        catalog: object,
        cost_budget: float,
    ) -> GuardrailResult:
        return GuardrailResult(
            sql=sql,
            result=GuardResult(
                allowed=False,
                reasons=["UNKNOWN_COLUMN: bad_column"],
            ),
        )

    def execute_fn(sql: str) -> None:
        raise AssertionError("Execution should not be reached.")

    repair_calls = 0

    def repair_fn(
        question: str,
        failed_sql: str,
        failure_class: FailureClass,
        error_message: str,
        candidates: list[str],
        cost_budget: float,
    ) -> str:
        nonlocal repair_calls
        repair_calls += 1
        return sql

    result = run_with_repair(
        "How many orders are there?",
        catalog,
        generate_fn,
        guard_fn,
        execute_fn,
        repair_fn,
        max_attempts=3,
        cost_budget=100.0,
    )

    assert result.succeeded is False
    assert result.sql is None
    assert len(result.attempts) == 1
    assert repair_calls == 1


def test_repair_loop_halves_cost_budget_after_timeout() -> None:
    sql = "SELECT * FROM marts.orders;"
    repaired_sql = "SELECT order_id FROM marts.orders;"

    budgets: list[float] = []
    repairs: list[float] = []

    catalog = make_catalog()

    def generate_fn(question: str) -> str:
        return sql

    def guard_fn(
        sql: str,
        catalog: object,
        cost_budget: float,
    ) -> GuardrailResult:
        budgets.append(cost_budget)

        return GuardrailResult(
            sql=sql,
            result=GuardResult(allowed=True),
        )

    def execute_fn(current_sql: str) -> None:
        if current_sql == sql:

            class FakeTimeoutError(Exception):
                sqlstate = "57014"

            raise FakeTimeoutError("statement timeout")

    def repair_fn(
        question: str,
        failed_sql: str,
        failure_class: FailureClass,
        error_message: str,
        candidates: list[str],
        cost_budget: float,
    ) -> str:
        repairs.append(cost_budget)
        return repaired_sql

    result = run_with_repair(
        "How many orders are there?",
        catalog,
        generate_fn,
        guard_fn,
        execute_fn,
        repair_fn,
        max_attempts=3,
        cost_budget=100.0,
    )

    assert result.succeeded is True
    assert result.sql == repaired_sql

    assert budgets == [100.0, 50.0]
    assert repairs == [50.0]


def test_repair_loop_respects_max_attempts() -> None:
    sqls = [
        "SELECT bad_one FROM marts.orders;",
        "SELECT bad_two FROM marts.orders;",
        "SELECT bad_three FROM marts.orders;",
    ]

    generated = iter(sqls)

    catalog = make_catalog()

    def generate_fn(question: str) -> str:
        return next(generated)

    def guard_fn(
        sql: str,
        catalog: object,
        cost_budget: float,
    ) -> GuardrailResult:
        return GuardrailResult(
            sql=sql,
            result=GuardResult(
                allowed=False,
                reasons=["UNKNOWN_COLUMN: bad_column"],
            ),
        )

    def execute_fn(sql: str) -> None:
        raise AssertionError("Execution should not be reached.")

    repairs = iter([sqls[1], sqls[2]])

    def repair_fn(
        question: str,
        failed_sql: str,
        failure_class: FailureClass,
        error_message: str,
        candidates: list[str],
        cost_budget: float,
    ) -> str:
        return next(repairs)

    result = run_with_repair(
        "How many orders are there?",
        catalog,
        generate_fn,
        guard_fn,
        execute_fn,
        repair_fn,
        max_attempts=3,
        cost_budget=100.0,
    )

    assert result.succeeded is False
    assert result.sql is None
    assert len(result.attempts) == 3


def test_mode_mismatch_has_dedicated_failure_class() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["MODE_MISMATCH: expected mode query"],
    )

    assert classify_failure(result) == FailureClass.MODE_MISMATCH


def test_superlative_mismatch_has_dedicated_failure_class() -> None:
    result = GuardResult(
        allowed=False,
        reasons=["SUPERLATIVE_MISMATCH: expected ordering"],
    )

    assert classify_failure(result) == FailureClass.SUPERLATIVE_MISMATCH
