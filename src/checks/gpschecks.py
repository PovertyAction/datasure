import folium
import numpy as np
import streamlit as st
from folium.plugins import HeatMap
from sklearn.cluster import DBSCAN
from streamlit_folium import st_folium


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
            default_enumerator = st.session_state["config_pages"]["Enumerator"][
                page_num - 1
            ]
            default_enumerator_index = survey_cols.get_loc(default_enumerator)

            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_backcheck",
                index=default_enumerator_index,
            )

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
            ]
        ):
            st.info(
                "Please select all required options to generate the progress report"
            )
            return

    st.markdown("## Overview")

    if gps_lat_col and gps_lon_col:
        st.write(data[[gps_lat_col, gps_lon_col]].head())
        st.write("### GPS Data Summary")
        st.write(data[[gps_lat_col, gps_lon_col]].describe())

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
