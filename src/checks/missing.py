import numpy as np
import pandas as pd
import plotly.express as px
import seaborn as sns
import streamlit as st
from streamlit_extras.stylable_container import stylable_container


def missing_settings(data) -> tuple:
    """Generate the settings for the missing data report."""
    survey_cols = data.columns.tolist()

    miss_codes, miss_labels = ([], [])

    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for missing data report")

        st.write("---")

        miss_codes = st.text_input(
            label="Enter missing codes separated by comma eg. -999, -888, 777 etc.",
            value="-999, -888",
        )
        if miss_codes:
            miss_codes_lst = miss_codes.split(",")

        miss_labels = st.text_input(
            label="Enter missing labels separated by comma eg. Missing, Not applicable, Don't know etc.",
            help="The labels should correspond to the missing codes entered above",
            value="Don't Know, Refuse to Answer",
        )
        if miss_labels:
            miss_labels_lst = miss_labels.split(",")

        if len(miss_codes_lst) != len(miss_labels_lst):
            st.warning("Number of missing codes and labels must be the same.")

        st.write("---")
        # add save settings button
        save_settings = st.button(label="Save settings", key="save_settings_missing")
        if save_settings:
            st.success("Settings saved successfully.")

    return survey_cols, miss_codes_lst, miss_labels_lst


def missing_summary(data, miss_cols) -> None:
    """Generate a summary of missing data in the dataset."""
    st.markdown("## Missing data")

    with stylable_container(
        key="missing_metrics",
        css_styles="""
            {
                background-color: #F9F9F9;
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.5rem;
                padding: calc(1em - 1px)
            }
            """,
    ):
        mc1, mc2, mc3, mc4 = st.columns(4)

        missing_values = data[miss_cols].isnull().mean() * 100
        all_missing = data[miss_cols].isnull().all() * 100
        any_missing = data[miss_cols].isnull().any() * 100
        no_missing = 100 - any_missing

        mc1.metric(
            label="% of missing values",
            value=f"{missing_values.mean():.2f}%",
        )

        mc2.metric(
            label="% of columns with all missing values",
            value=f"{all_missing.mean():.2f}%",
        )

        mc3.metric(
            label="% of columns with at least one missing value",
            value=f"{any_missing.mean():.2f}%",
        )

        mc4.metric(
            label="% of columns with no missing values",
            value=f"{no_missing.mean():.2f}%",
        )


def missing_columns(data, miss_cols, missing_codes, missing_labels) -> None:
    """Generate a table showing the percentage of missing values in each column."""
    # Create a table of number of missing values and percentage of missing values
    mv_data = data[miss_cols].isnull().sum()
    mv_data = pd.DataFrame({"Column": mv_data.index, "Null Values": mv_data.values})
    mv_data["% Null Values"] = (mv_data["Null Values"] / len(data)) * 100
    mv_data["Total Missing"] = mv_data["Null Values"]
    mv_data["% Total Missing"] = 0
    mv_data = mv_data[
        ["Column", "Total Missing", "% Total Missing", "Null Values", "% Null Values"]
    ]

    for i, mcode in enumerate(missing_codes):
        new_col = data[miss_cols].apply(lambda x: x == mcode).sum()  # noqa: B023
        new_col = pd.DataFrame(
            {"Column": new_col.index, f"{missing_labels[i]}": new_col.values}
        )
        new_col[f"% {missing_labels[i]}"] = (
            new_col[f"{missing_labels[i]}"] / len(data)
        ) * 100

        # join new column to mv_data using column name
        mv_data = mv_data.merge(new_col, on="Column", how="left")
        mv_data["Total Missing"] += mv_data[f"{missing_labels[i]}"]

    mv_data["% Total Missing"] = (mv_data["Total Missing"] / len(data)) * 100

    # format percentage columns
    for col in mv_data.columns:
        if "%" in col:
            mv_data.style.format({col: "{:.2f}%".format})

    # display the table
    st.write("---")
    st.markdown("## Missingness by column")

    _, _, _, slider_col = st.columns(4)

    # Create the slider
    with slider_col:
        mv_threshold = st.slider(
            label="Variables with % of missing values above:",
            help="Select the threshold for filtering variables based on missing values",
            min_value=0,
            max_value=100,
            value=0,
        )

    # Filter based on total missing percentage
    mv_data_filtered = mv_data[mv_data["% Null Values"] >= mv_threshold]

    st.dataframe(
        mv_data_filtered.reset_index(drop=True),
        use_container_width=True,
    )


