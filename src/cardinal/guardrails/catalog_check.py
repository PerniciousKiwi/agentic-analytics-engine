from __future__ import annotations

import sqlglot
from sqlglot import exp

from cardinal.catalog.catalog import Catalog
from cardinal.guardrails.ast_checks import GuardResult


def _cte_columns(cte: exp.CTE) -> set[str]:
    """Return columns exposed by a CTE."""
    query = cte.this

    columns: set[str] = set()

    for projection in query.find_all(exp.Select):
        for expression in projection.expressions:
            alias = expression.alias
            if alias:
                columns.add(alias.lower())
            elif isinstance(expression, exp.Column):
                columns.add(expression.name.lower())

    return columns


def check_catalog(sql: str, catalog: Catalog) -> GuardResult:
    try:
        expression = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        return GuardResult(
            allowed=False,
            reasons=[f"SQL_PARSE_ERROR: {exc}"],
        )

    reasons: list[str] = []
    relations: dict[str, object] = {}

    # CTE names shadow physical tables with the same name.
    cte_columns: dict[str, set[str]] = {}

    for cte in expression.find_all(exp.CTE):
        cte_name = cte.alias_or_name.lower()
        cte_columns[cte_name] = _cte_columns(cte)

    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()

        # A CTE shadows a physical table with the same name.
        if table_name in cte_columns:
            relations[table.alias_or_name.lower()] = cte_columns[table_name]
            relations[table_name] = cte_columns[table_name]
            continue

        relation = catalog.manifest.get_relation(table.name)

        if relation is None:
            reasons.append(f"UNKNOWN_TABLE: {table.name}")
            continue

        # Make the relation available through:
        #   - explicit alias
        #   - table name
        #   - schema-qualified table name
        relations[table.alias_or_name.lower()] = relation
        relations[table.name.lower()] = relation

        if table.db:
            qualified_name = f"{table.db}.{table.name}".lower()
            relations[qualified_name] = relation

    if not relations:
        return GuardResult(
            allowed=not reasons,
            reasons=sorted(set(reasons)),
        )

    for column in expression.find_all(exp.Column):
        column_name = column.name.lower()

        if column.table:
            table_reference = column.table.lower()
            relation = relations.get(table_reference)

            if relation is None:
                reasons.append(
                    f"UNKNOWN_TABLE: {column.table}",
                )
                continue

            if isinstance(relation, set):
                column_names = relation
            else:
                column_names = {name.lower() for name in relation.columns}

            if column_name not in column_names:
                reasons.append(
                    f"UNKNOWN_COLUMN: {column.table}.{column.name}",
                )

            continue

        matches = []

        for relation in relations.values():
            if isinstance(relation, set):
                column_names = relation
            else:
                column_names = {name.lower() for name in relation.columns}

            if column_name in column_names:
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

    return GuardResult(
        allowed=not reasons,
        reasons=sorted(set(reasons)),
    )
