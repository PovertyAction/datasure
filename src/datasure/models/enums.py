"""Enums and Constants for Datasure.

This module defines various enums and constants used throughout the Datasure codebase
"""

from enum import Enum

# === ENUMS === #


class PrepActions(Enum):
    """Data model for preparation actions."""

    add_column: str = "add new column"
    transform_column: str = "transform column(s)"
    remove_column: str = "remove column(s)"
    remove_row: str = "remove row(s)"


class PrepMethods(Enum):
    """Data model for preparation methods."""

    row_index: str = "by row index"
    condition: str = "by condition"


class PrepFunctions(Enum):
    """Data model for preparation functions."""

    sum: str = "sum"
    diff: str = "diff"
    mean: str = "mean"
    median: str = "median"
    mode: str = "mode"
    min: str = "min"
    max: str = "max"
    std: str = "std"
    var: str = "var"
    first: str = "first"
    last: str = "last"
    count: str = "count"
    nunique: str = "nunique"
    product: str = "product"
    quotient: str = "quotient"
    index: str = "index"
    uuid: str = "uuid"
    random: str = "random"
    constant: str = "constant"


class PrepOperations(Enum):
    """Operations for Prep."""

    day_of_month: str = "day of month"
    day_of_week: str = "day of week"
    day_of_year: str = "day of year"
    date: str = "date"
    week_of_year: str = "week of year"
    month_of_year: str = "month of year"
    year: str = "year"
    quarter_of_year: str = "quarter of year"
    hour: str = "hour"
    minute: str = "minute"
    second: str = "second"
    floor: str = "floor"
    ceil: str = "ceil"
    round: str = "round"
    abs: str = "absolute value"
    trim: str = "trim"
    substring: str = "substring"
    replace: str = "replace"
    strip: str = "strip"
    lower: str = "lowercase"
    upper: str = "uppercase"
    string_to_number: str = "string to number"
    string_to_date: str = "string to date"
    string_to_datetime: str = "string to datetime"
    extract_pattern: str = "extract pattern"
    get_dummies: str = "get dummies"
    add: str = "add"
    subtract: str = "subtract"
    multiply: str = "multiply"
    divide: str = "divide"


class PrepRowConditions(Enum):
    """Data model for preparation conditions."""

    missing: str = "value is missing"
    not_missing: str = "value is not missing"
    equal_to: str = "value is equal to"
    not_equal_to: str = "value is not equal to"
    greater_than: str = "value is greater than"
    less_than: str = "value is less than"
    greater_than_or_equal_to: str = "value is greater than or equal to"
    less_than_or_equal_to: str = "value is less than or equal to"
    between: str = "value is between"
    not_between: str = "value is not between"
    like: str = "value is like"
    not_like: str = "value is not like"


class SearchType(Enum):
    """Column search pattern types for duplicate detection."""

    EXACT = "exact"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    CONTAINS = "contains"
    REGEX = "regex"


class NumCondition(Enum):
    """Condition types for duplicate checks on numeric columns."""

    EQUALS = "Value is equal"
    NOT_EQUALS = "Value is not equal"
    GREATER_THAN = "Value is greater than"
    GREATER_THAN_OR_EQUAL = "Value is greater than or equal to"
    LESS_THAN = "Value is less than"
    LESS_THAN_OR_EQUAL = "Value is less than or equal to"
    INCLUDES = "Values includes"
    EXCLUDES = "Value does not include"
    IN_RANGE = "Value is in range"


class StrCondition(Enum):
    """Condition types for duplicate checks on string columns."""

    EQUALS = "Value is equal"
    NOT_EQUALS = "Value is not equal"
    STARTWITH = "Value starts with"
    ENDWITH = "Value ends with"
    CONTAINS = "Value contains"
    INCLUDES = "Values includes"
    EXCLUDES = "Value does not include"


# === COLUMN FUNCTION CONSTANTS === #

COL_FUNC_WITH_VALUES = (
    PrepFunctions.sum.value,
    PrepFunctions.diff.value,
    PrepFunctions.mean.value,
    PrepFunctions.median.value,
    PrepFunctions.mode.value,
    PrepFunctions.min.value,
    PrepFunctions.max.value,
    PrepFunctions.std.value,
    PrepFunctions.var.value,
    PrepFunctions.first.value,
    PrepFunctions.last.value,
    PrepFunctions.count.value,
    PrepFunctions.nunique.value,
    PrepFunctions.product.value,
    PrepFunctions.quotient.value,
)


COL_METHODS_WITHOUT_VALUES = (
    PrepFunctions.index.value,
    PrepFunctions.uuid.value,
    PrepFunctions.random.value,
)

# === ROW CONDITION CONSTANTS === #

# Conditions allowing max 1 column
DEL_ROW_COND_MAX_1 = (
    PrepRowConditions.equal_to.value,
    PrepRowConditions.not_equal_to.value,
    PrepRowConditions.greater_than.value,
    PrepRowConditions.less_than.value,
    PrepRowConditions.greater_than_or_equal_to.value,
    PrepRowConditions.less_than_or_equal_to.value,
)

# Numeric-only conditions
DEL_ROW_COND_NUM_ONLY = (
    PrepRowConditions.greater_than.value,
    PrepRowConditions.less_than.value,
    PrepRowConditions.greater_than_or_equal_to.value,
    PrepRowConditions.less_than_or_equal_to.value,
    PrepRowConditions.between.value,
    PrepRowConditions.not_between.value,
)

# String-only conditions
DEL_ROW_COND_STR_ONLY = (
    PrepRowConditions.like.value,
    PrepRowConditions.not_like.value,
)


# Conditions requiring value input
DEL_COND_USE_VALS = (
    PrepRowConditions.equal_to.value,
    PrepRowConditions.not_equal_to.value,
    PrepRowConditions.greater_than.value,
    PrepRowConditions.less_than.value,
    PrepRowConditions.greater_than_or_equal_to.value,
    PrepRowConditions.less_than_or_equal_to.value,
)

# Conditions requiring same-type columns
DEL_ROW_COND_SAME_TYPE = (
    PrepRowConditions.between.value,
    PrepRowConditions.not_between.value,
)
