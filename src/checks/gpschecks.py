import os

import matplotlib as mpl
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st
from geopy.distance import geodesic
from sklearn.neighbors import LocalOutlierFactor

from src.utils import load_check_settings, save_check_settings


@st.cache_data
def load_default_settings(setting_file: str, page_num: int) -> tuple:
    """
    Load the default settings for the summary report.

    Parameters
    ----------
    setting_file : str
            The settings file to load.

    page_num : int
            The page number of the report.

    Returns
    -------
    tuple
            A tuple containing the default settings for the summary report.

    """
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "gpscheck")
        if default_settings:
            default_date = default_settings.get("date")
            default_enumerator = default_settings.get("enumerator")
            default_survey_key = default_settings.get("survey_key")
            default_survey_id = default_settings.get("survey_id")
            default_gps_column_exists = default_settings.get("gps_column_exists")
            default_lat_lon_exist = default_settings.get("lat_lon_columns_exist")
            default_gps_column = default_settings.get("gps_column")
            default_gps_lat_col = default_settings.get("gps_lat_col")
            default_gps_lon_col = default_settings.get("gps_lon_col")
            default_gps_accuracy = default_settings.get("gps_accuracy")
        else:
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_enumerator = st.session_state["config_pages"]["Enumerator"][
                page_num - 1
            ]
            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_key = st.session_state["config_pages"]["Survey KEY"][
                page_num - 1
            ]
            default_gps_column_exists = False
            default_lat_lon_exist = False
            default_gps_lat_col = None
            default_gps_lon_col = None
            default_gps_accuracy = None
            default_gps_column = None
    else:
        default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
        default_enumerator = st.session_state["config_pages"]["Enumerator"][
            page_num - 1
        ]
        default_survey_id = st.session_state["config_pages"]["Survey ID"][page_num - 1]
        default_survey_key = st.session_state["config_pages"]["Survey KEY"][
            page_num - 1
        ]
        default_gps_column_exists = False
        default_lat_lon_exist = False
        default_gps_lat_col = None
        default_gps_lon_col = None
        default_gps_accuracy = None
        default_gps_column = None

    return (
        default_date,
        default_enumerator,
        default_survey_id,
        default_survey_key,
        default_gps_column_exists,
        default_lat_lon_exist,
        default_gps_lat_col,
        default_gps_lon_col,
        default_gps_accuracy,
        default_gps_column,
    )


