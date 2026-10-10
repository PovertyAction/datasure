from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl
import pydeck
import streamlit as st
from geopy.distance import geodesic
from pydantic import ValidationError

if TYPE_CHECKING:
    import pandas as pd

from datasure.checks.gpschecks.compute import (
    _build_map_dataframe,
    _build_tooltip_config,
    _collect_optional_fields,
    _get_gps_column_settings,
    _get_mapbox_key,
    _has_parsed_coords,
    _identity_optional_fields,
    _parse_gps_data,
    _save_gps_column_settings,
    detect_outliers_with_clusters,
    detect_outliers_with_lof,
)
from datasure.checks.gpschecks.models import MAPBOX_STYLE
from datasure.checks.gpschecks.review import (
    ACCEPTED_STATUS,
    GPS_CHECK_TYPE,
    OUTLIER_STATUS,
    CoordinateColumns,
    GPSAction,
    GPSSelection,
    accepted_gps_keys,
    allowed_gps_actions,
    build_gps_entries,
    coordinate_columns,
    count_unreviewed_outliers,
    mark_gps_reviewed,
    outlier_status,
    outliers_table,
    select_gps_outlier,
    validate_coordinates,
)
from datasure.checks.gpschecks.settings_ui import gpschecks_report_settings
from datasure.checks.outliers.review import (
    REVIEW_COLUMNS,
    REVIEW_STATUS_COL,
    highlight_reviewed_row,
    key_has_conflicting_values,
)
from datasure.models.enums import DelimiterType, GPSFormatType, GPSOutlierMethod
from datasure.models.schemas import GPSColumnConfig, GPSSettings
from datasure.processing.corrections import CorrectionProcessor
from datasure.utils.correction_form import apply_correction_entries, get_current_value
from datasure.utils.dataframe_utils import ColumnByType, get_df_columns
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import is_demo_project
from datasure.utils.ui_utils import (
    queue_notice,
    row_styler,
    show_queued_notices,
    styled_dataframe,
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
    gps_settings = _get_gps_column_settings(project_id, page_name_id)

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
    existing_config = _get_gps_column_settings(project_id, page_name_id)

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
    _save_gps_column_settings(project_id, page_name_id, updated_config)


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

                _save_gps_column_settings(project_id, page_name_id, updated_settings)

                st.rerun()


# =============================================================================
# GPS Plotting and Analysis Functions
# =============================================================================


def _apply_category_filter(data: pl.DataFrame, filter_by: str | None) -> pl.DataFrame:
    """Apply category-based filtering with a multiselect UI.

    Parameters
    ----------
    data : pl.DataFrame
        Data to filter.
    filter_by : str | None
        Column name to filter by, or None to skip filtering.

    Returns
    -------
    pl.DataFrame
        Filtered data (or original data if no filter applied).
    """
    if not filter_by:
        return data

    unique_values = data[filter_by].unique().drop_nulls().sort().to_list()
    filter_values = st.multiselect(
        label=f"Select {filter_by} values to display",
        options=unique_values,
        default=unique_values,
        help=f"Choose which {filter_by} values to show on the map.",
    )

    if filter_values:
        return data.filter(pl.col(filter_by).is_in(filter_values))
    return data


def _render_scatterplot_map(
    map_pd,
    tooltip_fields: list[str],
    fill_color: list[int] | str | None = None,
    zoom: int = 10,
    height: int = 600,
) -> None:
    """Render a pydeck scatterplot map in Streamlit.

    Parameters
    ----------
    map_pd : pd.DataFrame
        Pandas DataFrame with 'lat' and 'lon' columns.
    tooltip_fields : list[str]
        Field names for the hover tooltip.
    fill_color : list[int] | str | None
        Fill color for points. Can be an RGBA list, a column name string,
        or None for pydeck default.
    zoom : int
        Initial zoom level.
    height : int
        Chart height in pixels.
    """
    tooltip_config = _build_tooltip_config(tooltip_fields)

    center_lat = map_pd["lat"].mean()
    center_lon = map_pd["lon"].mean()

    layer = pydeck.Layer(
        "ScatterplotLayer",
        data=map_pd,
        get_position=["lon", "lat"],
        get_radius=100,
        radius_min_pixels=5,
        get_fill_color=fill_color,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pydeck.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=0,
    )

    mapbox_key = _get_mapbox_key()

    deck = pydeck.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip_config,
        map_style=MAPBOX_STYLE,
        api_keys={"mapbox": mapbox_key} if mapbox_key else None,
    )

    st.pydeck_chart(deck, height=height, width="stretch")


