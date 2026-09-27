"""Schema guards: the Postgres schema matches the dataclasses and money is NUMERIC.

Uses SQLAlchemy's inspector (not the ORM) to reflect the live schema. These are
the guards that keep the SQLite REAL/float mistake from reappearing.
"""

from sqlalchemy import Float, Numeric, inspect

EXPECTED_TABLES = {
    "invoice_headers",
    "invoice_lines",
    "po_headers",
    "po_lines",
    "grni_headers",
    "grni_lines",
    "pard",
}

# Exact names of the money / price / rate columns (all must be Numeric(18,4)).
# Exact names, not substrings: "tax" as a substring would false-positive on
# vendor_tax_id (a string column).
MONEY_COLUMNS = {
    "subtotal",
    "tax_amount",
    "total",
    "discount_amount",
    "tax_rate",
    "discount_rate",
    "unit_price",
    "amount",
}


def test_all_tables_exist(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"


def test_money_columns_are_numeric_18_4(pg_engine):
    insp = inspect(pg_engine)
    checked = 0
    for table in insp.get_table_names():
        for col in insp.get_columns(table):
            if col["name"] in MONEY_COLUMNS:
                t = col["type"]
                assert isinstance(t, Numeric), f"{table}.{col['name']} is {t}, not Numeric"
                assert (t.precision, t.scale) == (18, 4), f"{table}.{col['name']} is {t}, not Numeric(18,4)"
                checked += 1
    assert checked > 0, "no money columns found to check"


def test_no_float_or_real_columns(pg_engine):
    insp = inspect(pg_engine)
    for table in insp.get_table_names():
        for col in insp.get_columns(table):
            assert not isinstance(col["type"], Float), (
                f"{table}.{col['name']} is a float type: {col['type']}"
            )


def test_foreign_keys_present(pg_engine):
    insp = inspect(pg_engine)
    expected_fks = {
        ("invoice_lines", "invoice_headers"),
        ("po_lines", "po_headers"),
        ("grni_lines", "grni_headers"),
    }
    for child, parent in expected_fks:
        fks = insp.get_foreign_keys(child)
        assert any(fk["referred_table"] == parent for fk in fks), f"{child} has no FK to {parent}"


def test_primary_keys_match_document_numbers(pg_engine):
    insp = inspect(pg_engine)
    assert insp.get_pk_constraint("invoice_headers")["constrained_columns"] == ["invoice_number"]
    assert insp.get_pk_constraint("po_headers")["constrained_columns"] == ["po_number"]
    assert insp.get_pk_constraint("grni_headers")["constrained_columns"] == ["grn_number"]
    assert insp.get_pk_constraint("pard")["constrained_columns"] == ["pard_number"]
    assert insp.get_pk_constraint("invoice_lines")["constrained_columns"] == ["invoice_number", "line_no"]
    assert insp.get_pk_constraint("po_lines")["constrained_columns"] == ["po_number", "line_no"]
    assert insp.get_pk_constraint("grni_lines")["constrained_columns"] == ["grn_number", "line_no"]