#  gps check settings
def gps_check_settings(data: pd.DataFrame, setting_file: str, page_num) -> tuple:
    """
    Load and save settings for the GPS checks page.

    Parameters
    ----------
    data : pd.DataFrame
        survey data file.
    settings_file : str
        The path to the settings file.
    page_num : int
        The page number for the current check.

    Returns
    -------
    tuple
        A tuple containing updated settings.

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for GPS Checks Report")

        survey_cols = data.columns

        # load default settings
        (
            default_date,
            default_enumerator,
            default_survey_id,
            default_survey_key,
            default_gps_column_exists,
            default_lat_lon_exist,
            default_gps_lat_col,
            default_gps_lon_col,
            default_gps_accuracy,
            default_gps_column,
        ) = load_default_settings(setting_file, page_num)

        enum_col, gps_col = st.columns(spec=2, border=True)

        with gps_col:
            gps_column_exists = st.toggle(
                "Data contain GPS column(s)",
                value=default_gps_column_exists,
                key="gps_column_exists",
            )
            if gps_column_exists:
                lat_lon_columns_exist = st.toggle(
                    "GPS has latitude and longitude columns",
                    value=default_lat_lon_exist,
                    key="lat_long_columns_exist",
                )
                if lat_lon_columns_exist:
                    default_gps_lat_col_index = (
                        survey_cols.get_loc(default_gps_lat_col)
                        if default_gps_lat_col
                        else None
                    )
                    default_gps_lon_col_index = (
                        survey_cols.get_loc(default_gps_lon_col)
                        if default_gps_lon_col
                        else None
                    )
                    default_gps_accuracy_index = (
                        survey_cols.get_loc(default_gps_accuracy)
                        if default_gps_accuracy
                        else None
                    )
                    gps_lat_col = st.selectbox(
                        "Select latitude column",
                        survey_cols,
                        default_gps_lat_col_index,
                        key="gps_lat_col",
                    )
                    gps_lon_col = st.selectbox(
                        "Select longitude column",
                        survey_cols,
                        default_gps_lon_col_index,
                        key="gps_lon_col",
                    )
                    gps_accuracy = st.selectbox(
                        "Select gps accuracy column",
                        survey_cols,
                        default_gps_accuracy_index,
                        key="gps_accuracy_col",
                    )
                else:
                    default_gps_column_index = (
                        survey_cols.get_loc(default_gps_column)
                        if default_gps_column
                        else None
                    )
                    gps_column = st.selectbox(
                        "Select GPS column",
                        survey_cols,
                        index=default_gps_column_index,
                        key="gps_column",
                    )

                    if gps_column:
                        # Try to detect delimiter: comma, tab, or space
                        sample_val = data[gps_column].dropna().astype(str).iloc[0]
                        if "\t" in sample_val:
                            delimiter = "\t"
                        elif "," in sample_val:
                            delimiter = ","
                        elif " " in sample_val:
                            delimiter = " "
                        else:
                            delimiter = ","  # fallback

                        # Split the GPS column into parts
                        gps_split = (
                            data[gps_column]
                            .astype(str)
                            .str.split(delimiter, expand=True)
                        )

                        # Assign columns based on the number of split parts
                        if gps_split.shape[1] == 2:
                            gps_lat_col = "latitude"
                            gps_lon_col = "longitude"
                            data[[gps_lat_col, gps_lon_col]] = gps_split.iloc[
                                :, :2
                            ].astype(float)
                            gps_altitude = None
                            gps_accuracy = None
                        elif gps_split.shape[1] == 3:
                            gps_lat_col = "latitude"
                            gps_lon_col = "longitude"
                            gps_accuracy = "accuracy"
                            data[[gps_lat_col, gps_lon_col, gps_accuracy]] = (
                                gps_split.iloc[:, :3].astype(float)
                            )
                            gps_altitude = None
                        elif gps_split.shape[1] >= 4:
                            # remove any non-numeric values from split columns
                            gps_split = gps_split.apply(
                                lambda x: pd.to_numeric(x, errors="coerce")
                            )
                            gps_lat_col = "latitude"
                            gps_lon_col = "longitude"
                            gps_altitude = "altitude"
                            gps_accuracy = "accuracy"
                            data[
                                [gps_lat_col, gps_lon_col, gps_altitude, gps_accuracy]
                            ] = gps_split.iloc[:, :4].astype(float)
                        else:
                            gps_lat_col = None
                            gps_lon_col = None
                            gps_altitude = None
                            gps_accuracy = None
                    else:
                        gps_lat_col = None
                        gps_lon_col = None
                        gps_accuracy = None
            else:
                lat_lon_columns_exist = default_lat_lon_exist
                gps_column = default_gps_column
                gps_lat_col = default_gps_lat_col
                gps_lon_col = default_gps_lon_col
                gps_accuracy = default_gps_accuracy

        with enum_col:
            default_date_index = survey_cols.get_loc(default_date)

            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_gpscheck",
                index=default_date_index,
            )

            default_survey_key_index = survey_cols.get_loc(default_survey_key)

            survey_key = st.selectbox(
                "Survey KEY",
                options=survey_cols,
                help="Column containing Survey KEY",
                key="survey_key_gpscheck",
                index=default_survey_key_index,
            )

            default_survey_id_index = survey_cols.get_loc(default_survey_id)

            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="survey_id_gpscheck",
                index=default_survey_id_index,
            )

            default_enumerator_index = survey_cols.get_loc(default_enumerator)

            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_gpscheck",
                index=default_enumerator_index,
            )
        st.write("")

        # save settings to file
        gps_report_settings = {
            "date": date,
            "enumerator": enumerator,
            "survey_key": survey_key,
            "survey_id": survey_id,
            "gps_column_exists": gps_column_exists,
            "lat_lon_columns_exist": lat_lon_columns_exist
            if gps_column_exists
            else False,
            "gps_lat_col": gps_lat_col if gps_column_exists else None,
            "gps_lon_col": gps_lon_col if gps_column_exists else None,
            "gps_accuracy": gps_accuracy if gps_column_exists else None,
            "gps_column": gps_column if not lat_lon_columns_exist else None,
        }

        save_gpscheck_settings = st.button(
            label="Save settings", key="save_gpscheck_settings"
        )

        if save_gpscheck_settings:
            save_check_settings(setting_file, "gpscheck", gps_report_settings)
            st.success("Settings saved successfully!")

    return (
        gps_column_exists,
        gps_lat_col,
        gps_lon_col,
        gps_accuracy,
        date,
        survey_key,
        survey_id,
        enumerator,
    )


# plot gps coordinates on a map
def plot_gps_coordinates(
    df, enumerator, submissiondate, survey_id, gps_lat_col, gps_lon_col, color_col
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
    # Drop rows with missing coordinates
    df = df.dropna(subset=[gps_lat_col, gps_lon_col])

    # Assign a color to each unique value in color_col
    unique_values = df[color_col].unique()
    # generate a color palette based on the number of unique values
    num_colors = len(unique_values)
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
    ]
    color_map = {
        val: color_palette[i % len(color_palette)]
        for i, val in enumerate(unique_values)
    }
    df["color_value"] = df[color_col].map(color_map)

    # Prepare data for pydeck
    map_data = []
    for _, row in df.iterrows():
        map_data.append(
            {
                "longitude": float(row[gps_lon_col]),
                "latitude": float(row[gps_lat_col]),
                "color": row["color_value"],
                "tooltip": (
                    f"Submission Date: {row[submissiondate]}\n"
                    f"Enumerator: {row[enumerator]}\n"
                    f"Survey ID: {row[survey_id]}\n"
                    f"{color_col}: {row[color_col]}\n"
                    f"Latitude: {row[gps_lat_col]:.6f}\n"
                    f"Longitude: {row[gps_lon_col]:.6f}"
                ),
            }
        )

    # Calculate map center
    center_lat = df[gps_lat_col].mean()
    center_lon = df[gps_lon_col].mean()

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
    # Drop rows with missing latitude values or longitude values
    df = df.dropna(subset=[gps_lat_col, gps_lon_col])
    # df = df[df[gps_lat_col].notna()]

    # Group data by clustering_col and process each group separately
    grouped_df = df.groupby(clustering_col)

    # Calculate centroids for each group
    centroids = grouped_df[[gps_lat_col, gps_lon_col]].mean()

    # Calculate distances from centroids using geopy
    def calculate_distance(row):
        centroid = centroids.loc[row[clustering_col]]
        return geodesic(
            (row[gps_lat_col], row[gps_lon_col]),
            (centroid[gps_lat_col], centroid[gps_lon_col]),
        ).meters

    df["distance_from_centroid"] = df.apply(calculate_distance, axis=1)

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

    df = grouped_df.apply(flag_outliers).reset_index(drop=True)

    return df


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
    enumerator,
    submission_date,
    survey_id,
    gps_lat_col,
    gps_lon_col,
    clustering_col,
    outlier_col,
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
            "tooltip": (
                f"Enumerator: {row[enumerator]}\n"
                f"Date: {row[submission_date]}\n"
                f"Survey ID: {row[survey_id]}\n"
                f"Cluster: {row[clustering_col] if clustering_col else 'No Cluster'}\n"
                f"Outlier: {row[outlier_col]}\n"
            ),
        }
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


# gps checks report
def gpschecks_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:
    """
    Visualize distribution of GPS data in the survey

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe to visualize.
    setting_file : str
        The path to the settings file.
    page_num : int
        The page number for the current check.

    Returns
    -------
    None

    """
    # load settings
    (
        gps_column_exists,
        gps_lat_col,
        gps_lon_col,
        gps_accuracy,
        date,
        survey_key,
        survey_id,
        enumerator,
    ) = gps_check_settings(data, setting_file, page_num)
    if gps_column_exists:
        if gps_lat_col is None or gps_lon_col is None:
            st.warning("Select a GPS column or latitude and longitude columns")
            return
        if pd.api.types.is_numeric_dtype(
            data[gps_lat_col]
        ) and pd.api.types.is_numeric_dtype(data[gps_lon_col]):
            st.markdown("## Overview")

            survey_cols = data.columns
            default_enumerator_index = survey_cols.get_loc(enumerator)

            col1, col2, col3, col4 = st.columns(4)

            # calculate metrics
            num_total_surveys = data.shape[0]
            num_missing_gps = data[gps_lat_col].isnull().sum()
            non_missing_gps = num_total_surveys - num_missing_gps
            pct_non_missing_gps = (non_missing_gps / num_total_surveys) * 100

            col1.metric(
                label="Number of observations",
                value=num_total_surveys,
            )
            col2.metric(
                label="Non-missing GPS data",
                value=non_missing_gps,
            )
            col3.metric(
                label="% of non-missing GPS data",
                value=f"{pct_non_missing_gps:.1f}%",
            )
            try:
                col4.metric(
                    "% flagged as potential outliers",
                    f"{st.session_state.gps_outlier_rate:.1f}%",
                )
            except:
                col4.metric(
                    label="% flagged as potential outliers",
                    value="n/a",
                )
            st.write("")

            st.write("##### GPS Data Distribution")
            st.write("")

            gcol1, gcol2 = st.columns(spec=[0.25, 0.75], gap="medium")

            with gcol1:
                gps_color_col = st.selectbox(
                    "Select column to color-code GPS points",
                    survey_cols,
                    index=default_enumerator_index,
                    key="gps_color_col",
                    help="Column to color-code GPS points",
                )
                dist_map_filter_col = st.multiselect(
                    label="Select values to display on the map",
                    options=data[gps_color_col].unique(),
                    default=None,
                    key="dist_map_filter_col",
                    help="Column to filter values on the map",
                )
                if dist_map_filter_col:
                    dist_map_data_df = data[
                        data[gps_color_col].isin(dist_map_filter_col)
                    ]
                else:
                    dist_map_data_df = data

            with gcol2:
                st.write("GPS points distribution, colored by the selected column.")

                # plot gps coordinates on map
                plot_gps_coordinates(
                    dist_map_data_df,
                    enumerator,
                    date,
                    survey_id,
                    gps_lat_col,
                    gps_lon_col,
                    gps_color_col,
                )

            st.write("")

            # cluster detection
            st.write("##### GPS Outliers")
            st.write("")

            col1, col2 = st.columns(spec=[0.25, 0.75], gap="medium")
            with col1:
                outlier_detection_method = st.selectbox(
                    "Select a gps outlier detection method",
                    ["Automatic", "Manual"],
                    index=0,
                )
                if outlier_detection_method == "Manual":
                    clustering_col = st.selectbox(
                        "Select a column to cluster GPS points",
                        survey_cols,
                        index=default_enumerator_index,
                        key="clustering_col",
                        help="Column to cluster GPS points",
                    )

                    # Detect outliers using clustering
                    flag_outliers_df = detect_outliers_with_clusters(
                        data, gps_lat_col, gps_lon_col, clustering_col
                    )

                    outliers_filter_col = st.multiselect(
                        label="Select values to display on the map",
                        options=data[clustering_col].unique(),
                        default=None,
                        key="outliers_filter_col",
                        help="Column to filter values on the map",
                    )
                    if outliers_filter_col:
                        flag_outliers_df = flag_outliers_df[
                            flag_outliers_df[clustering_col].isin(outliers_filter_col)
                        ]
                else:
                    clustering_col = (
                        None  # no clustering column needed for automatic detection
                    )
                    flag_outliers_df = detect_outliers_with_lof(
                        data,
                        gps_lat_col,
                        gps_lon_col,
                        n_neighbors=5,
                        contamination="auto",
                    )

                    auto_outliers_filter_col = st.selectbox(
                        label="Select a column to filter values on the map",
                        options=survey_cols,
                        index=None,
                        key="auto_outliers_filter_col",
                        help="Column to filter values on the map",
                    )
                    if auto_outliers_filter_col:
                        # Filter values to display on the map
                        auto_outliers_filter_vals = st.multiselect(
                            label="Select values to display on the map",
                            options=data[auto_outliers_filter_col].unique(),
                            default=None,
                            key="auto_outliers_filter_vals",
                            help="Values to display on the map",
                        )

                        if auto_outliers_filter_vals:
                            flag_outliers_df = flag_outliers_df[
                                flag_outliers_df[auto_outliers_filter_col].isin(
                                    auto_outliers_filter_vals
                                )
                            ]

            with col2:
                st.write(
                    "The map below shows GPS data distribution, colored by the outlier check outcome. Red points are flagged as outliers."
                )
                # plot outliers map
                plot_clusters_on_map(
                    flag_outliers_df,
                    enumerator,
                    date,
                    survey_id,
                    gps_lat_col,
                    gps_lon_col,
                    clustering_col,
                    "Outlier",
                )

            st.write("")

            gps_outliers_df = flag_outliers_df[flag_outliers_df["Outlier"]].reset_index(
                drop=True
            )

            if gps_outliers_df.shape[0] > 0:
                outliers_df_cols = st.multiselect(
                    label="Select a list of columns to display",
                    options=gps_outliers_df.columns,
                    default=[survey_key, enumerator, gps_lat_col, gps_lon_col],
                    help="Columns to display in the table",
                )

                st.write("Below is a list of potential GPS outliers:")

                st.dataframe(
                    gps_outliers_df[outliers_df_cols], use_container_width=True
                )

                st.session_state.gps_outlier_rate = (
                    gps_outliers_df.shape[0] / flag_outliers_df.shape[0]
                ) * 100
            else:
                st.info("No outliers detected")

            st.write("")

            st.write("##### GPS Accuracy Statistics")
            if gps_accuracy:
                cl1, cl2 = st.columns(2)
                with cl1:
                    accuracy_cluster_col = st.selectbox(
                        "Select a column to summarize GPS points by:",
                        survey_cols,
                        index=default_enumerator_index,
                    )
                with cl2:
                    accuracy_stats_list = st.multiselect(
                        label="Select statistics to display",
                        options=[
                            "min",
                            "median",
                            "mean",
                            "max",
                            "std",
                            "25th percentile",
                            "75th percentile",
                            "95th percentile",
                        ],
                        default=[
                            "min",
                            "mean",
                            "max",
                        ],
                    )
                gps_accuracy_statistics = calculate_gps_accuracy_statistics(
                    data, gps_accuracy, accuracy_cluster_col, accuracy_stats_list
                )
                st.dataframe(gps_accuracy_statistics, use_container_width=True)
                st.write("")
            else:
                st.warning(
                    "No GPS accuracy column selected. Please select a GPS accuracy column to display statistics."
                )
        else:
            st.error("Please select valid GPS columns")
            return