def _load_and_parse_gps_data(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    alias_select_key: str | None = None,
) -> tuple[pl.DataFrame | None, str | None, pl.DataFrame | None]:
    """Load GPS configuration, let user select alias, and parse GPS data.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    data : pl.DataFrame
        Survey data containing GPS information.
    alias_select_key : str | None
        Streamlit widget key for the alias selectbox. If None, uses default.

    Returns
    -------
    tuple[pl.DataFrame | None, str | None, pl.DataFrame | None]
        (gps_settings, selected_alias, parsed_data) where any value may be
        None if a precondition failed (with appropriate UI messages shown).
    """
    gps_settings = _get_gps_column_settings(project_id, page_name_id)

    if gps_settings is None or gps_settings.is_empty():
        st.info(
            "No GPS configurations found. "
            "Please add a GPS column configuration in the section above."
        )
        return None, None, None

    aliases = gps_settings["alias"].to_list()

    selectbox_kwargs = {
        "label": "Select GPS Configuration",
        "options": aliases,
    }
    if alias_select_key:
        selectbox_kwargs["key"] = alias_select_key

    selected_alias = st.selectbox(**selectbox_kwargs)

    if not selected_alias:
        return gps_settings, None, None

    selected_config = gps_settings.filter(pl.col("alias") == selected_alias).to_dicts()[
        0
    ]

    try:
        parsed_data = _parse_gps_data(data, selected_config)
    except Exception as e:
        st.error(f"Error parsing GPS data: {e}")
        return gps_settings, selected_alias, None

    if "latitude" not in parsed_data.columns or "longitude" not in parsed_data.columns:
        st.warning("Unable to parse GPS coordinates from the selected configuration.")
        return gps_settings, selected_alias, None

    parsed_data = parsed_data.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    )

    if parsed_data.is_empty():
        st.warning("No valid GPS coordinates found in the data.")
        return gps_settings, selected_alias, None

    return gps_settings, selected_alias, parsed_data


def _run_lof_detection(
    df_pd,
    n_samples: int,
    go3_column,
) -> object | None:
    """Render LOF detection UI controls and run detection.

    Parameters
    ----------
    df_pd : pd.DataFrame
        Pandas DataFrame with latitude and longitude columns.
    n_samples : int
        Number of data points available.
    go3_column
        Streamlit column context for the neighbors slider.

    Returns
    -------
    pd.DataFrame | None
        DataFrame with Outlier column, or None if insufficient data.
    """
    if n_samples < 6:
        st.warning(
            f"Not enough GPS points for Auto-Clustering. "
            f"Found {n_samples} point(s), need at least 6. "
            "Try 'Cluster by Column' method or add more data."
        )
        return None

    max_neighbors = min(50, n_samples - 1)

    with go3_column:
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

    if n_samples < 20:
        st.warning(
            f"Only {n_samples} GPS points available. "
            "LOF works best with larger datasets (recommended: 50+ points)."
        )

    return detect_outliers_with_lof(
        df_pd, "latitude", "longitude", n_neighbors, contamination
    )


def _run_cluster_detection(
    df_pd,
    string_columns: list[str],
    go3_column,
) -> tuple[object | None, str | None]:
    """Render cluster detection UI controls and run detection.

    Parameters
    ----------
    df_pd : pd.DataFrame
        Pandas DataFrame with latitude and longitude columns.
    string_columns : list[str]
        Available categorical columns for clustering.
    go3_column
        Streamlit column context for the clustering column selector.

    Returns
    -------
    tuple[pd.DataFrame | None, str | None]
        (outlier_df, clustering_col) or (None, None) if no column selected.
    """
    with go3_column:
        clustering_col = st.selectbox(
            label="Clustering Column",
            options=[None] + string_columns,
            key="outlier_clustering_col",
            help="Select a column to group GPS coordinates for outlier detection.",
        )

    if not clustering_col:
        st.info("Please select a clustering column to continue.")
        return None, None

    outlier_df = detect_outliers_with_clusters(
        df_pd, "latitude", "longitude", clustering_col
    )
    return outlier_df, clustering_col


def _filter_available_columns(df, columns: list[str]) -> list[str]:
    """Return the subset of `columns` that are present in `df`.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to check column presence against.
    columns : list[str]
        Candidate column names.

    Returns
    -------
    list[str]
        Columns from `columns` that exist in `df.columns`.
    """
    return [col for col in columns if col in df.columns]


def _render_table_with_csv_download(
    df,
    columns: list[str],
    download_label: str,
    file_name: str,
) -> None:
    """Render a dataframe restricted to available columns with a CSV download button.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to display and download.
    columns : list[str]
        Candidate columns to display (filtered to those present in `df`).
    download_label : str
        Label for the download button.
    file_name : str
        File name for the downloaded CSV.
    """
    available_cols = _filter_available_columns(df, columns)
    display_df = df[available_cols]

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
    )

    csv = display_df.to_csv(index=False)
    st.download_button(
        label=download_label,
        data=csv,
        file_name=file_name,
        mime="text/csv",
    )


