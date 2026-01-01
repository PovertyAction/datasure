from enum import Enum

import matplotlib as mpl
import numpy as np
import polars as pl
import pydeck as pdk
import streamlit as st
from geopy.distance import geodesic
from pydantic import BaseModel, Field, ValidationError, field_validator
from sklearn.neighbors import LocalOutlierFactor

from datasure.utils import (
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.onboarding_utils import demo_output_onboarding

TAB_NAME: str = "gpschecks"


# =============================================================================
# Enums and Constants
# =============================================================================


class GPSFormatType(str, Enum):
    """GPS data format types."""

    SINGLE_COLUMN = "Single Column (delimited)"
    SEPARATE_COLUMNS = "Separate Columns"


class DelimiterType(str, Enum):
    """Delimiter types for single column GPS data."""

    SPACE = "Space"
    COMMA = "Comma"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class GPSSettings(BaseModel):
    """GPS check settings model."""

    survey_key: str | None = Field(..., description="Survey key column")
    survey_id: str | None = Field(None, min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    team: str | None = Field(None, description="Team identifier column")


class GPSColumnConfig(BaseModel):
    """Configuration for GPS column setup."""

    format_type: GPSFormatType = Field(..., description="GPS data format type")
    delimiter: DelimiterType | None = Field(
        None, description="Delimiter for single column GPS data"
    )
    gps_column: str | None = Field(
        None, description="Column containing delimited GPS data"
    )
    latitude_column: str | None = Field(None, description="Latitude column name")
    longitude_column: str | None = Field(None, description="Longitude column name")
    altitude_column: str | None = Field(None, description="Altitude column name")
    accuracy_column: str | None = Field(None, description="Accuracy column name")

    @field_validator("delimiter")
    @classmethod
    def validate_delimiter(cls, v: DelimiterType | None, info) -> DelimiterType | None:
        """Validate delimiter is required for single column format."""
        if info.data.get("format_type") == GPSFormatType.SINGLE_COLUMN and not v:
            raise ValueError("Delimiter is required for single column format")
        return v

    @field_validator("gps_column")
    @classmethod
    def validate_gps_column(cls, v: str | None, info) -> str | None:
        """Validate gps_column is required for single column format."""
        if info.data.get("format_type") == GPSFormatType.SINGLE_COLUMN and not v:
            raise ValueError("GPS column is required for single column format")
        return v

    @field_validator("latitude_column", "longitude_column")
    @classmethod
    def validate_lat_lon_columns(cls, v: str | None, info) -> str | None:
        """Validate latitude and longitude are required for separate columns format."""
        field_name = info.field_name
        format_type = info.data.get("format_type")

        if format_type == GPSFormatType.SEPARATE_COLUMNS and not v:
            raise ValueError(
                f"{field_name.replace('_', ' ').title()} is required "
                "for separate columns format"
            )
        return v


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

#  gps check settings
def gpschecks_report_settings(
    project_id: str,
    settings_file: str,
    data: pl.DataFrame,
    config: GPSSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> GPSSettings:
    """Create and render the settings UI for gpschecks report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    gpschecks report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    data : pl.DataFrame
        Dataset to analyze for duplicates.
    config : DuplicatesSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    GPSSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for GPS CHecks report")
        st.write("---")

        default_settings = load_default_gpschecks_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=categorical_columns,
                    key="survey_key_gpschecks",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_gpschecks",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.subheader("Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_gpschecks",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=categorical_columns,
                    key="enumerator_gpschecks",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                default_team = default_settings.team
                default_team_index = (
                    categorical_columns.index(default_team)
                    if default_team and default_team in categorical_columns
                    else None
                )
                team = st.selectbox(
                    "Team",
                    options=categorical_columns,
                    key="team_gpschecks",
                    help="Select the column that contains the team identifier",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

    return GPSSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
    )


# =============================================================================
# GPS Column Configuration Functions
# =============================================================================


def _render_gps_column_actions(
    project_id: str, page_name_id: str, all_columns: list[str]
) -> None:
    """Render the GPS column configuration UI.

    Allows users to configure GPS data columns for either single-column format
    (comma-separated lat, lon, altitude, accuracy) or separate column format.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    all_columns : list[str]
        List of all available columns in the dataset.
    """
    gps_settings = duckdb_get_table(
        project_id,
        f"gps_columns_{page_name_id}",
        "logs",
    )

    gs1, gs2, _ = st.columns([0.4, 0.3, 0.3])
    with gs1:
        st.button(
            "Add GPS Column Configuration",
            key="add_gps_column",
            help="Add a new GPS column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_gps_column,
            args=(
                project_id,
                page_name_id,
                all_columns,
            ),
        )
    with gs2:
        _delete_gps_column(project_id, page_name_id, gps_settings)

    if gps_settings.is_empty():
        st.info(
            "Use the :material/add: button to add GPS column configurations and "
            "the :material/delete: button to remove them."
        )
    else:
        _render_gps_settings_table(gps_settings)


@st.dialog("Add GPS Column Configuration", width="medium")
def _add_gps_column(
    project_id: str, page_name_id: str, all_columns: list[str]
) -> None:
    """Dialog to add a new GPS column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    all_columns : list[str]
        List of all available columns in the dataset.
    """
    st.markdown("### Configure GPS Data Format")

    # GPS format type selection
    format_type = st.selectbox(
        label="GPS Data Format",
        options=[e.value for e in GPSFormatType],
        index=0,
        help="Select how GPS data is stored in your dataset.",
    )

    gps_config = {}
    gps_config["format_type"] = format_type

    if format_type == GPSFormatType.SINGLE_COLUMN.value:
        st.info(
            "**Single Column Format**: GPS data is stored in one column as "
            "delimited values (e.g., '-1.2028556 36.7772324 0.0 15.849' or "
            "'-1.2028556, 36.7772324, 0.0, 15.849')."
        )

        delimiter = st.selectbox(
            label="Delimiter",
            options=[e.value for e in DelimiterType],
            index=0,  # Space is the default (first in enum)
            help="Select the delimiter used to separate GPS values in the column.",
        )
        gps_config["delimiter"] = delimiter

        gps_column = st.selectbox(
            label="GPS Column",
            options=all_columns,
            index=None,
            help="Select the column containing delimited GPS data "
            "(latitude, longitude, altitude, accuracy).",
        )
        gps_config["gps_column"] = gps_column

    else:  # SEPARATE_COLUMNS
        st.info(
            "**Separate Columns Format**: GPS data is stored in separate columns "
            "for latitude, longitude, and optionally altitude and accuracy."
        )

        gc1, gc2 = st.columns(2)
        with gc1:
            latitude_column = st.selectbox(
                label="Latitude Column",
                options=all_columns,
                index=None,
                help="Select the column containing latitude values.",
            )
            gps_config["latitude_column"] = latitude_column

        with gc2:
            longitude_column = st.selectbox(
                label="Longitude Column",
                options=all_columns,
                index=None,
                help="Select the column containing longitude values.",
            )
            gps_config["longitude_column"] = longitude_column

        st.markdown("#### Optional Columns")
        oc1, oc2 = st.columns(2)
        with oc1:
            altitude_column = st.selectbox(
                label="Altitude Column (Optional)",
                options=[None] + all_columns,
                index=0,
                help="Select the column containing altitude values (optional).",
            )
            gps_config["altitude_column"] = altitude_column

        with oc2:
            accuracy_column = st.selectbox(
                label="Accuracy Column (Optional)",
                options=[None] + all_columns,
                index=0,
                help="Select the column containing accuracy values (optional).",
            )
            gps_config["accuracy_column"] = accuracy_column

    # Validate configuration
    try:
        validated_config = GPSColumnConfig(**gps_config)
        is_valid = True
    except ValidationError as e:
        is_valid = False
        error_messages = []
        for error in e.errors():
            field = error.get("loc", [""])[0]
            msg = error.get("msg", "")
            error_messages.append(f"• {field}: {msg}")

    # Add configuration button
    if st.button(
        "Add GPS Configuration",
        key="confirm_add_gps_column",
        type="primary",
        width="stretch",
        disabled=not is_valid,
    ):
        _update_gps_column_config(
            project_id,
            page_name_id,
            validated_config,
        )

        st.success("GPS column configuration added successfully.")
        st.rerun()


def _update_gps_column_config(
    project_id: str,
    page_name_id: str,
    gps_config: GPSColumnConfig,
) -> None:
    """Update the GPS column configuration in the database.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    gps_config : GPSColumnConfig
        Validated GPS column configuration.
    """
    # Get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"gps_columns_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configuration
    new_config = {
        "format_type": gps_config.format_type.value,
        "delimiter": gps_config.delimiter.value if gps_config.delimiter else None,
        "gps_column": gps_config.gps_column,
        "latitude_column": gps_config.latitude_column,
        "longitude_column": gps_config.longitude_column,
        "altitude_column": gps_config.altitude_column,
        "accuracy_column": gps_config.accuracy_column,
    }

    schema = {
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }

    # Create new config DataFrame
    new_config_df = pl.DataFrame([new_config], schema=schema)

    # Append to existing or create new
    if not existing_config.is_empty():
        updated_config = pl.concat([existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configuration
    duckdb_save_table(
        project_id,
        updated_config,
        f"gps_columns_{page_name_id}",
        db_name="logs",
    )


def _render_gps_settings_table(gps_settings: pl.DataFrame) -> None:
    """Render the GPS settings table in Streamlit.

    Parameters
    ----------
    gps_settings : pl.DataFrame
        GPS settings configuration.
    """
    with st.expander("GPS Column Settings", expanded=False):
        st.dataframe(
            gps_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "format_type": st.column_config.Column("Format Type"),
                "delimiter": st.column_config.Column("Delimiter"),
                "gps_column": st.column_config.Column("GPS Column"),
                "latitude_column": st.column_config.Column("Latitude Column"),
                "longitude_column": st.column_config.Column("Longitude Column"),
                "altitude_column": st.column_config.Column("Altitude Column"),
                "accuracy_column": st.column_config.Column("Accuracy Column"),
            },
        )


def _delete_gps_column(
    project_id: str, page_name_id: str, gps_settings: pl.DataFrame
) -> None:
    """Render delete GPS column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    gps_settings : pl.DataFrame
        Current GPS settings.
    """
    with (
        st.popover(
            label=":material/delete: Delete GPS configuration",
            width="stretch",
        ),
    ):
        st.markdown("#### Remove GPS column configuration")

        if gps_settings.is_empty():
            st.info("No GPS column configurations have been added yet.")
        else:
            gps_settings = gps_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("format_type")
                    + " - "
                    + pl.coalesce(
                        pl.col("gps_column"),
                        pl.concat_str(
                            [pl.col("latitude_column"), pl.col("longitude_column")],
                            separator=" / ",
                        ),
                    )
                ).alias("composite_index")
            )

            unique_index = (
                gps_settings["composite_index"].unique(maintain_order=True).to_list()
            )

            selected_index = st.selectbox(
                label="Select GPS configuration to remove",
                options=unique_index,
                help="Select the GPS configuration to remove from the list.",
            )

            if selected_index:
                confirm_delete = st.button(
                    label="Confirm deletion",
                    type="primary",
                    width="stretch",
                )
                if confirm_delete:
                    updated_settings = gps_settings.filter(
                        pl.col("composite_index") != selected_index
                    ).drop("composite_index", "index")

                    duckdb_save_table(
                        project_id,
                        updated_settings,
                        f"gps_columns_{page_name_id}",
                        "logs",
                    )

                    st.rerun()


# =============================================================================
# GPS Plotting and Analysis Functions
# =============================================================================


# plot gps coordinates on a map
def plot_gps_coordinates(
    df,
    enumerator: str | None,
    submissiondate: str | None,
    survey_id: str | None,
    gps_lat_col: str,
    gps_lon_col: str,
    color_col: str | None,
):
    """
    Plot GPS coordinates on a map, color-coded by a specified column using pydeck.

    Parameters
    ----------
    df : pd.DataFrame
        The input dataframe containing GPS data.
    enumerator : str
        The name of the enumerator column.
    submissiondate : str
        The name of the submission date column.
    survey_id : str
        The name of the survey id column.
    gps_lat_col : str
        The name of the latitude column.
    gps_lon_col : str
        The name of the longitude column.
    color_col : str
        The name of the column to use for color-coding.

    Returns
    -------
    None
    """
    plot_df = df.copy(deep=True)
    # Drop rows with missing coordinates
    plot_df = plot_df.dropna(subset=[gps_lat_col, gps_lon_col])

    # Assign a color to each unique value in color_col
    unique_values = plot_df[color_col].unique() if color_col else [None]
    # generate a color palette based on the number of unique values
    num_colors = len(unique_values) if color_col else 1
    if num_colors <= 10:
        color_palette = [
            [31, 119, 180, 160],
            [255, 127, 14, 160],
            [44, 160, 44, 160],
            [214, 39, 40, 160],
            [148, 103, 189, 160],
            [140, 86, 75, 160],
            [227, 119, 194, 160],
            [127, 127, 127, 160],
            [188, 189, 34, 160],
            [23, 190, 207, 160],
        ][:num_colors]
    else:
        # Use matplot lib colormap for more colors
        cmap = mpl.cm.get_cmap("tab20", num_colors)
        color_palette = [
            [int(r * 255), int(g * 255), int(b * 255), 160]
            for r, g, b, _ in [cmap(i) for i in range(num_colors)]
        ]
    if color_col:
        color_map = {
            val: color_palette[i % len(color_palette)]
            for i, val in enumerate(unique_values)
        }
        plot_df["color_value"] = plot_df[color_col].map(color_map)
    else:
        # If no color column is specified, use a default color
        color_map = {None: [31, 119, 180, 160]}
        plot_df["color_value"] = [color_map[None]] * len(plot_df)

    # Prepare data for pydeck
    map_data = []
    for _, row in plot_df.iterrows():
        points = {
            "longitude": float(row[gps_lon_col]),
            "latitude": float(row[gps_lat_col]),
            "color": row["color_value"],
        }

        # Dynamically construct tooltip
        tooltip_lines = []

        if enumerator:
            tooltip_lines.append(f"Enumerator: {row[enumerator]}")
        if submissiondate:
            tooltip_lines.append(f"Submission Date: {row[submissiondate]}")
        if survey_id:
            tooltip_lines.append(f"Survey ID: {row[survey_id]}")
        if color_col:
            tooltip_lines.append(f"{color_col}: {row[color_col]}")
        tooltip_lines.append(f"Latitude: {row[gps_lat_col]:.6f}")
        tooltip_lines.append(f"Longitude: {row[gps_lon_col]:.6f}")

        points["tooltip"] = "\n".join(tooltip_lines)

        # Append the point to the map data
        map_data.append(points)

    # Calculate map center
    center_lat = plot_df[gps_lat_col].mean()
    center_lon = plot_df[gps_lon_col].mean()

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_data,
        get_position=["longitude", "latitude"],
        get_fill_color="color",
        get_radius=50,
        radius_scale=6,
        radius_min_pixels=3,
        radius_max_pixels=8,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        longitude=float(center_lon), latitude=float(center_lat), zoom=10, pitch=0
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "{tooltip}"},
        map_style="mapbox://styles/mapbox/streets-v11",
    )

    st.pydeck_chart(deck, height=450, use_container_width=True)


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
        Q1 = group["distance_from_centroid"].quantile(0.25)
        Q3 = group["distance_from_centroid"].quantile(0.75)
        IQR = Q3 - Q1
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

    # Convert coordinates to a numpy array
    coords = df[[gps_lat_col, gps_lon_col]].values

    # Apply Local Outlier Factor
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
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


# plot clusters on map
def plot_clusters_on_map(
    df,
    gps_lat_col: str,
    gps_lon_col: str,
    enumerator: str | None,
    submission_date: str | None,
    survey_id: str | None,
    clustering_col: str | None,
    outlier_col: str | None,
):
    """
    Plot clusters of GPS points on a map, highlighting outliers.

    Parameters
    ----------
    df : pd.DataFrame
        The input dataframe containing GPS data.
    enumerator : str
        The name of the enumerator column.
    submission_date : str
        The name of the submission date column.
    survey_id : str
        The name of the survey ID column.
    gps_lat_col : str
        The name of the latitude column.
    gps_lon_col : str
        The name of the longitude column.
    outlier_col : str
        The name of the column indicating outliers.

    Returns
    -------
    None
    """
    # make a copy of the dataframe
    df = df.copy()

    # Create a clean data structure for pydeck
    map_data = []
    for _, row in df.iterrows():
        point = {
            # Ensure coordinates are in [longitude, latitude] order for pydeck
            "longitude": float(row[gps_lon_col]),
            "latitude": float(row[gps_lat_col]),
            "outlier_color": [242, 45, 17, 160]
            if row[outlier_col]
            else [17, 89, 242, 160],
        }

        # Dynamically construct tooltip
        tooltip_lines = []

        if enumerator:
            tooltip_lines.append(f"Enumerator: {row[enumerator]}")
        if submission_date:
            tooltip_lines.append(f"Date: {row[submission_date]}")
        if survey_id:
            tooltip_lines.append(f"Survey ID: {row[survey_id]}")
        if clustering_col:
            tooltip_lines.append(f"Cluster: {row[clustering_col]}")
        else:
            tooltip_lines.append("Cluster: No Cluster")
        if outlier_col:
            tooltip_lines.append(f"Outlier: {row[outlier_col]}")

        point["tooltip"] = "\n".join(tooltip_lines)

        map_data.append(point)

    # Calculate map center
    center_lat = df[gps_lat_col].mean()
    center_lon = df[gps_lon_col].mean()

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_data,
        get_position=["longitude", "latitude"],
        get_fill_color="outlier_color",
        get_radius=50,
        radius_scale=6,
        radius_min_pixels=3,
        radius_max_pixels=8,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        longitude=float(center_lon), latitude=float(center_lat), zoom=7, pitch=0
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "{tooltip}"},
        map_style="mapbox://styles/mapbox/streets-v11",
    )

    st.pydeck_chart(deck, height=450, use_container_width=True)


@demo_output_onboarding(TAB_NAME)
# gps checks report
def gpschecks_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
) -> None:
    """
    Generate the GPS checks report.

    Parameters
    ----------
    project_id : str
        The project ID.
    page_name_id : str
        The page name ID.
    data : pl.DataFrame
        The input dataframe containing survey data.
    setting_file : str
        The path to the settings file.
    config : dict
        Configuration settings for the report.

    Returns
    -------
    None
    """
    st.title("GPS Checks Report")

    _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(data, cols_only=True)

    string_numeric_cols = list(set(string_columns + numeric_columns))

    if data.is_empty():
        st.info(
            "No data available for the gps checks report. "
            "Please upload data to proceed."
        )
        return

    config_settings = GPSSettings(**config)

    _gpschecks_settings = gpschecks_report_settings(
        project_id,
        setting_file,
        data,
        config_settings,
        string_numeric_cols,
        datetime_columns,
    )

    st.subheader("GPS Columns Configuration")
    all_columns = list(data.columns)
    _render_gps_column_actions(project_id, page_name_id, all_columns)
