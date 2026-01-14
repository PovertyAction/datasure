from enum import Enum

import numpy as np
import polars as pl
import pydeck
import streamlit as st
from geopy.distance import geodesic
from pydantic import BaseModel, Field, ValidationError, field_validator
from sklearn.neighbors import LocalOutlierFactor

from datasure.utils.dataframe_utils import ColumnByType, get_df_columns
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    save_secrets,
    trigger_save,
)

TAB_NAME: str = "gpschecks"

# Initialize pydeck with default Mapbox API key from secrets if available
# Users can override this in the settings
try:
    if "mapbox_custom_key" in st.secrets:
        pydeck.settings.mapbox_key = st.secrets["mapbox_custom_key"]
    elif "default_mapbox_api_key" in st.secrets:
        pydeck.settings.mapbox_key = st.secrets["default_mapbox_api_key"]
except Exception:
    # If secrets are not available, pydeck key will be set later from user settings
    pass


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
    mapbox_key_option: str | None = Field(None, description="Mapbox API key option")
    mapbox_custom_key: str | None = Field(None, description="Custom Mapbox API key")


class GPSColumnConfig(BaseModel):
    """Configuration for GPS column setup."""

    alias: str = Field(..., min_length=1, description="Alias for GPS configuration")
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

        # Mapbox API Key Configuration
        with st.container(border=True):
            st.subheader("Mapbox API Token Configuration")
            st.caption(
                "Configure your Mapbox API key for map visualizations. "
                "You can use the default key or provide your own."
            )

            if "mapbox_custom_key" in st.secrets:
                mapbox_api_key = st.secrets["mapbox_custom_key"]
                using_default_key = False

            else:
                # if mapbox key is not available, fallback on default key
                mapbox_api_key = st.secrets["default_mapbox_api_key"]
                using_default_key = True

            # Load saved settings
            saved_key_option = default_settings.mapbox_key_option or "default_api_token"

            options_map = {
                "default_api_token": ":material/lock_open_right: Default Public Token",
                "add_api_token": ":material/lock: Add API Token",
            }

            ko1, ko2 = st.columns([0.3, 0.7])
            with ko1:
                mapbox_key_option = st.pills(
                    "Select Mapbox API Key Option",
                    options=options_map.keys(),
                    format_func=lambda x: options_map[x],
                    default=saved_key_option,
                    key="mapbox_key_option_gpschecks_pills",
                    help="Choose to use the default public token or provide your own",
                    selection_mode="single",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_mapbox_key_option"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"mapbox_key_option": mapbox_key_option}
                )

            with ko2:
                # Show text input if user wants to add own key
                mapbox_custom_key = st.text_input(
                    "Your Mapbox API Key",
                    value=mapbox_api_key,
                    type="password",
                    key="mapbox_custom_key_gpschecks",
                    help="Enter your Mapbox API key. Get one free at https://account.mapbox.com/",
                    disabled=mapbox_key_option == "default_api_token",
                    on_change=trigger_save,
                    kwargs={"state_name": "mapbox_custom_key"},
                )
                save_secrets("mapbox_custom_key", mapbox_custom_key)

                # Set the Mapbox key globally for pydeck
                if not using_default_key:
                    st.success("Custom Mapbox API key set successfully.")
                else:
                    st.success("Using default Mapbox API key from secrets.")

    return GPSSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
        mapbox_key_option=mapbox_key_option,
        mapbox_custom_key=mapbox_custom_key,
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
def _add_gps_column(project_id: str, page_name_id: str, all_columns: list[str]) -> None:
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

        # Auto-populate alias with column name
        default_alias = gps_column if gps_column else ""
        alias = st.text_input(
            label="Configuration Alias",
            value=default_alias,
            help="A name to identify this GPS configuration. "
            "Defaults to the GPS column name.",
        )
        gps_config["alias"] = alias

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

        # Alias input for separate columns
        alias = st.text_input(
            label="Configuration Alias",
            help="A name to identify this GPS configuration (required).",
        )
        gps_config["alias"] = alias

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
        "alias": gps_config.alias,
        "format_type": gps_config.format_type.value,
        "delimiter": gps_config.delimiter.value if gps_config.delimiter else None,
        "gps_column": gps_config.gps_column,
        "latitude_column": gps_config.latitude_column,
        "longitude_column": gps_config.longitude_column,
        "altitude_column": gps_config.altitude_column,
        "accuracy_column": gps_config.accuracy_column,
    }

    schema = {
        "alias": pl.Utf8,
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
                "alias": st.column_config.Column("Alias"),
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
                    + pl.col("alias")
                    + " ("
                    + pl.col("format_type")
                    + ")"
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

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_delete_gps_column",
                disabled=not selected_index,
            ):
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