def _render_outliers_data_table(
    outlier_df,
    selected_alias: str,
    survey_key: str | None,
    survey_date: str | None,
    enumerator: str | None,
    detection_method: str,
    clustering_col: str | None,
    review: GPSReview | None = None,
) -> None:
    """Render the outliers data table with download button.

    Parameters
    ----------
    outlier_df : pd.DataFrame
        DataFrame with Outlier boolean column.
    selected_alias : str
        Selected GPS configuration alias (used for download filename).
    survey_key : str | None
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    enumerator : str | None
        Enumerator column name.
    detection_method : str
        Detection method used.
    clustering_col : str | None
        Clustering column name (for cluster method).
    review : GPSReview | None
        If given, accepted outliers are hidden (unless "Show reviewed" is
        on) and each row has a Review button that opens the correction form.
    """
    with st.expander("View Outliers Data", expanded=review is not None):
        show_reviewed = review is not None and st.toggle(
            "Show reviewed",
            key=f"gps_show_reviewed_{selected_alias}",
            help="Also show outliers accepted as valid, highlighted green, "
            "with the reason.",
        )
        outliers_only = outliers_table(outlier_df, show_reviewed=show_reviewed)

        if outliers_only.empty:
            # Every outlier may have been accepted as valid.
            if outlier_df["Outlier"].any():
                st.success("No outliers left to review!")
            else:
                st.success("No outliers detected!")
            return

        display_cols = _identity_optional_fields(
            outliers_only, [survey_key, survey_date, enumerator]
        )
        display_cols.extend(["latitude", "longitude"])

        if detection_method == "Cluster by Column" and clustering_col:
            display_cols.extend(
                _collect_optional_fields(
                    outliers_only,
                    [
                        (clustering_col, clustering_col),
                        ("distance_from_centroid", "distance_from_centroid"),
                    ],
                )
            )

        if review is None:
            _render_table_with_csv_download(
                outliers_only,
                display_cols,
                "Download Outliers Data",
                f"gps_outliers_{selected_alias}.csv",
            )
            return

        display_cols.extend(c for c in REVIEW_COLUMNS if c in outliers_only.columns)
        _render_reviewable_outliers_table(
            outliers_only[_filter_available_columns(outliers_only, display_cols)],
            selected_alias,
            survey_key,
            review,
        )


# =============================================================================
# Correcting and Accepting GPS Outliers
# =============================================================================

# `queue_notice` scope of the confirmation shown after the post-save rerun.
_NOTICE_SCOPE = "gps_corrections"

# First column of the outliers table: a button that opens the correction dialog.
REVIEW_BUTTON_COL = "_review"
REVIEW_BUTTON_LABEL = ":material/edit_note: Review"

# Map colors of outlier, accepted and normal points.
_OUTLIER_COLOR = [255, 0, 0, 160]
_ACCEPTED_COLOR = [25, 135, 84, 200]
_NORMAL_COLOR = [0, 0, 255, 160]


@dataclass(frozen=True)
class GPSReview:
    """What the outliers table needs to correct or accept GPS outliers.

    Attributes
    ----------
    processor : CorrectionProcessor
        Saves the entries and reads the active acceptances.
    alias : str
        The survey dataset alias.
    data : pl.DataFrame
        The corrected survey data, for current values.
    columns : CoordinateColumns | None
        The selected GPS configuration's coordinate columns; None if it
        stores both in one column, so only observations can be removed.
    survey_id : str | None
        The Survey ID column, recorded with each entry.
    """

    processor: CorrectionProcessor
    alias: str
    data: pl.DataFrame
    columns: CoordinateColumns | None
    survey_id: str | None = None


def _mark_accepted_outliers(
    outlier_df: pd.DataFrame, survey_key: str, review: GPSReview
) -> pd.DataFrame:
    """Mark the outliers accepted for the selected configuration's columns."""
    if review.columns is None:
        accepted = {}
    else:
        acceptances = review.processor.get_active_acceptances(
            review.alias, GPS_CHECK_TYPE, survey_key
        )
        accepted = accepted_gps_keys(acceptances, review.columns)
    return mark_gps_reviewed(outlier_df, accepted, survey_key)


def _render_reviewable_outliers_table(
    table: pd.DataFrame,
    selected_alias: str,
    survey_key: str,
    review: GPSReview,
) -> None:
    """Render the outliers table with a Review button on each row.

    Clicking Review opens the correction form for that row in a dialog.
    """
    click_key = f"gps_outlier_review_click_{selected_alias}"
    button_col = REVIEW_BUTTON_COL
    while button_col in table.columns:
        button_col = f"_{button_col}"
    shown = pl.from_pandas(table).select(
        pl.lit(REVIEW_BUTTON_LABEL).alias(button_col), pl.all()
    )
    dataframe_kwargs: dict[str, Any] = {
        "width": "stretch",
        "hide_index": True,
        "column_config": {
            button_col: st.column_config.ButtonColumn(
                "",
                type="tertiary",
                pinned=True,
                key=click_key,
                help="Correct the coordinates or accept them as valid.",
            )
        },
    }
    if REVIEW_STATUS_COL in shown.columns:
        # "Show reviewed" is on: colour the accepted outliers green.
        styled_dataframe(row_styler(shown, highlight_reviewed_row), **dataframe_kwargs)
    else:
        st.dataframe(shown, **dataframe_kwargs)

    st.download_button(
        label="Download Outliers Data",
        data=table.to_csv(index=False),
        file_name=f"gps_outliers_{selected_alias}.csv",
        mime="text/csv",
    )

    # The click is only present during the rerun it triggers, so the dialog
    # opens once per click; widgets inside the dialog rerun just the dialog.
    click = st.session_state.get(click_key)
    rows = [click["row"]] if click else []
    selection = select_gps_outlier(table, rows, survey_key)
    if selection is not None:
        _gps_correction_dialog(survey_key, selection, review)


