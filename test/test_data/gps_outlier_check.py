# load modules

import uuid

import folium
import numpy as np
import pandas as pd
import streamlit as st
from geopy.distance import geodesic
from sklearn.cluster import KMeans
from streamlit_folium import st_folium


# generate clusters if enumeration area/community is missing
def create_enumeration_clusters(gps_data, n_clusters):
    """Create clusters for the given GPS data using KMeans clustering.

    Parameters
    ----------
    gps_data : pd.DataFrame
        DataFrame containing GPS data with 'latitude' and 'longitude' columns.
    n_clusters : int
        Number of clusters to create.

    Returns
    -------
    gps_data: a dataframe with gps clusters.

    """
    coords = gps_data[["latitude", "longitude"]].values
    kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(coords)
    gps_data["cluster"] = kmeans.labels_

    return gps_data


# generate random gps data
def generate_random_gps_data(num_gps_points, ea_latitude, ea_longitude, num_clusters):
    """Generate random GPS data points within a specified area and create clusters.

    Parameters
    ----------
    num_gps_points : int
        Number of GPS points to generate.
    ea_latitude : float
        Latitude of the enumeration area.
    ea_longitude : float
        Longitude of the enumeration area.
    num_clusters : int
        Number of clusters to create.

    Returns
    -------
    gps_clusters_df : pd.DataFrame
        DataFrame containing generated GPS data with clusters.

    """
    unique_identifiers = []
    enum_list = []
    for _ in range(num_gps_points):
        unique_identifiers.append(str(uuid.uuid4()))
        enum_list.append(
            np.random.randint(1, num_gps_points / 25)
        )  # 1 enumerator for every 25 uuids

    min_lat = int(ea_latitude) - 0.3
    max_lat = int(ea_latitude) + 1.4
    min_lon = int(ea_longitude) - 1
    max_lon = int(ea_longitude) + 1
    lat_vals = [
        round(x, 6) for x in np.random.uniform(min_lat, max_lat, num_gps_points)
    ]
    lon_vals = [
        round(x, 6) for x in np.random.uniform(min_lon, max_lon, num_gps_points)
    ]
    gps_data = pd.DataFrame(
        {
            "key": unique_identifiers,
            "enum": enum_list,
            "latitude": lat_vals,
            "longitude": lon_vals,
        }
    )
    # create clusters
    gps_clusters_df = create_enumeration_clusters(
        gps_data=gps_data, n_clusters=num_clusters
    )

    return gps_clusters_df


# create a map centered at the provided gps data
def create_gps_distribution_map(df, ea_column, latitude, longitude, colors_list):
    """Create a map showing the distribution of GPS points.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing GPS data.
    ea_column : str
        Column name for enumeration area.
    latitude : float
        Latitude of the enumeration area.
    longitude : float
        Longitude of the enumeration area.
    colors_list : list
        List of colors for the markers.

    Returns
    -------
    folium.Map
        Folium map with GPS points.

    """
    gps_map = folium.Map(
        location=[latitude, longitude],
        width="80%",
        height="80%",
        left="2%",
        zoom_start=8,
    )
    # add gps markers
    for _index, row in df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=1,
            color=colors_list[row[ea_column] % len(colors_list)],
        ).add_to(gps_map)

    return gps_map


# calculate gps distances from cluster/EA central points
def flag_gps_distance_outliers(df, ea_column, method):
    """Calculate distances of GPS points from cluster centers and flag outliers.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing GPS data.
    ea_column : str
        Column name for enumeration area.
    method : str
        Method for detecting outliers: IQR / SD

    Returns
    -------
    pd.DataFrame
        DataFrame with distances from cluster centers and outlier flags.

    """
    cluster_centers = df.groupby(ea_column).agg(
        {"latitude": "mean", "longitude": "mean"}
    )
    cluster_centers.reset_index(inplace=True)
    cluster_centers.rename(
        columns={"latitude": "center_latitude", "longitude": "center_longitude"},
        inplace=True,
    )

    df = pd.merge(df, cluster_centers, on=ea_column, how="left")
    df["distance_from_center"] = df.apply(
        lambda row: geodesic(
            (row["latitude"], row["longitude"]),
            (row["center_latitude"], row["center_longitude"]),
        ).km,
        axis=1,
    )
    if method == "SD":
        mean_distance = df["distance_from_center"].mean()
        std_distance = df["distance_from_center"].std()
        df["is_outlier"] = (
            df["distance_from_center"] < (mean_distance - 2 * std_distance)
        ) | (df["distance_from_center"] > (mean_distance + 2 * std_distance))
        df["sd_fence"] = (
            "["
            + str(round(mean_distance - 2 * std_distance, 2))
            + ", "
            + str(round(mean_distance + 2 * std_distance, 2))
            + "]"
        )
    elif method == "IQR":
        Q1 = df["distance_from_center"].quantile(0.25)
        Q3 = df["distance_from_center"].quantile(0.75)
        IQR = Q3 - Q1
        df["is_outlier"] = (df["distance_from_center"] < (Q1 - 1.5 * IQR)) | (
            df["distance_from_center"] > (Q3 + 1.5 * IQR)
        )
        df["iqr_fence"] = (
            "["
            + str(round(Q1 - 1.5 * IQR, 2))
            + ", "
            + str(round(Q3 + 1.5 * IQR, 2))
            + "]"
        )

    return df