@st.fragment
def _render_gps_coordinates(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
    team: str | None,
) -> None:
    """Render GPS coordinates visualization with interactive features.

    Allows users to:
    - Select GPS configuration by alias
    - Color points by categorical column
    - Filter points by categorical column
    - Hover to see ID, Date, Enumerator, Team, and GPS coordinates

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    data : pl.DataFrame
        Survey data containing GPS information.
    survey_key : str
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    enumerator : str | None
        Enumerator column name.
    team : str | None
        Team column name.
    """
    st.subheader("GPS Coordinates Visualization")

    # Load GPS configurations
    gps_settings = duckdb_get_table(
        project_id,
        f"gps_columns_{page_name_id}",
        "logs",
    )

    if gps_settings.is_empty():
        st.info(
            "No GPS configurations found. "
            "Please add a GPS column configuration in the section above."
        )
        return

    # Get list of aliases
    aliases = gps_settings["alias"].to_list()

    gp1, gp2, gp3 = st.columns([0.4, 0.3, 0.3])

    with gp1:
        # GPS configuration selection
        selected_alias = st.selectbox(
            label="Select GPS Configuration",
            options=aliases,
            help="Choose which GPS configuration to visualize.",
        )

    if not selected_alias:
        return

    # Get selected configuration
    selected_config = gps_settings.filter(pl.col("alias") == selected_alias).to_dicts()[
        0
    ]

    # Parse GPS data
    try:
        parsed_data = _parse_gps_data(data, selected_config)
    except Exception as e:
        st.error(f"Error parsing GPS data: {e}")
        return

    # Drop rows with missing coordinates
    parsed_data = parsed_data.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    )

    if parsed_data.is_empty():
        st.warning("No valid GPS coordinates found in the data.")
        return

    # Get categorical columns for coloring and filtering
    df_columns: ColumnByType = get_df_columns(parsed_data)
    categorical_cols = df_columns.categorical_columns

    # UI controls
    with gp2:
        color_by = st.selectbox(
            label="Color Points By",
            options=categorical_cols,
            index=None,
            help="Select a categorical column to color the GPS points.",
        )

    with gp3:
        filter_by = st.selectbox(
            label="Filter Points By",
            options=categorical_cols,
            index=None,
            help="Select a categorical column to filter the GPS points.",
        )

    # Apply filter if selected
    filtered_data = parsed_data
    filter_values = None

    if filter_by:
        unique_values = parsed_data[filter_by].unique().drop_nulls().sort().to_list()
        filter_values = st.multiselect(
            label=f"Select {filter_by} values to display",
            options=unique_values,
            default=unique_values,
            help=f"Choose which {filter_by} values to show on the map.",
        )

        if filter_values:
            filtered_data = filtered_data.filter(pl.col(filter_by).is_in(filter_values))

    if filtered_data.is_empty():
        st.warning("No data matches the selected filters.")
        return

    # Prepare data for pydeck with hover information
    map_df = filtered_data.select(
        [
            pl.col("latitude").alias("lat"),
            pl.col("longitude").alias("lon"),
        ]
    )

    # Add key columns for hover tooltips
    tooltip_fields = []
    if survey_key:
        map_df = map_df.with_columns(filtered_data[survey_key].alias("ID"))
        tooltip_fields.append("ID")
    if survey_date:
        map_df = map_df.with_columns(filtered_data[survey_date].alias("Date"))
        tooltip_fields.append("Date")
    if enumerator:
        map_df = map_df.with_columns(filtered_data[enumerator].alias("Enumerator"))
        tooltip_fields.append("Enumerator")
    if team:
        map_df = map_df.with_columns(filtered_data[team].alias("Team"))
        tooltip_fields.append("Team")

    # Add GPS coordinates to tooltip
    tooltip_fields.extend(["lat", "lon"])

    # Add color column if coloring by a categorical variable
    if color_by:
        map_df = map_df.with_columns(filtered_data[color_by].alias("color_group"))
        tooltip_fields.append(color_by)

    # Convert to pandas for pydeck
    map_pd = map_df.to_pandas()

    # Create tooltip configuration
    tooltip_config = {
        "html": "<br>".join(
            [f"<b>{field}:</b> {{{field}}}" for field in tooltip_fields]
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    # Calculate center coordinates for initial view
    center_lat = map_pd["lat"].mean()
    center_lon = map_pd["lon"].mean()

    # Create pydeck layer
    layer = pydeck.Layer(
        "ScatterplotLayer",
        data=map_pd,
        get_position=["lon", "lat"],
        get_radius=100,
        get_fill_color=[255, 0, 0, 160] if not color_by else None,
        pickable=True,
        auto_highlight=True,
    )

    # Set initial view state
    view_state = pydeck.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=10,
        pitch=0,
    )

    # Get Mapbox API key
    mapbox_key = pydeck.settings.mapbox_key
    if not mapbox_key:
        # Fallback to secrets if not set
        if "mapbox_custom_key" in st.secrets:
            mapbox_key = st.secrets["mapbox_custom_key"]
        elif "default_mapbox_api_key" in st.secrets:
            mapbox_key = st.secrets["default_mapbox_api_key"]

    # Create deck with explicit API key
    deck = pydeck.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip_config,
        map_style="mapbox://styles/mapbox/light-v9",
        api_keys={"mapbox": mapbox_key} if mapbox_key else None,
    )

    # Display the map
    st.pydeck_chart(deck, height=600, width="stretch")

    # Display summary statistics
    st.caption(f"Displaying {len(map_pd):,} GPS points")