@st.dialog("Correct or accept GPS outlier", width="medium")
def _gps_correction_dialog(
    survey_key: str, selection: GPSSelection, review: GPSReview
) -> None:
    """Show the correction form for a GPS outlier in a dialog."""
    _render_gps_correction_form(survey_key, selection, review)


def _render_gps_correction_form(
    survey_key: str, selection: GPSSelection, review: GPSReview
) -> None:
    """Render the correction form for the selected GPS outlier.

    The form is prefilled with the KEY and its coordinates. Modifying or
    removing the coordinates saves one entry per coordinate column with a
    shared reason, all or none. A successful save reruns the page so the
    map, metrics and table reflect it.

    A KEY shared by rows with different coordinates can't be reviewed, since
    a correction would change every one of those rows.
    """
    data, columns = review.data, review.columns
    key_value = selection.key_value

    st.markdown(f"GPS outlier for KEY **{key_value}**")
    rows = data.filter(pl.col(survey_key) == key_value)
    if rows.is_empty():
        st.warning(f"KEY {key_value} is no longer in the data. Refresh the page.")
        return
    coordinate_cols = columns.as_tuple() if columns else ()
    if any(
        key_has_conflicting_values(data, survey_key, key_value, col)
        for col in coordinate_cols
    ):
        st.warning(
            f"KEY {key_value} is on more than one row, with different "
            "coordinates. Corrections and acceptances apply to every row with "
            "the KEY, so this outlier can't be reviewed here. Give each record "
            "a unique KEY in the source data first; the Duplicates check lists "
            "duplicated KEYs."
        )
        return

    current = {col: rows[0, col] for col in coordinate_cols}
    if columns is None:
        st.info(
            "This GPS configuration stores the coordinates in one column, so "
            "they can't be corrected or accepted here. You can remove the "
            "observation, or correct the column on the Correct Data page."
        )
    else:
        st.write(f"**{columns.latitude}:** {current[columns.latitude]}")
        st.write(f"**{columns.longitude}:** {current[columns.longitude]}")
    if selection.reviewed:
        st.info(
            "This outlier was accepted as valid. Remove the acceptance on the "
            "Correct Data page to flag it again."
        )

    # JSON keeps the parts distinct, and the columns keep forms for two GPS
    # configurations apart.
    namespace = json.dumps([GPS_CHECK_TYPE, str(key_value), *coordinate_cols])
    action = st.selectbox(
        label="Select Action",
        options=allowed_gps_actions(columns, reviewed=selection.reviewed),
        key=f"gps_correction_action_{namespace}",
    )

    new_latitude = new_longitude = validation_error = None
    if action == GPSAction.MODIFY_COORDINATES and columns is not None:
        lat_input, lon_input = st.columns(2)
        new_latitude = lat_input.text_input(
            f"New {columns.latitude}",
            key=f"gps_correction_new_lat_{namespace}",
            placeholder="Enter new latitude",
        )
        new_longitude = lon_input.text_input(
            f"New {columns.longitude}",
            key=f"gps_correction_new_lon_{namespace}",
            placeholder="Enter new longitude",
        )
        if new_latitude and new_longitude:
            validation_error = validate_coordinates(new_latitude, new_longitude)
            if validation_error:
                st.error(validation_error)
    elif action == GPSAction.REMOVE_COORDINATES and columns is not None:
        st.caption(
            f"Clears {columns.latitude} and {columns.longitude}. Accuracy and "
            "altitude are kept."
        )
    elif action == GPSAction.REMOVE_OBSERVATION:
        st.warning(
            f"This will remove the {rows.height} rows with KEY {key_value} "
            "from the dataset."
            if rows.height > 1
            else f"This will remove the row with KEY {key_value} from the dataset."
        )

    reason = st.text_input(
        label="Reason for Correction",
        key=f"gps_correction_reason_{namespace}",
        placeholder="Enter reason for correction",
    )

    apply_enabled = bool(reason and reason.strip()) and not validation_error
    if action == GPSAction.MODIFY_COORDINATES:
        apply_enabled = apply_enabled and bool(new_latitude and new_longitude)
    if not st.button(
        label="Apply",
        key=f"gps_correction_apply_{namespace}",
        width="stretch",
        disabled=not apply_enabled,
        type="primary",
    ):
        return

    survey_id_value = (
        get_current_value(data, survey_key, key_value, review.survey_id)
        if review.survey_id
        else None
    )
    entries = build_gps_entries(
        action,
        key_value,
        reason,
        columns=columns,
        current=current,
        new_latitude=new_latitude,
        new_longitude=new_longitude,
        survey_id_value=survey_id_value,
    )
    if not apply_correction_entries(
        review.processor, review.alias, survey_key, entries, source=GPS_CHECK_TYPE
    ):
        return

    # A full rerun closes the dialog and refreshes the map, metrics and table.
    queue_notice(
        _NOTICE_SCOPE,
        "toast",
        f"Saved {action} for KEY {key_value}. "
        "It is listed in the Correction Log on the Correct Data page.",
    )
    st.rerun()


