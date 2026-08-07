from __future__ import annotations

import numpy as np
import polars as pl
import pydeck
import streamlit as st
from geopy.distance import geodesic
from sklearn.neighbors import LocalOutlierFactor

from datasure.checks.gpschecks.models import _CATEGORY_COLORS, TAB_NAME
from datasure.models.enums import DelimiterType, GPSFormatType
from datasure.models.schemas import GPSSettings
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.settings_utils import load_check_settings


def _get_mapbox_key() -> str | None:
    """Resolve Mapbox API key from pydeck settings or Streamlit secrets.

    Returns
    -------
    str | None
        Mapbox API key if found, None otherwise.
    """
    mapbox_key = pydeck.settings.mapbox_key
    if mapbox_key:
        return mapbox_key
    if "mapbox_custom_key" in st.secrets:
        return st.secrets["mapbox_custom_key"]
    if "default_mapbox_api_key" in st.secrets:
        return st.secrets["default_mapbox_api_key"]
    return None


def _build_tooltip_config(fields: list[str]) -> dict:
    """Build pydeck tooltip configuration from a list of field names.

    Parameters
    ----------
    fields : list[str]
        Field names to include in the tooltip.

    Returns
    -------
    dict
        Tooltip configuration for pydeck.
    """
    return {
        "html": "<br>".join([f"<b>{field}:</b> {{{field}}}" for field in fields]),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }


@st.cache_data(ttl=60)
def load_default_gpschecks_settings(
    settings_file: str, config: GPSSettings
) -> GPSSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved gps report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : DuplicatesSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    DuplicatesSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return GPSSettings(**default_settings)


def _get_gps_column_settings(project_id: str, page_name_id: str) -> pl.DataFrame:
    """Load the saved GPS column configuration table for a project/page.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.

    Returns
    -------
    pl.DataFrame
        Saved GPS column configurations (empty if none exist).
    """
    return duckdb_get_table(
        project_id,
        f"gps_columns_{page_name_id}",
        "logs",
    )


def _save_gps_column_settings(
    project_id: str, page_name_id: str, settings: pl.DataFrame
) -> None:
    """Persist the GPS column configuration table for a project/page.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    settings : pl.DataFrame
        GPS column configurations to save.
    """
    duckdb_save_table(
        project_id,
        settings,
        f"gps_columns_{page_name_id}",
        "logs",
    )


def _parse_gps_data(
    data: pl.DataFrame,
    gps_config: dict,
) -> pl.DataFrame:
    """Parse GPS data based on configuration.

    Extracts latitude and longitude from either single column (delimited)
    or separate columns format.

    Parameters
    ----------
    data : pl.DataFrame
        Input dataframe containing GPS data.
    gps_config : dict
        GPS configuration dictionary with format_type, delimiter, and columns.

    Returns
    -------
    pl.DataFrame
        DataFrame with added 'latitude' and 'longitude' columns.
    """
    result_df = data.clone()

    if gps_config["format_type"] == GPSFormatType.SINGLE_COLUMN.value:
        # Single column format - split by delimiter
        gps_col = gps_config["gps_column"]
        delimiter = gps_config["delimiter"]

        separator = " " if delimiter == DelimiterType.SPACE.value else ","

        # Check if column exists
        if gps_col not in result_df.columns:
            # Return empty lat/lon columns if GPS column doesn't exist
            result_df = result_df.with_columns(
                [
                    pl.lit(None).cast(pl.Float64).alias("latitude"),
                    pl.lit(None).cast(pl.Float64).alias("longitude"),
                ]
            )
        else:
            # Convert to string first (in case column is numeric or other type)
            # Then split GPS column and extract lat/lon
            result_df = result_df.with_columns(
                [
                    pl.col(gps_col)
                    .cast(pl.Utf8, strict=False)
                    .str.split(separator)
                    .list.get(0)
                    .cast(pl.Float64, strict=False)
                    .alias("latitude"),
                    pl.col(gps_col)
                    .cast(pl.Utf8, strict=False)
                    .str.split(separator)
                    .list.get(1)
                    .cast(pl.Float64, strict=False)
                    .alias("longitude"),
                ]
            )
    else:
        # Separate columns format
        lat_col = gps_config["latitude_column"]
        lon_col = gps_config["longitude_column"]

        # Check if columns exist
        if lat_col not in result_df.columns or lon_col not in result_df.columns:
            # Return empty lat/lon columns if either column doesn't exist
            result_df = result_df.with_columns(
                [
                    pl.lit(None).cast(pl.Float64).alias("latitude"),
                    pl.lit(None).cast(pl.Float64).alias("longitude"),
                ]
            )
        else:
            result_df = result_df.with_columns(
                [
                    pl.col(lat_col).cast(pl.Float64, strict=False).alias("latitude"),
                    pl.col(lon_col).cast(pl.Float64, strict=False).alias("longitude"),
                ]
            )

    return result_df