@st.fragment
def _render_gps_outliers_checks(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
) -> None:
    """Render GPS outliers detection and visualization.

    Allows users to:
    - Select GPS configuration by alias
    - Choose outlier detection method (auto or by column)
    - Configure detection parameters
    - View outliers on interactive map
    - Download outliers data

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    data : pl.DataFrame
        Survey data containing GPS information.
    survey_key : str
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    enumerator : str | None
        Enumerator column name.
    """
    st.subheader("GPS Outliers Detection")

    # Load GPS configurations
    gps_settings = duckdb_get_table(
        project_id,
        f"gps_columns_{page_name_id}",
        "logs",
    )

    if gps_settings is None or gps_settings.is_empty():
        st.info(
            "No GPS configurations found. "
            "Please add a GPS column configuration in the section above."
        )
        return

    # Get list of aliases
    aliases = gps_settings["alias"].to_list()

    go1, go2, go3 = st.columns([0.4, 0.3, 0.3])

    with go1:
        # GPS configuration selection
        selected_alias = st.selectbox(
            label="Select GPS Configuration",
            options=aliases,
            key="outlier_gps_config",
            help="Choose which GPS configuration to use for outlier detection.",
        )

    if not selected_alias:
        return

    # Get selected configuration
    selected_config = gps_settings.filter(pl.col("alias") == selected_alias).to_dicts()[
        0
    ]

    # Parse GPS data
    parsed_data = _parse_gps_data(data, selected_config)

    # Check if GPS data was successfully parsed
    if "latitude" not in parsed_data.columns or "longitude" not in parsed_data.columns:
        st.warning("Unable to parse GPS coordinates from the selected configuration.")
        return

    # Filter out invalid coordinates
    parsed_data = parsed_data.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    )

    if parsed_data.is_empty():
        st.warning("No valid GPS coordinates found in the data.")
        return

    # Convert to pandas for outlier detection
    df_pd = parsed_data.to_pandas()

    # Get categorical columns for clustering
    df_columns: ColumnByType = get_df_columns(parsed_data)
    string_columns = df_columns.categorical_columns

    with go2:
        # Detection method selection
        detection_method = st.selectbox(
            label="Detection Method",
            options=["Auto-Clustering (LOF)", "Cluster by Column"],
            key="outlier_detection_method",
            help="Choose how to detect outliers: automatic or based on a grouping column.",
        )

    # Configure detection parameters based on method
    if detection_method == "Auto-Clustering (LOF)":
        # Check if we have enough data points
        n_samples = len(df_pd)

        # LOF requires at least 6 points to work properly (min_neighbors=5)
        if n_samples < 6:
            st.warning(
                f"Not enough GPS points for Auto-Clustering. "
                f"Found {n_samples} point(s), need at least 6. "
                "Try 'Cluster by Column' method or add more data."
            )
            return

        max_neighbors = min(50, n_samples - 1)

        with go3:
            n_neighbors = st.slider(
                label="Number of Neighbors",
                min_value=5,
                max_value=max_neighbors,
                value=min(20, max_neighbors),
                key="outlier_n_neighbors",
                help="Number of neighbors for Local Outlier Factor algorithm.",
            )

        contamination = st.slider(
            label="Expected Outlier Proportion",
            min_value=0.01,
            max_value=0.5,
            value=0.1,
            step=0.01,
            key="outlier_contamination",
            help="Expected proportion of outliers in the data.",
        )

        # Show warning if data is small
        if n_samples < 20:
            st.warning(
                f"⚠ Only {n_samples} GPS points available. "
                "LOF works best with larger datasets (recommended: 50+ points)."
            )

        # Detect outliers using LOF
        outlier_df = detect_outliers_with_lof(
            df_pd, "latitude", "longitude", n_neighbors, contamination
        )

    else:  # Cluster by Column
        with go3:
            clustering_col = st.selectbox(
                label="Clustering Column",
                options=[None] + string_columns,
                key="outlier_clustering_col",
                help="Select a column to group GPS coordinates for outlier detection.",
            )

        if not clustering_col:
            st.info("Please select a clustering column to continue.")
            return

        # Detect outliers using clustering column
        outlier_df = detect_outliers_with_clusters(
            df_pd, "latitude", "longitude", clustering_col
        )

    # Calculate outlier statistics
    num_outliers = outlier_df["Outlier"].sum()
    total_points = len(outlier_df)
    outlier_pct = (num_outliers / total_points * 100) if total_points > 0 else 0

    # Display summary statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total GPS Points", f"{total_points:,}")
    with col2:
        st.metric("Outliers Detected", f"{num_outliers:,}")
    with col3:
        st.metric("Outlier Percentage", f"{outlier_pct:.2f}%")

    # Display map with outliers
    st.subheader("Outliers Map")
    plot_clusters_on_map(
        outlier_df,
        "latitude",
        "longitude",
        enumerator,
        survey_date,
        survey_key,
        clustering_col if detection_method == "Cluster by Column" else None,
        "Outlier",
    )

    # Display outliers data table
    with st.expander("View Outliers Data", expanded=False):
        # Filter to show only outliers
        outliers_only = outlier_df[outlier_df["Outlier"]].copy()

        if not outliers_only.empty:
            # Select relevant columns
            display_cols = []
            if survey_key and survey_key in outliers_only.columns:
                display_cols.append(survey_key)
            if survey_date and survey_date in outliers_only.columns:
                display_cols.append(survey_date)
            if enumerator and enumerator in outliers_only.columns:
                display_cols.append(enumerator)

            display_cols.extend(["latitude", "longitude"])

            if detection_method == "Cluster by Column" and clustering_col:
                if clustering_col in outliers_only.columns:
                    display_cols.append(clustering_col)
                if "distance_from_centroid" in outliers_only.columns:
                    display_cols.append("distance_from_centroid")

            # Show only available columns
            available_cols = [
                col for col in display_cols if col in outliers_only.columns
            ]

            st.dataframe(
                outliers_only[available_cols],
                width="stretch",
                hide_index=True,
            )

            # Download button
            csv = outliers_only[available_cols].to_csv(index=False)
            st.download_button(
                label="Download Outliers Data",
                data=csv,
                file_name=f"gps_outliers_{selected_alias}.csv",
                mime="text/csv",
            )
        else:
            st.success("No outliers detected!")


