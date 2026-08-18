"""Tests for datasure.checks.outliers.models."""

import pytest
from pydantic import ValidationError

from datasure.checks.outliers.models import (
    ConstraintBounds,
    ConstraintMetrics,
    OutlierBounds,
    OutlierColumnConfig,
    OutlierMethod,
    OutlierMetrics,
    OutlierOptionsConfig,
    OutlierSettings,
    OutlierStatistics,
    SearchType,
)

# ============================================================================
# PYDANTIC MODEL TESTS
# ============================================================================


class TestOutlierBounds:
    """Test OutlierBounds Pydantic model."""

    def test_valid_bounds(self):
        """Test creating valid outlier bounds."""
        bounds = OutlierBounds(lower_bound=0.0, upper_bound=100.0)
        assert bounds.lower_bound == 0.0
        assert bounds.upper_bound == 100.0

    def test_negative_bounds(self):
        """Test bounds with negative values."""
        bounds = OutlierBounds(lower_bound=-50.0, upper_bound=50.0)
        assert bounds.lower_bound == -50.0
        assert bounds.upper_bound == 50.0


class TestOutlierOptionsConfig:
    """Test OutlierOptionsConfig Pydantic model."""

    def test_valid_config(self):
        """Test creating valid outlier options config."""
        config = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        assert config.outlier_method == OutlierMethod.IQR
        assert config.outlier_multiplier == 1.5
        assert config.outlier_threshold == 20

    def test_invalid_multiplier_zero(self):
        """Test that zero multiplier raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )

    def test_invalid_multiplier_negative(self):
        """Test that negative multiplier raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=-1.5,
                outlier_threshold=20,
            )

    def test_invalid_threshold_zero(self):
        """Test that zero threshold raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
                outlier_threshold=0,
            )


class TestConstraintBounds:
    """Test ConstraintBounds Pydantic model."""

    def test_valid_bounds_all_fields(self):
        """Test creating valid constraint bounds with all fields."""
        bounds = ConstraintBounds(
            hard_min=0.0, soft_min=10.0, soft_max=90.0, hard_max=100.0
        )
        assert bounds.hard_min == 0.0
        assert bounds.soft_min == 10.0
        assert bounds.soft_max == 90.0
        assert bounds.hard_max == 100.0

    def test_valid_bounds_partial(self):
        """Test creating valid constraint bounds with partial fields."""
        bounds = ConstraintBounds(soft_min=10.0, soft_max=90.0)
        assert bounds.hard_min is None
        assert bounds.soft_min == 10.0
        assert bounds.soft_max == 90.0
        assert bounds.hard_max is None

    def test_invalid_bounds_hierarchy(self):
        """Test that invalid hierarchy raises validation error."""
        with pytest.raises(ValidationError, match="Bounds must follow hierarchy"):
            ConstraintBounds(
                hard_min=50.0,
                soft_min=10.0,  # hard_min > soft_min
            )

    def test_invalid_soft_bounds(self):
        """Test that soft_min > soft_max raises validation error."""
        with pytest.raises(ValidationError):
            ConstraintBounds(soft_min=90.0, soft_max=10.0)

    def test_negative_bounds(self):
        """Test constraint bounds with negative values."""
        bounds = ConstraintBounds(
            hard_min=-100.0, soft_min=-50.0, soft_max=50.0, hard_max=100.0
        )
        assert bounds.hard_min == -100.0


class TestConstraintMetrics:
    """Test ConstraintMetrics Pydantic model."""

    def test_valid_metrics(self):
        """Test creating valid constraint metrics."""
        metrics = ConstraintMetrics(
            columns_checked=5,
            total_violations=10,
            hard_min_violations=2,
            soft_min_violations=3,
            soft_max_violations=3,
            hard_max_violations=2,
        )
        assert metrics.total_violations == 10

    def test_negative_values_invalid(self):
        """Test that negative values raise validation error."""
        with pytest.raises(ValidationError):
            ConstraintMetrics(
                columns_checked=-1,
                total_violations=0,
                hard_min_violations=0,
                soft_min_violations=0,
                soft_max_violations=0,
                hard_max_violations=0,
            )


class TestOutlierMetrics:
    """Test OutlierMetrics Pydantic model."""

    def test_valid_metrics(self):
        """Test creating valid outlier metrics."""
        metrics = OutlierMetrics(
            columns_checked=5,
            columns_with_outliers=3,
            total_outliers=10,
            enumerators_with_outliers=2,
        )
        assert metrics.columns_checked == 5
        assert metrics.total_outliers == 10


class TestOutlierStatistics:
    """Test OutlierStatistics Pydantic model."""

    def test_valid_statistics(self):
        """Test creating valid outlier statistics."""
        stats = OutlierStatistics(
            count=100,
            min_value=0.0,
            max_value=100.0,
            mean=50.0,
            median=48.0,
            sd=15.0,
            iqr=25.0,
            lower_bound=10.0,
            upper_bound=90.0,
        )
        assert stats.count == 100
        assert stats.mean == 50.0
        assert stats.sd == 15.0

    def test_alias_std(self):
        """Test that 'sd' alias works for std field."""
        stats = OutlierStatistics(
            count=100,
            min_value=0.0,
            max_value=100.0,
            mean=50.0,
            median=48.0,
            sd=15.0,  # Using alias
            iqr=25.0,
            lower_bound=10.0,
            upper_bound=90.0,
        )
        assert stats.sd == 15.0


class TestOutlierColumnConfig:
    """Test OutlierColumnConfig Pydantic model."""

    def test_valid_config_exact(self):
        """Test creating valid config with exact search."""
        config = OutlierColumnConfig(
            search_type=SearchType.EXACT,
            pattern=None,
            outlier_cols=["col1", "col2"],
            lock_cols=False,
            grouped_cols=False,
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
        )
        assert config.search_type == SearchType.EXACT

    def test_invalid_pattern_required(self):
        """Test that pattern is required for non-exact search types."""
        with pytest.raises(ValidationError):
            OutlierColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern=None,  # Should be required
                outlier_cols=["col1"],
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
            )

    def test_invalid_soft_bounds(self):
        """Test that soft_max must be greater than soft_min."""
        with pytest.raises(ValidationError):
            OutlierColumnConfig(
                search_type=SearchType.EXACT,
                outlier_cols=["col1"],
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
                soft_min=50.0,
                soft_max=10.0,  # Less than soft_min
            )


class TestOutlierSettings:
    """Test OutlierSettings Pydantic model."""

    def test_valid_settings(self):
        """Test creating valid outlier settings."""
        settings = OutlierSettings(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team",
        )
        assert settings.survey_key == "key"

    def test_minimal_settings(self):
        """Test creating minimal valid settings."""
        settings = OutlierSettings(survey_key="key")
        assert settings.survey_key == "key"
        assert settings.survey_id is None


# ============================================================================
# Additional Model Validation Edge Case Tests
# ============================================================================


class TestConstraintValidation:
    """Test constraint bounds validation."""

    def test_constraint_bounds_all_none(self):
        """Test ConstraintBounds with all None values."""
        bounds = ConstraintBounds()
        assert bounds.hard_min is None
        assert bounds.soft_min is None
        assert bounds.soft_max is None
        assert bounds.hard_max is None

    def test_constraint_bounds_partial(self):
        """Test ConstraintBounds with partial values."""
        bounds = ConstraintBounds(soft_min=10, soft_max=100)
        assert bounds.soft_min == 10
        assert bounds.soft_max == 100
        assert bounds.hard_min is None
        assert bounds.hard_max is None

    def test_constraint_bounds_invalid_order(self):
        """Test ConstraintBounds with invalid hierarchy."""
        with pytest.raises(ValidationError, match="must be <="):
            ConstraintBounds(hard_min=100, soft_min=50)

    def test_constraint_bounds_negative_values(self):
        """Test ConstraintBounds with negative values."""
        bounds = ConstraintBounds(
            hard_min=-100, soft_min=-50, soft_max=50, hard_max=100
        )
        assert bounds.hard_min == -100
        assert bounds.soft_min == -50


class TestOutlierColumnConfigValidation:
    """Test OutlierColumnConfig validation edge cases."""

    def test_pattern_required_for_non_exact(self):
        """Test that pattern is required for non-exact search types."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            OutlierColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern=None,
                outlier_cols=["col1"],
                outlier_multiplier=1.5,
            )

    def test_soft_max_validation(self):
        """Test soft_max must be greater than soft_min."""
        with pytest.raises(ValidationError, match="soft_max must be greater"):
            OutlierColumnConfig(
                search_type=SearchType.EXACT,
                outlier_cols=["col1"],
                outlier_multiplier=1.5,
                soft_min=100,
                soft_max=50,
            )

    def test_valid_config_with_constraints(self):
        """Test valid configuration with all constraints."""
        config = OutlierColumnConfig(
            search_type=SearchType.EXACT,
            outlier_cols=["col1"],
            outlier_multiplier=1.5,
            soft_min=10,
            soft_max=100,
        )
        assert config.soft_min == 10
        assert config.soft_max == 100
