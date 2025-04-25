import folium
import numpy as np
import streamlit as st
from branca.colormap import linear
from folium.plugins import HeatMap
from sklearn.cluster import DBSCAN
from streamlit_folium import st_folium


# plot gps coordinates on a map
# @st.cache_data
def plot_gps_coordinates(df, survey_key, gps_lat_col, gps_lon_col, color_col):
    """
    Plot GPS coordinates on a map, color-coded by a specified column.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe containing GPS data.
    survey_key : str
        The name of the survey key column.
    survey_id : str
        The name of the survey ID column.
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
    # Create a folium map centered at the mean latitude and longitude
    df = df[~df[gps_lat_col].isna()]
    map_center = [df[gps_lat_col].mean(), df[gps_lon_col].mean()]
    gps_map = folium.Map(location=map_center, zoom_start=10)

    # assign colors to the color column
    unique_values = df[color_col].unique()
    value_to_index = {val: i for i, val in enumerate(unique_values)}
    colormap = linear.viridis.scale(0, len(unique_values) - 1)
    color_map = {val: colormap(value_to_index[val]) for val in unique_values}
    df["color_value"] = df[color_col].map(color_map)

    feature_groups = {}
    for val in unique_values:
        feature_groups[val] = folium.FeatureGroup(name=f"{val}")

    for _, row in df.iterrows():
        marker = folium.CircleMarker(
            location=(row[gps_lat_col], row[gps_lon_col]),
            radius=5,
            color=row["color_value"],
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"""
                <b>{color_col}:</b> {row[color_col]}<br>
                <b>survey key:</b> {row[survey_key]}<br>
                <b>latitude:</b> {row[gps_lat_col]:.6f}<br>
                <b>longitude:</b> {row[gps_lon_col]:.6f}
                """,
                min_width=200,
                max_width=300,
            ),
        )

        feature_groups[row[color_col]].add_child(marker)

    for group in feature_groups.values():
        gps_map.add_child(group)

    folium.LayerControl(
        title=color_col,
        title_style={"font-size": "16px", "font-weight": "bold"},
        position="topright",
        collapsed=True,
        autoZIndex=True,
    ).add_to(gps_map)

    # Display the map in Streamlit
    st_folium(gps_map, height=500, use_container_width=True)


# outlier detection using clustering
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
    # Drop rows with missing latitude values
    df = df[df[gps_lat_col].notna()]

    # Perform clustering for each group in the clustering column
    df["Outlier"] = False
    for _group, group_data in df.groupby(clustering_col):
        coords = group_data[[gps_lat_col, gps_lon_col]].values
        if len(coords) < 5:
            continue  # Skip groups with insufficient data for clustering

        eps_meters = 10000  # desired distance in meters
        eps_degrees = eps_meters / 111320  # 1 degree ≈ 111.32 km at equator

        db = DBSCAN(eps=eps_degrees, min_samples=5).fit(coords)  # Adjust eps as needed
        group_data["Cluster"] = db.labels_

        # Calculate centroids for each cluster
        centroids = (
            group_data[group_data["Cluster"] != -1]
            .groupby("Cluster")[[gps_lat_col, gps_lon_col]]
            .mean()
        )

        # Flag outliers based on distance from cluster centroids
        for cluster, centroid in centroids.iterrows():
            cluster_points = group_data[group_data["Cluster"] == cluster]
            distances = np.linalg.norm(
                cluster_points[[gps_lat_col, gps_lon_col]].values - centroid.values,
                axis=1,
            )
            threshold = (
                distances.mean() + 2 * distances.std()
            )  # Adjust threshold as needed
            outliers = cluster_points[distances > threshold].index
            df.loc[outliers, "Outlier"] = True

        # Mark DBSCAN outliers (label -1) as outliers
        df.loc[group_data[group_data["Cluster"] == -1].index, "Outlier"] = True
    return df


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
    # Create a folium map centered at the mean latitude and longitude
    map_center = [df[gps_lat_col].mean(), df[gps_lon_col].mean()]
    cluster_map = folium.Map(location=map_center, zoom_start=10)

    # Add points to the map
    for _, row in df.iterrows():
        color = "red" if row[outlier_col] else "blue"
        folium.CircleMarker(
            location=(row[gps_lat_col], row[gps_lon_col]),
            radius=5,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"""
                <b>{"Submission Date"}:</b> {row[submission_date]}<br>
                <b>{"Enumerator"}:</b> {row[enumerator]}<br>
                <b>{"Survey ID"}:</b> {row[survey_id]}<br>
                <b>{"Cluster"}:</b> {row[clustering_col]}<br>
                <b>Outlier:</b> {row[outlier_col]}<br>
                """,
                min_width=200,
                max_width=300,
            ),
        ).add_to(cluster_map)

    # Display the map in Streamlit
    st_folium(cluster_map, height=500, use_container_width=True)


# define function for gps checks
def gpschecks_report(data, page_num) -> None:  # noqa: D417, RUF100
    """
    Visualize the distribution of gps points in the survey

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe to visualize.

    Returns
    -------
    None

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for GPS Checks")

        survey_cols = data.columns

        gps_col, enum_col = st.columns(spec=2, border=True)

        with gps_col:
            gps_column_exists = st.toggle("Data contain GPS column(s)", value=True)
            if gps_column_exists:
                lat_long_columns = st.toggle(
                    "GPS has latitude and longitude columns", value=True
                )
                if lat_long_columns:
                    gps_lat_col = st.selectbox("Select latitude column", survey_cols)
                    gps_lon_col = st.selectbox("Select longitude column", survey_cols)
                    gps_accuracy = st.selectbox(
                        "Select gps accuracy column", survey_cols
                    )
                else:
                    gps_column = st.selectbox("Select GPS column", survey_cols)
                    gps_lat_col = "latitude"
                    gps_lon_col = "longitude"
                    gps_altitude = "altitude"
                    gps_accuracy = "accuracy"
                    data[[gps_lat_col, gps_lon_col, gps_altitude, gps_accuracy]] = (
                        data[gps_column].str.split(",", expand=True).astype(float)
                    )

                # outlier detection method
                outlier_method = st.selectbox(
                    "Select Outlier Detection Method",
                    ["Distance Threshold", "DBSCAN Clustering", "Z-Score", "IQR"],
                )
                if outlier_method == "Distance Threshold":
                    threshold = st.number_input(
                        "Set Distance Threshold (meters)",
                        min_value=0,
                        max_value=100000,
                        value=1000,
                    )

        with enum_col:
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_date_index = survey_cols.get_loc(default_date)

            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_gpscheck",
                index=default_date_index,
            )

            default_survey_key = st.session_state["config_pages"]["Survey KEY"][
                page_num - 1
            ]
            default_survey_key_index = survey_cols.get_loc(default_survey_key)

            survey_key = st.selectbox(
                "Survey KEY",
                options=survey_cols,
                help="Column containing Survey KEY",
                key="surveykey_gpscheck",
                index=default_survey_key_index,
            )

            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_id_index = survey_cols.get_loc(default_survey_id)

            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="survey_id_gpscheck",
                index=default_survey_id_index,
            )

            default_enumerator = st.session_state["config_pages"]["Enumerator"][
                page_num - 1
            ]
            default_enumerator_index = survey_cols.get_loc(default_enumerator)

            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_gpscheck",
                index=default_enumerator_index,
            )
        st.write("")

        # save settings
        save_settings = st.button("Save settings", key="save_settings_gpscheck")  # noqa: F841

    # check if configuration is complete
    if not all(
        [
            gps_column_exists,
            lat_long_columns,
            gps_lat_col,
            gps_lon_col,
            outlier_method,
            threshold,
            enumerator,
            survey_key,
            survey_id,
        ]
    ):
        st.info("Please select all required options to generate the progress report")
        return

    if gps_lat_col and gps_lon_col:
        st.markdown("## Overview")

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
            value=f"{pct_non_missing_gps:.2f}%",
        )
        col4.metric(
            label="% flagged as potential outliers",
            value=f"{(0.2390):.2f}%",
        )
        st.write("")

        st.write("##### GPS Data Distribution")
        gcol1, gcol2 = st.columns(2)
        with gcol1:
            gps_color_col = st.selectbox(
                "Select column to color-code GPS points",
                survey_cols,
                index=default_enumerator_index,
            )
        # plot gps coordinates on a map
        plot_gps_coordinates(data, survey_key, gps_lat_col, gps_lon_col, gps_color_col)

        st.write("")

        # cluster detection
        st.write("##### Cluster Outlier Detection")

        col1, col2 = st.columns(2)
        with col1:
            clustering_col = st.selectbox(
                "Select a column to cluster GPS points",
                survey_cols,
                index=default_enumerator_index,
            )

        # Detect outliers using clustering
        clusters_df = detect_outliers_with_clusters(
            data, gps_lat_col, gps_lon_col, clustering_col
        )

        # Plot clusters on a map
        plot_clusters_on_map(
            clusters_df,
            enumerator,
            date,
            survey_id,
            gps_lat_col,
            gps_lon_col,
            clustering_col,
            "Outlier",
        )

        st.write("")

        st.write("### Heatmap of GPS Points")
        m = folium.Map(
            location=[data[gps_lat_col].mean(), data[gps_lon_col].mean()], zoom_start=10
        )
        HeatMap(data[[gps_lat_col, gps_lon_col]].dropna().values.tolist()).add_to(m)
        st_folium(m, width=700, height=500)

        st.write("### Outlier Detection")
        if outlier_method == "Distance Threshold":
            # Distance threshold-based outlier detection
            coords = data[[gps_lat_col, gps_lon_col]].dropna().values
            center = np.mean(coords, axis=0)
            distances = np.linalg.norm(coords - center, axis=1)
            outliers = data.iloc[np.where(distances > threshold)]

            st.write(f"Outliers detected using threshold: {threshold} meters")
            st.write(outliers[[gps_lat_col, gps_lon_col]])

        elif outlier_method == "DBSCAN Clustering":
            # DBSCAN clustering-based outlier detection
            coords = data[[gps_lat_col, gps_lon_col]].dropna().values
            db = DBSCAN(eps=threshold / 111320, min_samples=5).fit(
                coords
            )  # Convert meters to degrees
            labels = db.labels_

            data["Cluster"] = labels
            outliers = data[data["Cluster"] == -1]

            st.write(
                f"Number of clusters found: {len(set(labels)) - (1 if -1 in labels else 0)}"
            )
            st.write(f"Number of outliers detected: {len(outliers)}")
            st.write(outliers[[gps_lat_col, gps_lon_col]])

            # Visualize clusters
            cluster_map = folium.Map(
                location=[data[gps_lat_col].mean(), data[gps_lon_col].mean()],
                zoom_start=10,
            )
            for _idx, row in data.iterrows():
                color = "red" if row["Cluster"] == -1 else "blue"
                folium.CircleMarker(
                    location=(row[gps_lat_col], row[gps_lon_col]),
                    radius=3,
                    color=color,
                    fill=True,
                    fill_opacity=0.6,
                ).add_to(cluster_map)
            st_folium(cluster_map, width=700, height=500)

        elif outlier_method == "Z-Score":
            # Z-Score-based outlier detection
            coords = data[[gps_lat_col, gps_lon_col]].dropna()
            z_scores = np.abs((coords - coords.mean()) / coords.std())
            outliers = data[(z_scores > 3).any(axis=1)]

            st.write("Outliers detected using Z-Score method")
            st.write(outliers[[gps_lat_col, gps_lon_col]])

        elif outlier_method == "IQR":
            # IQR-based outlier detection
            coords = data[[gps_lat_col, gps_lon_col]].dropna()
            Q1 = coords.quantile(0.25)
            Q3 = coords.quantile(0.75)
            IQR = Q3 - Q1
            outliers = data[
                ((coords < (Q1 - 1.5 * IQR)) | (coords > (Q3 + 1.5 * IQR))).any(axis=1)
            ]

            st.write("Outliers detected using IQR method")
            st.write(outliers[[gps_lat_col, gps_lon_col]])
