from decimal import Decimal

import apmatch.matching.config as config

# Public Decimal tolerance/fuzzy constants defined in the module.
_DECIMAL_CONSTANTS = [
    "QTY_TOLERANCE_ABS",
    "UNIT_PRICE_TOLERANCE",
    "AMOUNT_TOLERANCE",
    "TOTAL_TOLERANCE",
    "UNIT_PRICE_TOLERANCE_REL",
    "AMOUNT_TOLERANCE_REL",
    "VENDOR_NAME_FUZZY_MIN",
]

# Names imported into the module (not constants defined here).
_IMPORTED = {"Decimal", "MatchCode"}


def test_all_tolerances_are_decimal():
    for name in _DECIMAL_CONSTANTS:
        value = getattr(config, name)
        assert isinstance(value, Decimal), f"{name} is {type(value).__name__}, not Decimal"


def test_all_exports_are_listed_in_dunder_all():
    for name in dir(config):
        if name.startswith("_") or name in _IMPORTED:
            continue
        assert name in config.__all__, f"public name {name!r} missing from __all__"


def test_matchable_fields_is_tuple_of_str():
    assert isinstance(config.MATCHABLE_FIELDS, tuple)
    assert all(isinstance(f, str) for f in config.MATCHABLE_FIELDS)