def _show_saved_toast() -> None:
    """Show the confirmation queued by a save before the page reran."""
    if not show_queued_notices(_NOTICE_SCOPE):
        return
    # A markdown link in the toast would open a new browser session and lose
    # the selected project; a page link navigates within this session.
    corrections_page = st.session_state.get("st_corr_page")
    if corrections_page is not None:
        st.page_link(
            corrections_page,
            label="Open the Correction Log",
            icon=":material/cleaning_services:",
        )


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

    gp1, gp2, gp3 = st.columns([0.4, 0.3, 0.3])

    with gp1:
        _gps_settings, _selected_alias, parsed_data = _load_and_parse_gps_data(
            project_id, page_name_id, data
        )

    if parsed_data is None:
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
    filtered_data = _apply_category_filter(parsed_data, filter_by)

    if filtered_data is None or filtered_data.is_empty():
        st.warning("No data matches the selected filters.")
        return

    # Build map dataframe with tooltip columns
    map_pd, tooltip_fields = _build_map_dataframe(
        filtered_data, survey_key, survey_date, enumerator, team, color_by
    )

    # Render the map
    _render_scatterplot_map(
        map_pd,
        tooltip_fields,
        fill_color="color" if color_by else [255, 0, 0, 160],
    )

    st.caption(f"Displaying {len(map_pd):,} GPS points")


@st.fragment
def _render_gps_outliers_checks(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
    alias: str | None = None,
    survey_id: str | None = None,
) -> None:
    """Render GPS outliers detection and visualization.

    Allows users to:
    - Select GPS configuration by alias
    - Choose outlier detection method (auto or by column)
    - Configure detection parameters
    - View outliers on interactive map
    - Download outliers data
    - Correct or accept outliers (when `alias` is given)

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
    alias : str | None
        The survey dataset alias. If given, outliers can be corrected or
        accepted from the outliers table, and accepted ones are not counted.
    survey_id : str | None
        Survey ID column name, recorded with each correction.
    """
    st.subheader("GPS Outliers Detection")

    go1, go2, go3 = st.columns([0.4, 0.3, 0.3])

    with go1:
        gps_settings, selected_alias, parsed_data = _load_and_parse_gps_data(
            project_id, page_name_id, data, alias_select_key="outlier_gps_config"
        )

    if parsed_data is None:
        return

    df_pd = parsed_data.to_pandas()

    df_columns: ColumnByType = get_df_columns(parsed_data)
    string_columns = df_columns.categorical_columns

    with go2:
        detection_method = st.selectbox(
            label="Detection Method",
            options=[item.value for item in GPSOutlierMethod],
            key="outlier_detection_method",
            help="Choose how to detect outliers: automatic or based on a grouping column.",
        )

    # Run selected detection method
    clustering_col = None
    if detection_method == GPSOutlierMethod.auto_lof.value:
        outlier_df = _run_lof_detection(df_pd, len(df_pd), go3)
    else:
        outlier_df, clustering_col = _run_cluster_detection(df_pd, string_columns, go3)

    if outlier_df is None:
        return

    review = None
    if alias and survey_key and survey_key in outlier_df.columns:
        selected_config = gps_settings.filter(
            pl.col("alias") == selected_alias
        ).to_dicts()[0]
        review = GPSReview(
            processor=CorrectionProcessor(project_id),
            alias=alias,
            data=data,
            columns=coordinate_columns(selected_config),
            survey_id=survey_id,
        )
        outlier_df = _mark_accepted_outliers(outlier_df, survey_key, review)

    # Display summary statistics
    num_outliers = count_unreviewed_outliers(outlier_df)
    total_points = len(outlier_df)
    outlier_pct = (num_outliers / total_points * 100) if total_points > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total GPS Points", f"{total_points:,}")
    with col2:
        st.metric(
            "Outliers Detected",
            f"{num_outliers:,}",
            help="Outliers accepted as valid are not counted.",
        )
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

    _render_outliers_data_table(
        outlier_df,
        selected_alias,
        survey_key,
        survey_date,
        enumerator,
        detection_method,
        clustering_col,
        review,
    )


