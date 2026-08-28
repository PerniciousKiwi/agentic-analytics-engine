from unittest.mock import MagicMock, patch

from cardinal.db.reader import WarehouseReader


def test_engine_is_created_lazily() -> None:
    reader = WarehouseReader()

    assert reader._engine is None


@patch("cardinal.db.reader.create_engine")
@patch("cardinal.db.reader.get_settings")
def test_engine_uses_read_only_dsn(
    mock_get_settings: MagicMock,
    mock_create_engine: MagicMock,
) -> None:
    mock_get_settings.return_value.postgres_ro_dsn = "postgresql+psycopg://test"

    reader = WarehouseReader()

    engine = reader.engine

    mock_create_engine.assert_called_once_with(
        "postgresql+psycopg://test",
    )
    assert engine is mock_create_engine.return_value


@patch("cardinal.db.reader.create_engine")
def test_fetch_all_returns_dictionaries(
    mock_create_engine: MagicMock,
) -> None:
    connection = mock_create_engine.return_value.connect.return_value.__enter__.return_value
    result = connection.execute.return_value
    result.mappings.return_value.all.return_value = [
        {"table_name": "fct_orders", "row_count": 100},
        {"table_name": "dim_customer", "row_count": 50},
    ]

    reader = WarehouseReader()
    rows = reader.fetch_all(
        "SELECT table_name, row_count FROM catalog",
    )

    assert rows == [
        {"table_name": "fct_orders", "row_count": 100},
        {"table_name": "dim_customer", "row_count": 50},
    ]

    connection.execute.assert_called_once()


@patch("cardinal.db.reader.create_engine")
def test_fetch_all_passes_parameters(
    mock_create_engine: MagicMock,
) -> None:
    connection = mock_create_engine.return_value.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.all.return_value = []

    reader = WarehouseReader()

    reader.fetch_all(
        "SELECT * FROM table WHERE id = :id",
        {"id": 123},
    )

    connection.execute.assert_called_once()
    _, params = connection.execute.call_args.args

    assert params == {"id": 123}


@patch("cardinal.db.reader.create_engine")
def test_fetch_scalar_returns_scalar(
    mock_create_engine: MagicMock,
) -> None:
    connection = mock_create_engine.return_value.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 99441

    reader = WarehouseReader()

    result = reader.fetch_scalar(
        "SELECT COUNT(*) FROM fct_orders",
    )

    assert result == 99441
    connection.execute.assert_called_once()


def test_dispose_without_engine_is_safe() -> None:
    reader = WarehouseReader()

    reader.dispose()

    assert reader._engine is None


@patch("cardinal.db.reader.create_engine")
def test_dispose_releases_engine(
    mock_create_engine: MagicMock,
) -> None:
    reader = WarehouseReader()

    engine = reader.engine

    reader.dispose()

    engine.dispose.assert_called_once()
    assert reader._engine is None


@patch("cardinal.db.reader.create_engine")
def test_context_manager_disposes_engine(
    mock_create_engine: MagicMock,
) -> None:
    with WarehouseReader() as reader:
        engine = reader.engine

    engine.dispose.assert_called_once()
    assert reader._engine is None