@st.fragment
def _render_gps_comparison_checks(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
) -> None:
    """Render GPS comparison checks between two GPS configurations.

    Allows users to:
    - Select two GPS configurations to compare
    - Set a distance threshold for flagging discrepancies
    - View flagged points on interactive map
    - Download comparison results

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    data : pl.DataFrame
        Survey data containing GPS information.
    survey_key : str
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    enumerator : str | None
        Enumerator column name.
    """
    st.subheader("GPS Coordinates Comparison")
    st.caption(
        "Compare GPS coordinates from two different sources and flag discrepancies "
        "that exceed a specified distance threshold."
    )

    # Load GPS configurations
    gps_settings = duckdb_get_table(
        project_id,
        f"gps_columns_{page_name_id}",
        "logs",
    )

    if gps_settings is None or gps_settings.is_empty():
        st.info(
            "No GPS configurations found. "
            "Please add at least two GPS column configurations in the section above."
        )
        return

    # Get list of aliases
    aliases = gps_settings["alias"].to_list()

    if len(aliases) < 2:
        st.warning(
            "⚠ Need at least 2 GPS configurations to compare. "
            f"Currently have {len(aliases)} configuration(s). "
            "Please add more GPS column configurations above."
        )
        return

    gc1, gc2, gc3 = st.columns([0.3, 0.3, 0.4])

    with gc1:
        # First GPS configuration selection
        gps_config_1 = st.selectbox(
            label="First GPS Configuration",
            options=aliases,
            key="comparison_gps_config_1",
            help="Select the first GPS configuration to compare.",
        )

    with gc2:
        # Second GPS configuration selection
        # Filter out the first selection from options
        remaining_aliases = [a for a in aliases if a != gps_config_1]
        gps_config_2 = st.selectbox(
            label="Second GPS Configuration",
            options=remaining_aliases,
            key="comparison_gps_config_2",
            help="Select the second GPS configuration to compare.",
        )

    if not gps_config_1 or not gps_config_2:
        return

    with gc3:
        # Distance threshold in meters
        distance_threshold = st.number_input(
            label="Distance Threshold (meters)",
            min_value=1,
            max_value=100000,
            value=100,
            step=10,
            key="comparison_distance_threshold",
            help="Flag GPS points where the distance between the two configurations exceeds this threshold.",
        )

    # Get configurations
    config_1 = gps_settings.filter(pl.col("alias") == gps_config_1).to_dicts()[0]
    config_2 = gps_settings.filter(pl.col("alias") == gps_config_2).to_dicts()[0]

    # Parse GPS data from both configurations
    parsed_data_1 = _parse_gps_data(data, config_1)
    parsed_data_2 = _parse_gps_data(data, config_2)

    # Check if GPS data was successfully parsed
    if (
        "latitude" not in parsed_data_1.columns
        or "longitude" not in parsed_data_1.columns
    ):
        st.warning(f"Unable to parse GPS coordinates from '{gps_config_1}'.")
        return

    if (
        "latitude" not in parsed_data_2.columns
        or "longitude" not in parsed_data_2.columns
    ):
        st.warning(f"Unable to parse GPS coordinates from '{gps_config_2}'.")
        return

    # Rename columns to distinguish between the two GPS sources
    parsed_data_1 = parsed_data_1.rename({"latitude": "lat_1", "longitude": "lon_1"})
    parsed_data_2 = parsed_data_2.rename({"latitude": "lat_2", "longitude": "lon_2"})

    # Merge the two datasets based on survey key
    if (
        survey_key
        and survey_key in parsed_data_1.columns
        and survey_key in parsed_data_2.columns
    ):
        comparison_data = parsed_data_1.join(
            parsed_data_2.select([survey_key, "lat_2", "lon_2"]),
            on=survey_key,
            how="inner",
        )
    else:
        st.error(
            "Survey key is required to match GPS coordinates between the two configurations."
        )
        return

    # Filter out rows with missing coordinates
    comparison_data = comparison_data.filter(
        pl.col("lat_1").is_not_null()
        & pl.col("lon_1").is_not_null()
        & pl.col("lat_2").is_not_null()
        & pl.col("lon_2").is_not_null()
    )

    if comparison_data.is_empty():
        st.warning("No matching GPS coordinates found between the two configurations.")
        return

    # Convert to pandas for distance calculation
    comparison_df = comparison_data.to_pandas()

    # Calculate distance between the two GPS points
    def calculate_distance(row):
        try:
            return geodesic(
                (row["lat_1"], row["lon_1"]), (row["lat_2"], row["lon_2"])
            ).meters
        except Exception:
            return None

    comparison_df["distance_meters"] = comparison_df.apply(calculate_distance, axis=1)

    # Remove rows where distance couldn't be calculated
    comparison_df = comparison_df.dropna(subset=["distance_meters"])

    if comparison_df.empty:
        st.warning("Unable to calculate distances between GPS coordinates.")
        return

    # Flag points exceeding threshold
    comparison_df["exceeds_threshold"] = (
        comparison_df["distance_meters"] > distance_threshold
    )

    # Calculate statistics
    total_points = len(comparison_df)
    flagged_points = comparison_df["exceeds_threshold"].sum()
    flagged_pct = (flagged_points / total_points * 100) if total_points > 0 else 0
    avg_distance = comparison_df["distance_meters"].mean()
    max_distance = comparison_df["distance_meters"].max()

    # Display summary statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Comparisons", f"{total_points:,}")
    with col2:
        st.metric("Flagged Points", f"{flagged_points:,}")
    with col3:
        st.metric("Average Distance", f"{avg_distance:.1f} m")
    with col4:
        st.metric("Max Distance", f"{max_distance:.1f} m")

    if flagged_pct > 0:
        st.warning(
            f"⚠ {flagged_pct:.1f}% of GPS points exceed the {distance_threshold}m threshold"
        )
    else:
        st.success(f"✓ All GPS points are within {distance_threshold}m of each other")

    # Display comparison map
    st.subheader("Comparison Map")

    # Prepare data for map visualization
    # We'll show the first GPS point and color by whether it exceeds threshold
    map_df = comparison_df.copy()
    map_df["lat"] = map_df["lat_1"]
    map_df["lon"] = map_df["lon_1"]
    map_df["status"] = map_df["exceeds_threshold"].map(
        {True: "Exceeds Threshold", False: "Within Threshold"}
    )

    # Build tooltip fields
    tooltip_fields = []
    if survey_key and survey_key in map_df.columns:
        tooltip_fields.append(survey_key)
    if survey_date and survey_date in map_df.columns:
        tooltip_fields.append(survey_date)
    if enumerator and enumerator in map_df.columns:
        tooltip_fields.append(enumerator)
    tooltip_fields.extend(["lat", "lon", "distance_meters", "status"])

    # Create tooltip configuration
    tooltip_config = {
        "html": "<br>".join(
            [f"<b>{field}:</b> {{{field}}}" for field in tooltip_fields]
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    # Calculate center coordinates
    center_lat = map_df["lat"].mean()
    center_lon = map_df["lon"].mean()

    # Color points based on threshold
    map_df["color"] = map_df["exceeds_threshold"].apply(
        lambda x: [255, 0, 0, 160] if x else [0, 255, 0, 160]
    )

    # Create pydeck layer
    layer = pydeck.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=100,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    # Set initial view state
    view_state = pydeck.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=10,
        pitch=0,
    )

    # Get Mapbox API key
    mapbox_key = pydeck.settings.mapbox_key
    if not mapbox_key:
        if "mapbox_custom_key" in st.secrets:
            mapbox_key = st.secrets["mapbox_custom_key"]
        elif "default_mapbox_api_key" in st.secrets:
            mapbox_key = st.secrets["default_mapbox_api_key"]

    # Create deck
    deck = pydeck.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip_config,
        map_style="mapbox://styles/mapbox/light-v9",
        api_keys={"mapbox": mapbox_key} if mapbox_key else None,
    )

    # Display the map
    st.pydeck_chart(deck, height=600, width="stretch")

    # Display comparison data table
    with st.expander("View Comparison Details", expanded=False):
        # Select relevant columns
        display_cols = []
        if survey_key and survey_key in comparison_df.columns:
            display_cols.append(survey_key)
        if survey_date and survey_date in comparison_df.columns:
            display_cols.append(survey_date)
        if enumerator and enumerator in comparison_df.columns:
            display_cols.append(enumerator)

        display_cols.extend(
            ["lat_1", "lon_1", "lat_2", "lon_2", "distance_meters", "exceeds_threshold"]
        )

        # Show only available columns
        available_cols = [col for col in display_cols if col in comparison_df.columns]

        # Rename columns for better readability
        display_df = comparison_df[available_cols].copy()
        display_df = display_df.rename(
            columns={
                "lat_1": f"{gps_config_1}_lat",
                "lon_1": f"{gps_config_1}_lon",
                "lat_2": f"{gps_config_2}_lat",
                "lon_2": f"{gps_config_2}_lon",
                "distance_meters": "Distance (m)",
                "exceeds_threshold": "Flagged",
            }
        )

        # Sort by distance descending to show largest discrepancies first
        display_df = display_df.sort_values("Distance (m)", ascending=False)

        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
        )

        # Download button
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download Comparison Data",
            data=csv,
            file_name=f"gps_comparison_{gps_config_1}_vs_{gps_config_2}.csv",
            mime="text/csv",
        )


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
    Plot GPS coordinates on a map with hover tooltips using pydeck.

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

    # Rename columns for pydeck
    plot_df = plot_df.rename(columns={gps_lat_col: "lat", gps_lon_col: "lon"})

    # Build tooltip fields
    tooltip_fields = []
    if survey_id and survey_id in plot_df.columns:
        tooltip_fields.append(survey_id)
    if submissiondate and submissiondate in plot_df.columns:
        tooltip_fields.append(submissiondate)
    if enumerator and enumerator in plot_df.columns:
        tooltip_fields.append(enumerator)
    tooltip_fields.extend(["lat", "lon"])
    if color_col and color_col in plot_df.columns:
        tooltip_fields.append(color_col)

    # Create tooltip configuration
    tooltip_config = {
        "html": "<br>".join(
            [f"<b>{field}:</b> {{{field}}}" for field in tooltip_fields]
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    # Calculate center coordinates
    center_lat = plot_df["lat"].mean()
    center_lon = plot_df["lon"].mean()

    # Create pydeck layer
    layer = pydeck.Layer(
        "ScatterplotLayer",
        data=plot_df,
        get_position=["lon", "lat"],
        get_radius=100,
        get_fill_color=[255, 0, 0, 160],
        pickable=True,
        auto_highlight=True,
    )

    # Set initial view state
    view_state = pydeck.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=10,
        pitch=0,
    )

    # Get Mapbox API key
    mapbox_key = pydeck.settings.mapbox_key
    if not mapbox_key:
        # Fallback to secrets if not set
        if "mapbox_custom_key" in st.secrets:
            mapbox_key = st.secrets["mapbox_custom_key"]
        elif "default_mapbox_api_key" in st.secrets:
            mapbox_key = st.secrets["default_mapbox_api_key"]

    # Create deck with explicit API key
    deck = pydeck.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip_config,
        map_style="mapbox://styles/mapbox/light-v9",
        api_keys={"mapbox": mapbox_key} if mapbox_key else None,
    )

    # Display the map
    st.pydeck_chart(deck, height=600, width="stretch")


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

    # Rename columns for pydeck
    df = df.rename(columns={gps_lat_col: "lat", gps_lon_col: "lon"})

    # Create outlier status column for coloring
    df["outlier_status"] = df[outlier_col].map({True: "Outlier", False: "Normal"})

    # Build tooltip fields
    tooltip_fields = []
    if survey_id and survey_id in df.columns:
        tooltip_fields.append(survey_id)
    if submission_date and submission_date in df.columns:
        tooltip_fields.append(submission_date)
    if enumerator and enumerator in df.columns:
        tooltip_fields.append(enumerator)
    tooltip_fields.extend(["lat", "lon", "outlier_status"])
    if clustering_col and clustering_col in df.columns:
        tooltip_fields.append(clustering_col)

    # Create tooltip configuration
    tooltip_config = {
        "html": "<br>".join(
            [f"<b>{field}:</b> {{{field}}}" for field in tooltip_fields]
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    # Calculate center coordinates
    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    # Color outliers red, normal points blue
    df["color"] = df["outlier_status"].apply(
        lambda x: [255, 0, 0, 160] if x == "Outlier" else [0, 0, 255, 160]
    )

    # Create pydeck layer
    layer = pydeck.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["lon", "lat"],
        get_radius=100,
        get_fill_color="color",
        pickable=True,
        auto_highlight=True,
    )

    # Set initial view state
    view_state = pydeck.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=7,
        pitch=0,
    )

    # Get Mapbox API key
    mapbox_key = pydeck.settings.mapbox_key
    if not mapbox_key:
        # Fallback to secrets if not set
        if "mapbox_custom_key" in st.secrets:
            mapbox_key = st.secrets["mapbox_custom_key"]
        elif "default_mapbox_api_key" in st.secrets:
            mapbox_key = st.secrets["default_mapbox_api_key"]

    # Create deck with explicit API key
    deck = pydeck.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip_config,
        map_style="mapbox://styles/mapbox/light-v9",
        api_keys={"mapbox": mapbox_key} if mapbox_key else None,
    )

    # Display the map
    st.pydeck_chart(deck, height=600, width="stretch")