@st.fragment
def _load_comparison_aliases(
    project_id: str,
    page_name_id: str,
) -> list[str] | None:
    """Load GPS configuration aliases for comparison.

    Returns
    -------
    list[str] | None
        List of aliases if at least 2 exist, otherwise None (with UI messages shown).
    """
    gps_settings = _get_gps_column_settings(project_id, page_name_id)

    if gps_settings is None or gps_settings.is_empty():
        st.info(
            "No GPS configurations found. "
            "Please add at least two GPS column configurations in the section above."
        )
        return None

    aliases = gps_settings["alias"].to_list()

    if len(aliases) < 2:
        st.warning(
            "⚠ Need at least 2 GPS configurations to compare. "
            f"Currently have {len(aliases)} configuration(s). "
            "Please add more GPS column configurations above."
        )
        return None

    return aliases


def _render_comparison_selectors(
    aliases: list[str],
) -> tuple[str, str, int] | None:
    """Render GPS comparison selection UI widgets.

    Returns
    -------
    tuple[str, str, int] | None
        (gps_config_1, gps_config_2, distance_threshold) or None if selections invalid.
    """
    gc1, gc2, gc3 = st.columns([0.3, 0.3, 0.4])

    with gc1:
        gps_config_1 = st.selectbox(
            label="First GPS Configuration",
            options=aliases,
            key="comparison_gps_config_1",
            help="Select the first GPS configuration to compare.",
        )

    with gc2:
        remaining_aliases = [a for a in aliases if a != gps_config_1]
        gps_config_2 = st.selectbox(
            label="Second GPS Configuration",
            options=remaining_aliases,
            key="comparison_gps_config_2",
            help="Select the second GPS configuration to compare.",
        )

    if not gps_config_1 or not gps_config_2:
        return None

    with gc3:
        distance_threshold = st.number_input(
            label="Distance Threshold (meters)",
            min_value=1,
            max_value=100000,
            value=100,
            step=10,
            key="comparison_distance_threshold",
            help="Flag GPS points where the distance between the two configurations "
            "exceeds this threshold.",
        )

    return gps_config_1, gps_config_2, distance_threshold


def _merge_parsed_gps_data(
    parsed_data_1: pl.DataFrame,
    parsed_data_2: pl.DataFrame,
    survey_key: str,
) -> pl.DataFrame | None:
    """Merge two parsed GPS datasets on survey key and drop rows with nulls.

    Returns
    -------
    pl.DataFrame | None
        Merged DataFrame with non-null coordinates, or None if merge fails.
    """
    renamed_1 = parsed_data_1.rename({"latitude": "lat_1", "longitude": "lon_1"})
    renamed_2 = parsed_data_2.rename({"latitude": "lat_2", "longitude": "lon_2"})

    if not (
        survey_key
        and survey_key in renamed_1.columns
        and survey_key in renamed_2.columns
    ):
        st.error(
            "Survey key is required to match GPS coordinates "
            "between the two configurations."
        )
        return None

    merged = renamed_1.join(
        renamed_2.select([survey_key, "lat_2", "lon_2"]),
        on=survey_key,
        how="inner",
    )

    merged = merged.filter(
        pl.col("lat_1").is_not_null()
        & pl.col("lon_1").is_not_null()
        & pl.col("lat_2").is_not_null()
        & pl.col("lon_2").is_not_null()
    )

    if merged.is_empty():
        st.warning("No matching GPS coordinates found between the two configurations.")
        return None

    return merged


def _calculate_comparison_distances(
    comparison_data: pl.DataFrame,
) -> pd.DataFrame | None:
    """Calculate geodesic distances and return a pandas DataFrame.

    Returns
    -------
    pd.DataFrame | None
        DataFrame with ``distance_meters`` column, or None if calculation fails.
    """
    comparison_df = comparison_data.to_pandas()

    def _row_distance(row):
        try:
            return geodesic(
                (row["lat_1"], row["lon_1"]), (row["lat_2"], row["lon_2"])
            ).meters
        except Exception:
            return None

    comparison_df["distance_meters"] = comparison_df.apply(_row_distance, axis=1)
    comparison_df = comparison_df.dropna(subset=["distance_meters"])

    if comparison_df.empty:
        st.warning("Unable to calculate distances between GPS coordinates.")
        return None

    return comparison_df


def _display_comparison_summary(
    comparison_df: pd.DataFrame,
    distance_threshold: int,
) -> None:
    """Display summary statistics and threshold status message."""
    total_points = len(comparison_df)
    flagged_points = comparison_df["exceeds_threshold"].sum()
    flagged_pct = (flagged_points / total_points * 100) if total_points > 0 else 0
    avg_distance = comparison_df["distance_meters"].mean()
    max_distance = comparison_df["distance_meters"].max()

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
            f"⚠ {flagged_pct:.1f}% of GPS points exceed the "
            f"{distance_threshold}m threshold"
        )
    else:
        st.success(f"✓ All GPS points are within {distance_threshold}m of each other")


