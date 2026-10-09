import pytest
from sqlalchemy import Column, Integer, Table

from app.models import Base
from app.repositories.account_repository import owned_tables


def test_every_app_table_is_in_export_and_delete():
    covered = {t.name for t, _ in owned_tables()}
    expected = {t.name for t in Base.metadata.sorted_tables if t.schema != "auth"}
    assert covered == expected


def test_owner_column_exists_on_every_covered_table():
    for table, owner in owned_tables():
        assert owner in table.c, table.name


def test_delete_order_is_children_before_parents():
    delete_order = [t.name for t, _ in reversed(owned_tables())]
    assert delete_order.index("habit_logs") < delete_order.index("habit_definitions")


def test_a_table_with_no_owner_column_trips_the_wire():
    rogue = Table("rogue_tmp", Base.metadata, Column("id", Integer, primary_key=True))
    try:
        with pytest.raises(RuntimeError, match="rogue_tmp"):
            owned_tables()
    finally:
        Base.metadata.remove(rogue)