def _collect_optional_fields(
    df, field_pairs: list[tuple[str | None, str]]
) -> list[str]:
    """Collect field names that are non-None and present in the dataframe.

    Parameters
    ----------
    df : pd.DataFrame or pl.DataFrame
        DataFrame to check column presence against.
    field_pairs : list[tuple[str | None, str]]
        Pairs of (column_name, tooltip_label). If column_name is truthy and
        present in df.columns, tooltip_label is included in the result.

    Returns
    -------
    list[str]
        List of tooltip field names.
    """
    fields: list[str] = []
    for col, label in field_pairs:
        if col and col in df.columns:
            fields.append(label)
    return fields


def _identity_optional_fields(df, columns: list[str | None]) -> list[str]:
    """Collect present columns from df, using each column name as its own label.

    Equivalent to calling `_collect_optional_fields` with (name, name) pairs,
    which is the common case for tooltip/display field lists keyed by survey
    identifiers (survey key/id, date, enumerator, etc.).

    Parameters
    ----------
    df : pd.DataFrame or pl.DataFrame
        DataFrame to check column presence against.
    columns : list[str | None]
        Column names to include if truthy and present in df.columns.

    Returns
    -------
    list[str]
        List of column names present in df.
    """
    return _collect_optional_fields(df, [(col, col) for col in columns])


def _build_map_dataframe(
    data: pl.DataFrame,
    survey_key: str | None,
    survey_date: str | None,
    enumerator: str | None,
    team: str | None,
    color_by: str | None,
) -> tuple[object, list[str]]:
    """Build a pandas DataFrame and tooltip fields for pydeck visualization.

    Parameters
    ----------
    data : pl.DataFrame
        Filtered data with latitude and longitude columns.
    survey_key : str | None
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    enumerator : str | None
        Enumerator column name.
    team : str | None
        Team column name.
    color_by : str | None
        Column name to color points by.

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        Pandas DataFrame for pydeck and list of tooltip field names.
    """
    map_df = data.select(
        pl.col("latitude").alias("lat"),
        pl.col("longitude").alias("lon"),
    )

    # Map source column -> tooltip alias for hover labels
    column_aliases = [
        (survey_key, "ID"),
        (survey_date, "Date"),
        (enumerator, "Enumerator"),
        (team, "Team"),
    ]

    tooltip_fields: list[str] = []
    for col, alias in column_aliases:
        if col:
            map_df = map_df.with_columns(data[col].alias(alias))
            tooltip_fields.append(alias)

    tooltip_fields.extend(["lat", "lon"])

    if color_by:
        map_df = map_df.with_columns(data[color_by].alias("color_group"))
        tooltip_fields.append(color_by)

    map_pd = map_df.to_pandas()

    if color_by:
        unique_vals = map_pd["color_group"].unique()
        color_map = {
            val: _CATEGORY_COLORS[i % len(_CATEGORY_COLORS)]
            for i, val in enumerate(unique_vals)
        }
        map_pd["color"] = map_pd["color_group"].map(color_map)

    return map_pd, tooltip_fields


def _has_parsed_coords(parsed_data: pl.DataFrame) -> bool:
    """Check whether a parsed GPS DataFrame contains latitude and longitude columns."""
    return "latitude" in parsed_data.columns and "longitude" in parsed_data.columns


# detect outliers using a clustering column
@st.cache_data
def detect_outliers_with_clusters(df, gps_lat_col, gps_lon_col, clustering_col):
    """
    Detect outliers using clustering and visualize them on a map.

    Parameters
    ----------
    df : pd.DataFrame
        The input dataframe containing GPS data.
    gps_lat_col : str
        The name of the latitude column.
    gps_lon_col : str
        The name of the longitude column.
    clustering_col : str
        The name of the column to group data for clustering.

    Returns
    -------
    pd.DataFrame
        The input dataframe with an additional column indicating outliers.
    """
    outlier_df = df.copy(deep=True)
    if not clustering_col:
        # If no clustering column is provided, treat the entire DataFrame
        # as a single group
        # create a dummy clustering column
        outlier_df["dummy_cluster"] = "all"
        clustering_col = "dummy_cluster"

    # replace missing values in clustering column with a placeholder
    outlier_df[clustering_col] = outlier_df[clustering_col].fillna("Unknown")

    # Drop rows with missing latitude values or longitude values
    outlier_df = outlier_df.dropna(subset=[gps_lat_col, gps_lon_col])

    grouped_df = outlier_df.groupby(clustering_col)

    # Calculate centroids for each group
    centroids = grouped_df[[gps_lat_col, gps_lon_col]].mean()

    # Calculate distances from centroids using geopy
    def calculate_distance(row):
        centroid = centroids.loc[row[clustering_col]]
        return geodesic(
            (row[gps_lat_col], row[gps_lon_col]),
            (centroid[gps_lat_col], centroid[gps_lon_col]),
        ).meters

    outlier_df["distance_from_centroid"] = outlier_df.apply(calculate_distance, axis=1)

    # Flag outliers using IQR for each group
    def flag_outliers(group):
        # Skip outlier detection for groups with too few points
        if len(group) < 4:
            group["Outlier"] = False
            return group

        Q1 = group["distance_from_centroid"].quantile(0.25)
        Q3 = group["distance_from_centroid"].quantile(0.75)
        IQR = Q3 - Q1

        # If IQR is 0 (all points at same distance), mark none as outliers
        if IQR == 0:
            group["Outlier"] = False
            return group

        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        group["Outlier"] = (group["distance_from_centroid"] < lower_bound) | (
            group["distance_from_centroid"] > upper_bound
        )
        return group

    outlier_df = grouped_df.apply(flag_outliers, include_groups=False).reset_index(
        drop=True
    )

    return outlier_df