@demo_output_onboarding(TAB_NAME)
# gps checks report
def gpschecks_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
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

    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns

    if data.is_empty():
        st.info(
            "No data available for the gps checks report. "
            "Please upload data to proceed."
        )
        return

    config_settings = GPSSettings(**config)

    # Configure pydeck with appropriate Mapbox API key
    mapbox_key_option = config_settings.mapbox_key_option
    mapbox_custom_key = config_settings.mapbox_custom_key

    # Set the appropriate key based on user's preference
    if mapbox_key_option == "add_api_token" and mapbox_custom_key:
        # User wants to use their own custom key
        pydeck.settings.mapbox_key = mapbox_custom_key
    elif mapbox_key_option == "default_api_token" or not mapbox_key_option:
        # User wants to use default key or hasn't selected yet
        if "mapbox_custom_key" in st.secrets:
            pydeck.settings.mapbox_key = st.secrets["mapbox_custom_key"]
        elif "default_mapbox_api_key" in st.secrets:
            pydeck.settings.mapbox_key = st.secrets["default_mapbox_api_key"]

    # If still no key set and custom key is saved, use it
    if not pydeck.settings.mapbox_key and mapbox_custom_key:
        pydeck.settings.mapbox_key = mapbox_custom_key

    _gpschecks_settings = gpschecks_report_settings(
        project_id,
        setting_file,
        data,
        config_settings,
        categorical_columns,
        datetime_columns,
    )

    st.subheader("GPS Columns Configuration")
    all_columns = list(data.columns)
    _render_gps_column_actions(project_id, page_name_id, all_columns)

    st.write("---")

    mapbox_key = _gpschecks_settings.mapbox_custom_key
    pydeck.settings.mapbox_key = mapbox_key

    # Render GPS coordinates visualization
    _render_gps_coordinates(
        project_id,
        page_name_id,
        data,
        config_settings.survey_key,
        config_settings.survey_date,
        config_settings.enumerator,
        config_settings.team,
    )

    st.write("---")

    # Render GPS outliers detection
    _render_gps_outliers_checks(
        project_id,
        page_name_id,
        data,
        config_settings.survey_key,
        config_settings.survey_date,
        config_settings.enumerator,
    )

    st.write("---")

    # Render GPS comparison checks
    _render_gps_comparison_checks(
        project_id,
        page_name_id,
        data,
        config_settings.survey_key,
        config_settings.survey_date,
        config_settings.enumerator,
    )