def _render_comparison_map(
    comparison_df: pd.DataFrame,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
) -> None:
    """Render the comparison scatterplot map."""
    st.subheader("Comparison Map")

    map_df = comparison_df.copy()
    map_df["lat"] = map_df["lat_1"]
    map_df["lon"] = map_df["lon_1"]
    map_df["status"] = map_df["exceeds_threshold"].map(
        {True: "Exceeds Threshold", False: "Within Threshold"}
    )

    tooltip_fields = _identity_optional_fields(
        map_df, [survey_key, survey_date, enumerator]
    )
    tooltip_fields.extend(["lat", "lon", "distance_meters", "status"])

    map_df["color"] = map_df["exceeds_threshold"].apply(
        lambda x: [255, 0, 0, 160] if x else [0, 255, 0, 160]
    )

    _render_scatterplot_map(map_df, tooltip_fields, fill_color="color")


def _render_comparison_details_table(
    comparison_df: pd.DataFrame,
    gps_config_1: str,
    gps_config_2: str,
    survey_key: str,
    survey_date: str | None,
    enumerator: str | None,
) -> None:
    """Render the expandable comparison details table with download button."""
    with st.expander("View Comparison Details", expanded=False):
        display_cols = _identity_optional_fields(
            comparison_df, [survey_key, survey_date, enumerator]
        )
        display_cols.extend(
            ["lat_1", "lon_1", "lat_2", "lon_2", "distance_meters", "exceeds_threshold"]
        )

        available_cols = _filter_available_columns(comparison_df, display_cols)

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
        display_df = display_df.sort_values("Distance (m)", ascending=False)

        _render_table_with_csv_download(
            display_df,
            list(display_df.columns),
            "Download Comparison Data",
            f"gps_comparison_{gps_config_1}_vs_{gps_config_2}.csv",
        )


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

    aliases = _load_comparison_aliases(project_id, page_name_id)
    if aliases is None:
        return

    selections = _render_comparison_selectors(aliases)
    if selections is None:
        return

    gps_config_1, gps_config_2, distance_threshold = selections

    gps_settings = _get_gps_column_settings(project_id, page_name_id)
    config_1 = gps_settings.filter(pl.col("alias") == gps_config_1).to_dicts()[0]
    config_2 = gps_settings.filter(pl.col("alias") == gps_config_2).to_dicts()[0]

    parsed_data_1 = _parse_gps_data(data, config_1)
    parsed_data_2 = _parse_gps_data(data, config_2)

    if not _has_parsed_coords(parsed_data_1):
        st.warning(f"Unable to parse GPS coordinates from '{gps_config_1}'.")
        return

    if not _has_parsed_coords(parsed_data_2):
        st.warning(f"Unable to parse GPS coordinates from '{gps_config_2}'.")
        return

    comparison_data = _merge_parsed_gps_data(parsed_data_1, parsed_data_2, survey_key)
    if comparison_data is None:
        return

    comparison_df = _calculate_comparison_distances(comparison_data)
    if comparison_df is None:
        return

    comparison_df["exceeds_threshold"] = (
        comparison_df["distance_meters"] > distance_threshold
    )

    _display_comparison_summary(comparison_df, distance_threshold)
    _render_comparison_map(comparison_df, survey_key, survey_date, enumerator)
    _render_comparison_details_table(
        comparison_df,
        gps_config_1,
        gps_config_2,
        survey_key,
        survey_date,
        enumerator,
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
    plot_df = plot_df.dropna(subset=[gps_lat_col, gps_lon_col])
    plot_df = plot_df.rename(columns={gps_lat_col: "lat", gps_lon_col: "lon"})

    # Build tooltip fields
    tooltip_fields = _identity_optional_fields(
        plot_df, [survey_id, submissiondate, enumerator]
    )
    tooltip_fields.extend(["lat", "lon"])
    if color_col and color_col in plot_df.columns:
        tooltip_fields.append(color_col)

    _render_scatterplot_map(plot_df, tooltip_fields, fill_color=[255, 0, 0, 160])


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

    Outliers are red and other points blue. Outliers accepted as valid
    (marked by `mark_gps_reviewed`) are green, labelled "Accepted".

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
    df = df.copy()
    df = df.rename(columns={gps_lat_col: "lat", gps_lon_col: "lon"})

    # Create outlier status column for coloring
    df["outlier_status"] = outlier_status(df, outlier_col)

    # Build tooltip fields
    tooltip_fields = _identity_optional_fields(
        df, [survey_id, submission_date, enumerator]
    )
    tooltip_fields.extend(["lat", "lon", "outlier_status"])
    if clustering_col and clustering_col in df.columns:
        tooltip_fields.append(clustering_col)

    # Color outliers red, accepted outliers green, normal points blue
    colors = {OUTLIER_STATUS: _OUTLIER_COLOR, ACCEPTED_STATUS: _ACCEPTED_COLOR}
    df["color"] = df["outlier_status"].apply(lambda x: colors.get(x, _NORMAL_COLOR))

    _render_scatterplot_map(df, tooltip_fields, fill_color="color", zoom=7)


def gpschecks_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
    alias: str | None = None,
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
    alias : str | None
        The survey dataset alias. If given, GPS outliers can be corrected
        or accepted from the outliers table.

    Returns
    -------
    None
    """
    st.title("GPS Checks Report")
    _show_saved_toast()

    if is_demo_project():
        demo_callout(
            "This tab visualises your GPS data and checks coordinate quality. "
            "It has three sections:\n\n"
            "- **GPS Coordinates Visualization**: Plot all survey GPS points on an "
            "interactive map, colour-coded by enumerator, team, or any categorical column.\n"
            "- **GPS Outliers Detection**: Flag coordinates that appear to be in the wrong "
            "location, using statistical (Auto-LOF) or group-based (Cluster by Column) "
            "methods.\n"
            "- **GPS Coordinates Comparison**: Compare coordinates from two different GPS "
            "configurations to identify discrepancies beyond a set distance threshold.\n\n"
            "Start by reviewing the :material/settings: **settings** panel, then configure "
            "your GPS columns below."
        )

    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns

    if data.is_empty():
        st.info(
            "No data available for the gps checks report. "
            "Please upload data to proceed."
        )
        return

    config_settings = GPSSettings(**config)

    _gpschecks_settings = gpschecks_report_settings(
        setting_file,
        config_settings,
        categorical_columns,
        datetime_columns,
    )

    st.subheader("GPS Columns Configuration")

    if is_demo_project():
        demo_callout(
            "Click **Add GPS Column Configuration** to tell DataSure which columns "
            "contain your GPS data. In the dialog that opens:\n\n"
            "1. Under **GPS Data Format**, select **Separate Columns**.\n"
            "2. Set **Latitude Column** to **household_latitude**.\n"
            "3. Set **Longitude Column** to **household_longitude**.\n"
            "4. Set **Accuracy Column** to **household_gps_accuracy**.\n"
            "5. Enter a short **Configuration Alias** such as **household_gps**.\n"
            "6. Click **Add GPS Configuration** to save.\n\n"
            "If your GPS data is stored as a single delimited column "
            "(e.g., '-1.20 36.77 0.0 15.8'), choose **Single Column** instead and "
            "select the delimiter and column."
        )

    all_columns = list(data.columns)
    _render_gps_column_actions(project_id, page_name_id, all_columns)

    st.write("---")

    mapbox_token = _gpschecks_settings.mapbox_custom_key
    pydeck.settings.mapbox_key = mapbox_token

    if is_demo_project() and not mapbox_token:
        demo_callout(
            "Map visualizations require a **Mapbox API token**. "
            "A free token is available from Mapbox — sign up on their website to get one. "
            "Once you have a token, open the :material/settings: **settings** panel, "
            "paste it under **Mapbox API Token Configuration**, and click "
            "**Save Mapbox Token**. The three map sections below will then load.",
            "warning",
        )

    if not mapbox_token:
        st.warning(
            "⚠ No Mapbox API key provided. "
            "Please add a Mapbox API token in the settings to enable map visualizations."
        )
        return

    # Render GPS coordinates visualization
    if is_demo_project():
        demo_callout(
            "Select a **GPS Configuration** from the dropdown to load your coordinates "
            "onto the map. Use **Color Points By** to colour-code points by a categorical "
            "column (e.g., **enum_name** to see each enumerator's coverage area). "
            "Use **Filter Points By** to show only a subset of points. "
            "Hover over any point to see the survey ID, date, enumerator, team, and "
            "coordinates."
        )

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
    if is_demo_project():
        demo_callout(
            "This section flags GPS points that appear to be in the wrong location. "
            "Two detection methods are available:\n\n"
            "- **Auto (LOF)**: Uses the Local Outlier Factor algorithm to flag points "
            "distant from their neighbours. Adjust **Number of Neighbors** and "
            "**Expected Outlier Proportion** to tune sensitivity.\n"
            "- **Cluster by Column**: Groups points by a categorical column and flags "
            "points far from their group's centroid. Try **state** as the clustering "
            "column to detect households recorded in the wrong state.\n\n"
            "Three metrics summarise the results: **Total GPS Points**, "
            "**Outliers Detected**, and **Outlier Percentage**. "
            "Flagged points appear red on the map. Expand **View Outliers Data** to "
            "download the flagged records."
        )

    _render_gps_outliers_checks(
        project_id,
        page_name_id,
        data,
        config_settings.survey_key,
        config_settings.survey_date,
        config_settings.enumerator,
        alias=alias,
        survey_id=config_settings.survey_id,
    )

    st.write("---")

    # Render GPS comparison checks
    if is_demo_project():
        demo_callout(
            "This section compares GPS coordinates from two different configurations "
            "and flags pairs where the distance between them exceeds a threshold. "
            "It is useful when you have GPS from both a main survey and a backcheck "
            "visit and want to verify the household was revisited at the same location.\n\n"
            "This section requires at least **two GPS configurations** added above. "
            "The demo only has one configuration, so you can skip this section."
        )

    _render_gps_comparison_checks(
        project_id,
        page_name_id,
        data,
        config_settings.survey_key,
        config_settings.survey_date,
        config_settings.enumerator,
    )

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select the **Enumerator Statistics** tab."
    )