def missing_over_time(data, miss_cols, color_map) -> None:
    """Generate a report on missing data over time."""
    # missingness over time
    st.write("---")
    st.markdown("## Missingness over time")

    # get the date columns from dataset
    date_cols = data.select_dtypes(include=["datetime64"]).columns
    select_date_col = st.selectbox("Select date column", options=date_cols)

    # extract dateonly from selected date column
    miss_trend_data = data.copy()
    miss_trend_data["missingness_trend_date"] = data[select_date_col].dt.date
    miss_trend_date_count = miss_trend_data["missingness_trend_date"]

    # generate a new dataset aggregating missingness trend date by date count
    miss_trend_date_count = miss_trend_date_count.value_counts().reset_index()

    # calculate missingness over time
    missingness_over_time = miss_trend_data.groupby("missingness_trend_date")[
        miss_cols
    ].apply(lambda x: x.isnull().sum())
    missingness_over_time = missingness_over_time.reset_index()

    # get a list of all variables except for missingness_trend_date
    cols = list(missingness_over_time.columns)
    cols.remove("missingness_trend_date")

    missingness_over_time["total_missing"] = (
        missingness_over_time[cols].sum(axis=1).reset_index(drop=True)
    )
    missingness_over_time = missingness_over_time[
        ["missingness_trend_date", "total_missing"]
    ]

    # merge missingness_over_time with miss_trend_date_count
    missingness_over_time = missingness_over_time.merge(
        miss_trend_date_count, on="missingness_trend_date", how="left"
    )
    missingness_over_time["count"] = missingness_over_time["count"] * len(cols)
    missingness_over_time["missingness_rate"] = (
        missingness_over_time["total_missing"] / missingness_over_time["count"]
    ) * 100

    # display area plot of missingness over time
    fig = px.area(
        missingness_over_time,
        x="missingness_trend_date",
        y="missingness_rate",
        title="Missingness over time",
        labels={
            "missingness_trend_date": select_date_col,
            "missingness_rate": "Missingness rate (%)",
        },
        color_discrete_sequence=["#e8848b"],
    )
    fig.update_layout(width=1000, height=500)
    fig.update_layout(yaxis_range=[0, 100])
    st.plotly_chart(fig)


def missing_correlation(data, miss_cols, color_map) -> None:
    """Generate a report on missing data correlation."""
    ## nullity correlation
    st.write("---")
    st.markdown("## Nullity correlation")

    # get columns with at least one missing value and not all missing values
    null_cols = [col for col in data.columns if data[col].isnull().any()]
    null_cols = [col for col in null_cols if not data[col].isnull().all()]

    # user define columns for nullity correlation
    null_cols_sel = st.multiselect(
        label="Select columns to include in the nullity correlation heatmap",
        options=null_cols,
    )
    if null_cols_sel and len(null_cols_sel) > 1:
        nullity_cols = null_cols_sel
    else:
        nullity_cols = null_cols

    nullity_corr = data[nullity_cols].isnull().corr()
    nullity_corr = nullity_corr.where(
        np.tril(np.ones(nullity_corr.shape)).astype(np.bool)
    )

    fig = px.imshow(nullity_corr, color_continuous_scale=color_map)
    fig.update_layout(width=1000, height=1000)
    st.plotly_chart(fig)


