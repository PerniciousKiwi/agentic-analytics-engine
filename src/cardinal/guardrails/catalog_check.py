from __future__ import annotations

import sqlglot
from sqlglot import exp

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import GuardResult


def _projection_columns(query: exp.Expression) -> set[str]:
    """Return columns exposed by the immediate SELECT projection."""
    select = query if isinstance(query, exp.Select) else query.find(exp.Select)

    if select is None:
        return set()

    columns: set[str] = set()

    for expression in select.expressions:
        alias = expression.alias

        if alias:
            columns.add(alias.lower())
        elif isinstance(expression, exp.Column):
            columns.add(expression.name.lower())

    return columns


def _cte_columns(cte: exp.CTE) -> set[str]:
    """Return columns exposed by a CTE."""
    return _projection_columns(cte.this)


def _subquery_columns(subquery: exp.Subquery) -> set[str]:
    """Return columns exposed by a derived table."""
    return _projection_columns(subquery.this)


def _relation_columns(relation: object) -> set[str]:
    """Return normalized column names for a relation."""
    if isinstance(relation, set):
        return {str(name).lower() for name in relation}

    return {str(name).lower() for name in relation.columns}


def _register_table(
    relations: dict[str, object],
    table: exp.Table,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> None:
    """Register a physical table, CTE, and aliases."""
    table_name = table.name.lower()
    alias = table.alias_or_name.lower()

    # CTEs shadow physical tables with the same name.
    if table_name in cte_columns:
        relation = cte_columns[table_name]

        relations[table_name] = relation
        relations[alias] = relation
        return

    relation = catalog.manifest.get_relation(table.name)

    if relation is None:
        reasons.append(f"UNKNOWN_TABLE: {table.name}")
        return

    # Physical table name.
    relations[table_name] = relation

    # Explicit alias.
    relations[alias] = relation

    # Schema-qualified name.
    if table.db:
        qualified_name = f"{table.db}.{table.name}".lower()
        relations[qualified_name] = relation


def _register_source(
    relations: dict[str, object],
    source: exp.Expression,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> None:
    """Register one FROM/JOIN source in a SELECT scope."""
    if isinstance(source, exp.Table):
        _register_table(
            relations,
            source,
            catalog,
            cte_columns,
            reasons,
        )
        return

    if isinstance(source, exp.Subquery):
        alias = source.alias_or_name

        if alias:
            relations[alias.lower()] = _subquery_columns(source)


def _register_scope_relations(
    select: exp.Select,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> dict[str, object]:
    """Return relations visible directly in one SELECT scope."""
    relations: dict[str, object] = {}

    from_expression = select.args.get("from")

    if from_expression is not None:
        _register_source(
            relations,
            from_expression.this,
            catalog,
            cte_columns,
            reasons,
        )

    for join in select.args.get("joins", []):
        _register_source(
            relations,
            join.this,
            catalog,
            cte_columns,
            reasons,
        )

    return relations


def _column_belongs_to_select(
    column: exp.Column,
    select: exp.Select,
) -> bool:
    """Return whether a column belongs to this SELECT scope."""
    current = column.parent

    while current is not None:
        if current is select:
            return True

        # A nested SELECT owns its own column references.
        if isinstance(current, exp.Select):
            return False

        current = current.parent

    return False


def _resolve_column_scope(
    select: exp.Select,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> dict[str, object]:
    """Resolve relations visible directly in one SELECT scope."""
    return _register_scope_relations(
        select,
        catalog,
        cte_columns,
        reasons,
    )


def _select_output_aliases(select: exp.Select) -> set[str]:
    """Return output aliases defined in this SELECT's own expression list.

    Postgres allows ORDER BY and GROUP BY to reference an output alias
    rather than a physical column, so these names must not be treated
    as unresolved catalog columns.
    """
    aliases: set[str] = set()

    for expression in select.expressions:
        if isinstance(expression, exp.Alias):
            aliases.add(expression.alias.lower())

    return aliases


def _check_select(
    select: exp.Select,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> None:
    """Validate column references belonging to one SELECT scope."""
    relations = _resolve_column_scope(
        select,
        catalog,
        cte_columns,
        reasons,
    )
    output_aliases = _select_output_aliases(select)

    for column in select.find_all(exp.Column):
        if not _column_belongs_to_select(column, select):
            continue

        column_name = column.name.lower()

        # Qualified column:
        #
        #   o.order_id
        #   i.order_id
        #
        if column.table:
            table_reference = column.table.lower()
            relation = relations.get(table_reference)

            if relation is None:
                reasons.append(
                    f"UNKNOWN_TABLE: {column.table}",
                )
                continue

            if column_name not in _relation_columns(relation):
                reasons.append(
                    f"UNKNOWN_COLUMN: {column.table}.{column.name}",
                )

            continue

        # Unqualified column.
        if column_name in output_aliases:
            continue

        matches: list[object] = []
        for relation in relations.values():
            if column_name in _relation_columns(relation):
                matches.append(relation)

        unique_matches = list(
            {id(relation): relation for relation in matches}.values(),
        )

        if not unique_matches:
            reasons.append(
                f"UNKNOWN_COLUMN: {column.name}",
            )
        elif len(unique_matches) > 1:
            reasons.append(
                f"AMBIGUOUS_COLUMN: {column.name}",
            )


def _check_unknown_tables(
    expression: exp.Expression,
    catalog: Catalog,
    cte_columns: dict[str, set[str]],
    reasons: list[str],
) -> None:
    """Reject physical tables that do not exist in the catalog."""
    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()

        if table_name in cte_columns:
            continue

        if catalog.manifest.get_relation(table.name) is None:
            reason = f"UNKNOWN_TABLE: {table.name}"

            if reason not in reasons:
                reasons.append(reason)


def check_catalog(
    sql: str,
    catalog: Catalog,
) -> GuardResult:
    """Validate SQL identifiers against the catalog with SELECT scoping."""
    try:
        expression = sqlglot.parse_one(
            sql,
            read="postgres",
        )
    except sqlglot.errors.ParseError as exc:
        return GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    reasons: list[str] = []

    # Collect CTE definitions first so they can shadow physical tables.
    cte_columns: dict[str, set[str]] = {}

    for cte in expression.find_all(exp.CTE):
        cte_name = cte.alias_or_name.lower()
        cte_columns[cte_name] = _cte_columns(cte)

    # Check physical tables independently of column references.
    # This catches:
    #
    #   SELECT * FROM marts.fake_table
    #
    # because SELECT * does not produce an exp.Column for fake_table.
    _check_unknown_tables(
        expression,
        catalog,
        cte_columns,
        reasons,
    )

    selects = list(expression.find_all(exp.Select))

    for select in selects:
        _check_select(
            select,
            catalog,
            cte_columns,
            reasons,
        )

    return GuardResult(
        allowed=not reasons,
        reasons=sorted(set(reasons)),
    )