# automatically detect outliers using Local Outlier Factor (LOF)
@st.cache_data
def detect_outliers_with_lof(df, gps_lat_col, gps_lon_col, n_neighbors, contamination):
    """
    Automatically detect GPS outliers using Local Outlier Factor (LOF).

    Parameters
    ----------
    df : pd.DataFrame
        The input dataframe containing GPS data.
    gps_lat_col : str
        The name of the latitude column.
    gps_lon_col : str
        The name of the longitude column.
    n_neighbors : int
        Number of neighbors to use for LOF.
    contamination : float
        The proportion of outliers in the data.

    Returns
    -------
    pd.DataFrame
        The input dataframe with an additional 'Outlier' column indicating GPS outliers.
    """
    # Drop rows with missing latitude or longitude values
    df = df.dropna(subset=[gps_lat_col, gps_lon_col])

    # Check if we have enough samples for LOF
    n_samples = len(df)
    if n_samples < 2:
        # Not enough data for outlier detection
        df["Outlier"] = False
        return df

    # Adjust n_neighbors if necessary
    # LOF requires n_neighbors < n_samples
    adjusted_n_neighbors = min(n_neighbors, n_samples - 1)

    # Convert coordinates to a numpy array
    coords = df[[gps_lat_col, gps_lon_col]].values

    # Apply Local Outlier Factor
    lof = LocalOutlierFactor(
        n_neighbors=adjusted_n_neighbors, contamination=contamination
    )
    df["Outlier"] = lof.fit_predict(coords) == -1  # LOF assigns -1 to outliers

    return df


# calculate gps accuracy statistics
@st.cache_data
def calculate_gps_accuracy_statistics(
    df, gps_accuracy, accuracy_cluster_col, accuracy_stats_list
):
    """
    Calculate GPS accuracy statistics grouped by a specified column.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe containing GPS data.
    gps_accuracy : str
        The name of the GPS accuracy column.
    accuracy_cluster_col : str
        The name of the column to group data for calculating statistics.
    accuracy_stats_list : list
        List of statistics to calculate (e.g., ['min', 'median', 'mean', 'max', 'std']).

    Returns
    -------
    pd.DataFrame
        A dataframe containing grouped GPS accuracy statistics.
    """
    allowed_stats = [
        "min",
        "median",
        "mean",
        "max",
        "std",
        "25th percentile",
        "75th percentile",
        "95th percentile",
    ]
    # Validate the accuracy_stats_list
    accuracy_stats_list = [
        stat for stat in accuracy_stats_list if stat in allowed_stats
    ]
    # update percentile statistics with numpy percentile function
    percentile_map = {
        "25th percentile": lambda x: np.percentile(x, 25),
        "75th percentile": lambda x: np.percentile(x, 75),
        "95th percentile": lambda x: np.percentile(x, 95),
    }

    accuracy_stats_list = [
        percentile_map.get(stat, stat) for stat in accuracy_stats_list
    ]

    # Group GPS accuracy statistics by the selected column
    gps_accuracy_stats = df.groupby(accuracy_cluster_col)[gps_accuracy].agg(
        accuracy_stats_list
    )
    # Rename lambda_* columns back to their correct percentile names if present
    for col in gps_accuracy_stats.columns:
        if "lambda" in col:
            for percentile_name, func in percentile_map.items():
                if gps_accuracy_stats[col].equals(
                    df.groupby(accuracy_cluster_col)[gps_accuracy].agg(func)
                ):
                    gps_accuracy_stats = gps_accuracy_stats.rename(
                        columns={col: percentile_name}
                    )
                    break

    return gps_accuracy_stats
