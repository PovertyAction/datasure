import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_extras.stylable_container import stylable_container


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
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for missing data report")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to include in missing data report")

        miss_cols = st.multiselect("Columns", options=survey_cols)
        if not miss_cols:
            miss_cols = survey_cols

        missing_codes_input = st.text_input(
            "Enter missing codes separated by comma eg. -999, -888, 777 etc.",
            value="-999, -888",
        )
        if missing_codes_input:
            missing_codes = missing_codes_input.split(",")
        missing_labels_input = st.text_input(
            "Enter missing labels separated by comma eg. Missing, Not applicable, Don't know etc.",
            value="Don't Know, Refuse to Answer",
        )
        if missing_labels_input:
            missing_labels = missing_labels_input.split(",")

        st.write("---")
        st.markdown("### Report filter options")
        miss_filter_options = ["All", "Top N", "Bottom N", "Greater than", "Less than"]
        miss_filter = st.selectbox("Filter by", options=miss_filter_options)
        if miss_filter and miss_filter != "All":
            if miss_filter == "Top N" or miss_filter == "Bottom N":
                miss_filter_val = st.number_input(
                    "Number of columns", min_value=1, value=5
                )
            else:
                miss_filter_val = st.number_input(  # noqa: F841
                    "Percentage", min_value=0, max_value=100, value=10
                )

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

    # calculate the number of missing values in each column
    mv_data = data[miss_cols].isnull().sum()
    mv_data = pd.DataFrame({"Column": mv_data.index, "Null Values": mv_data.values})
    mv_data["% Null Values"] = (mv_data["Null Values"] / len(data)) * 100

    mv_data["Total Missing"] = 0
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
        mv_threshold = st.slider("Variables with % of missing values above:", 0, 100, 1)

    # Filter based on total missing percentage
    mv_data_filtered = mv_data[mv_data["% Null Values"] >= mv_threshold]

    with stylable_container(
        key="missing_table",
        css_styles="""
            {
                background-color: #F9F9F9;
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.5rem;
            }
            """,
    ):
        st.dataframe(
            mv_data_filtered.reset_index(drop=True),
            use_container_width=True,
        )

    # missingness over time
    st.write("---")
    st.markdown("## Missingness over time")

    # using the submission date column to show missingness over time
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
    st.area_chart(
        missingness_over_time.set_index("missingness_trend_date"),
        y="missingness_rate",
        use_container_width=True,
        color=["#FF8000"],
    )

    ## nullity correlation
    st.write("---")
    st.markdown("## Nullity correlation")

    # get default columns to include in the nullity correlation heatmap.
    # These are columns with at least one missing value and les 100% missing values
    null_cols = mv_data[
        (mv_data["% Null Values"] > 0) & (mv_data["% Null Values"] < 100)
    ]["Column"].tolist()

    # allow users to select columns to include in the nullity correlation heatmap
    null_cols_sel = st.multiselect(
        "Select columns to include in the nullity correlation heatmap",
        options=null_cols,
    )
    if null_cols_sel and len(null_cols_sel) > 1:
        nullity_cols = null_cols_sel
    else:
        nullity_cols = null_cols

    # build correlation matrix
    nullity_corr = data[nullity_cols].isnull().corr()
    # remove top half of the correlation matrix
    nullity_corr = nullity_corr.where(
        np.tril(np.ones(nullity_corr.shape)).astype(np.bool)
    )

    # define colors for heatmap
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

    # create a heatmap
    fig = px.imshow(nullity_corr, color_continuous_scale=sns_colormap)
    fig.update_layout(width=1000, height=1000)
    st.plotly_chart(fig)