def missing_matrix(data, color_map) -> None:
    """Generate a report on missing data matrix."""
    st.write("---")
    st.markdown("## Nullity matrix")

    # select columns to group nullity matrix by
    group_by_col = st.selectbox(
        "Select columns to group nullity matrix by", options=data.columns, index=None
    )

    if group_by_col:
        null_data = data.set_index(group_by_col)
        null_data.sort_index(inplace=True)

    else:
        null_data = data

    # convert data into a giant matrix of 1s and 0s depending on missingness
    nullity_matrix = null_data.isnull().astype(int)

    # display as heatmap
    fig1 = px.imshow(nullity_matrix, color_continuous_scale=color_map)
    fig1.layout.coloraxis.showscale = False
    fig1.update_layout(width=1000, height=1000)
    st.plotly_chart(fig1)


def missing_compare(data, miss_cols, color_map) -> None:
    """Generate a report comparing missing data in the dataset."""
    # missing data comparison
    st.write("---")
    st.markdown("## Compare missing data within groups")

    mc_1, mc_2 = st.columns([0.3, 0.7])

    with mc_1:
        group_by_col = st.selectbox(
            label="Select column to group missing data by",
            options=miss_cols,
            index=None,
        )

    with mc_2:
        compare_col = st.multiselect(
            label="Select column to compare missing data",
            options=data.columns,
        )

    if group_by_col:
        group_by_data = data[group_by_col].value_counts(dropna=False).reset_index()
        group_by_data.columns = [group_by_col, "values (count)"]
        group_by_data["values (%)"] = (
            group_by_data["values (count)"] / len(data)
        ) * 100

    if group_by_col and not compare_col:
        st.dataframe(group_by_data, use_container_width=True, hide_index=True)
    elif group_by_col and compare_col:
        missing_compare = data.groupby(group_by_col, dropna=False)[compare_col].apply(
            lambda x: x.isnull().mean() * 100
        )

        group_by_data = group_by_data.merge(
            missing_compare, left_on=group_by_col, right_index=True
        )
        group_by_data.reset_index(drop=True, inplace=True)
        group_by_data.set_index(group_by_col, inplace=True)

        vmin_val = group_by_data[compare_col].min().min()
        vmax_val = group_by_data[compare_col].max().max()

        cmap = sns.light_palette("pink", as_cmap=True)
        st.dataframe(
            group_by_data.style.format(subset=compare_col, precision=2)
            .format(subset=["values (count)"], thousands=",")
            .format(subset=["values (%)"], precision=2)
            .background_gradient(
                subset=compare_col, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
            ),
            use_container_width=True,
        )

    else:
        st.warning(
            "Please select a column to group missing data by and a column to compare missing data."
        )


# define function to create summary report
def missing_report(data, page_num) -> None:  # noqa: D417, RUF100
    """Generate a report on missing data in the dataset. The report includes a
    summary of missing data, a table showing the percentage of missing values
    in each column, and an option to inspect variables with missing data.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to generate the missing data
                report for.

    Returns
    -------
            None

    """
    # define the color palette for the nullity correlation heatmap
    sns_colormap = [
        [0.0, "#3f7f93"],
        [0.1, "#6397a7"],
        [0.2, "#88b1bd"],
        [0.3, "#acc9d2"],
        [0.4, "#d1e2e7"],
        [0.5, "#f2f2f2"],
        [0.6, "#f6cdd0"],
        [0.7, "#efa8ad"],
        [0.8, "#e8848b"],
        [0.9, "#e15e68"],
        [1.0, "#da3b46"],
    ]

    miss_cols, missing_codes, missing_labels = missing_settings(data)
    missing_summary(data, miss_cols)
    missing_columns(data, miss_cols, missing_codes, missing_labels)
    missing_over_time(data, miss_cols, color_map=sns_colormap)
    missing_compare(data, miss_cols, sns_colormap)
    missing_correlation(data, miss_cols, sns_colormap)
    missing_matrix(data, sns_colormap)