# flag outliers using intra-distances by enumeration area/enumerator
def flag_too_clustered_gps_points(df, ea_column, min_distance_threshold):
    """Flag GPS points that are too clustered based on a minimum distance threshold.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing GPS data.
    ea_column : str
        Column name for enumeration area.
    min_distance_threshold : float
        Minimum distance threshold in kilometers.

    Returns
    -------
    pd.DataFrame
        DataFrame with a flag for too clustered points.

    """

    def calculate_min_distance(row, group):
        distances = group.apply(
            lambda x: geodesic(
                (row["latitude"], row["longitude"]), (x["latitude"], x["longitude"])
            ).km,
            axis=1,
        )
        distances = distances[distances > 0]  # Exclude zero distance (self-distance)
        return distances.min() if not distances.empty else np.nan

    df["min_distance"] = (
        df.groupby(ea_column)
        .apply(
            lambda group: group.apply(
                lambda row: calculate_min_distance(row, group), axis=1
            )
        )
        .reset_index(level=0, drop=True)
    )
    df["is_too_clustered"] = df["min_distance"] < min_distance_threshold

    df["gps_is_outlier"] = np.where(
        (df["is_outlier"] == True) | (df["is_too_clustered"] == True),  # noqa: E712
        "Yes",
        "No",
    )

    return df


# plot outliers
def plot_gps_distance_outliers(df, latitude, longitude):
    """Plot GPS distance outliers on a map.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing GPS data with outlier flags.
    latitude : float
        Latitude of the map center.
    longitude : float
        Longitude of the map center.

    Returns
    -------
    folium.Map
        Folium map with GPS points marked as outliers or non-outliers.

    """
    outlier_gps_vals_df = df[df["gps_is_outlier"] == "Yes"]
    non_outlier_gps_vals_df = df[df["gps_is_outlier"] == "No"]

    # plot values
    outliers_map = folium.Map(
        location=[latitude, longitude], height="80%", width="80%", zoom_start=8
    )

    for _index, row in non_outlier_gps_vals_df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]], radius=1.5, color="darkgreen"
        ).add_to(outliers_map)
    for _index, row in outlier_gps_vals_df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]], radius=1.5, color="red"
        ).add_to(outliers_map)

    return outliers_map


# load data
with st.sidebar:
    gps_data_available = st.selectbox("Is GPS data available?", ["No", "Yes"])

    # define enumeration area / region to sample gps points
    if gps_data_available == "Yes":
        file_name = "data/gps_test_data.csv"
        gps_data = pd.read_csv(file_name)
        gps_data = gps_data[gps_data["latitude"].isna() == False].reset_index(drop=True)  # noqa: E712
        sample_df = gps_data.sample(1)
        ea_latitude = sample_df["latitude"].values[0]
        ea_longitude = sample_df["longitude"].values[0]
        ea_column = st.selectbox(
            "Select the enumeration area or column to classify your data:",
            [c for c in gps_data.columns],
        )
        len_ea_column_vals = len(gps_data[ea_column].unique())
        cluster_mapping = {
            val: idx for idx, val in enumerate(gps_data[ea_column].unique())
        }
        gps_data["cluster"] = gps_data[ea_column].map(cluster_mapping)

    else:
        ea_latitude = 2.049912
        ea_longitude = 33.005245

    # generate gps data
    if gps_data_available == "No":
        num_gps_points = st.number_input(
            "Number of GPS points to generate:", min_value=1, value=500, placeholder=100
        )
        num_clusters = st.number_input(
            "Number of enumeration areas (clusters):",
            min_value=1,
            value=10,
            placeholder=5,
        )
        gps_data = generate_random_gps_data(
            num_gps_points, ea_latitude, ea_longitude, num_clusters
        )
    # select outlier method
    outlier_method = st.selectbox(
        "Select an outlier detection method to use", ["IQR", "SD"]
    )
    # select map to display
    map_option = st.selectbox(
        "Select a map to display:", ["GPS Distribution Map", "GPS Outliers Map"]
    )


# define mapping colors
map_colors = ["red", "blue", "green", "purple", "orange", "yellow", "brown", "black"]

# plot gps data distribution
ea_column = "cluster"
ea_map = create_gps_distribution_map(
    gps_data,
    ea_column=ea_column,
    latitude=ea_latitude,
    longitude=ea_longitude,
    colors_list=map_colors,
)


# preview data
st.write("Here is the preview of the data provided")
st.write(gps_data.head())


# check outliers
gps_distances_df = flag_gps_distance_outliers(
    gps_data, ea_column=ea_column, method=outlier_method
)


# flag too clustered points
min_distance_threshold = 0.1  # example threshold in kilometers
gps_distances_df = flag_too_clustered_gps_points(
    gps_distances_df, ea_column=ea_column, min_distance_threshold=min_distance_threshold
)

# plot outliers
outliers_map = plot_gps_distance_outliers(gps_distances_df, ea_latitude, ea_longitude)


# display map
if map_option == "GPS Distribution Map":
    st_folium(ea_map, width=700, height=500, returned_objects=[])
else:
    st_folium(outliers_map, width=700, height=500, returned_objects=[])


outlier_using_gps_distance = gps_distances_df[gps_distances_df["is_outlier"] == True]  # noqa: E712
too_clustered_gps = gps_distances_df[gps_distances_df["is_too_clustered"] == True]  # noqa: E712
overall_gps_outliers = gps_distances_df.loc[gps_distances_df["gps_is_outlier"] == "Yes"]

st.write(
    "Number of outliers found using gps distance check: ",
    outlier_using_gps_distance.shape[0],
)
st.write(
    "Number of outliers found using gps clustering using a threshold of "
    + str(min_distance_threshold * 1000)
    + " meters: ",
    too_clustered_gps.shape[0],
)
st.write("Total Number of gps outliers detected: ", overall_gps_outliers.shape[0])

st.write("")

# data output
if overall_gps_outliers.shape[0] > 0:
    st.write("Here are the surveys flagged by the gps cluster analysis:")
    st.write(overall_gps_outliers)
