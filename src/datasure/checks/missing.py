import json

import numpy as np
import pandas as pd
import plotly.express as px
import seaborn as sns
import streamlit as st

from datasure.utils import (
    get_cache_path,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


def load_missing_settings(missing_setting_file: str) -> pd.DataFrame:
    """Load the default settings for the missing data report.

    Parameters
    ----------
    setting_file : str
        The file to load the settings from.

    Returns
    -------
    pd.DataFrame
        The default settings for the missing data report.
    """
    try:
        with open(missing_setting_file) as f:
            settings_dict = json.load(f)
            settings_df = pd.DataFrame(settings_dict)

    except FileNotFoundError:
        # create new dataframe with default values
        settings_df = pd.DataFrame(
            {
                "Missing Labels": [
                    "Don't Know",
                    "Refuse to Answer",
                    "Not Applicable",
                ],
                "Missing Codes": ["-999, .999", "-888, .888", "-777, .777"],
            }
        )
    return settings_df


@st.cache_data
def save_missing_settings(missing_settings_df: pd.DataFrame, setting_file: str) -> None:
    """Save the settings for the missing data report.

    Parameters
    ----------
    settings_df : pd.DataFrame
        The settings to save.
    setting_file : str
        The file to save the settings to.

    Returns
    -------
    None
    """
    with open(setting_file, "w") as f:
        json.dump(missing_settings_df.to_dict(), f)


def missing_settings(missing_setting_file: str) -> pd.DataFrame:
    """Generate the settings for the missing data report.

    Parameters
    ----------
    setting_file : str
        The file to save the settings to.

    Returns
    -------
    pd.DataFrame
        The settings for the missing data report
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("### Configure settings for missing data report")

        st.write("---")

        st.markdown("#### Add missing codes and labels for the dataset.")
        info_col, table_col = st.columns([0.3, 0.7])
        info_col.info(
            "Add missing codes and labels for the dataset. These codes and labels will be used to "
            "identify missing values in the dataset. You may edit the default values or add new ones."
        )
        with table_col:
            missing_settings_df = load_missing_settings(
                missing_setting_file=missing_setting_file
            )

            missing_settings_df_edited = st.data_editor(
                data=missing_settings_df,
                key="missing_codes_labels",
                num_rows="dynamic",
                use_container_width=True,
                on_change=trigger_save,
                kwargs={"state_name": "missing_code_save"},
            )
            if (
                "missing_code_save" in st.session_state
                and st.session_state.missing_code_save
            ):
                save_missing_settings(
                    missing_settings_df=missing_settings_df_edited,
                    setting_file=missing_setting_file,
                )

        # check that rows are either completely empty or completely filled
        if missing_settings_df_edited.isnull().sum().sum() > 0:
            st.warning("Please fill in all missing codes and labels.")

    return missing_settings_df_edited


@st.cache_data
def compute_missing_summary(data: pd.DataFrame) -> tuple:
    """Compute the summary of missing data in the dataset.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.

    Returns
    -------
    tuple
        The summary of missing data in the dataset.
    """
    missing_values = data.isnull().mean() * 100
    all_missing = data.isnull().all() * 100
    any_missing = data.isnull().any() * 100
    no_missing = 100 - any_missing

    return missing_values, all_missing, any_missing, no_missing


def missing_summary(data: pd.DataFrame) -> None:
    """Generate a summary of missing data in the dataset."""
    st.markdown("## Missing data")

    with st.container():
        missing_values, all_missing, any_missing, no_missing = compute_missing_summary(
            data=data
        )
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric(
            label="Percentage of missing values",
            value=f"{missing_values.mean():.2f}%",
            border=True,
            help="Percentage of missing values in the dataset",
        )

        mc2.metric(
            label="% of columns with all missing values",
            value=f"{all_missing.mean():.2f}%",
            border=True,
            help="Percentage of columns with all missing values",
        )

        mc3.metric(
            label="% of columns with any missing values",
            value=f"{any_missing.mean():.2f}%",
            border=True,
            help="Percentage of columns with at least one missing value",
        )

        mc4.metric(
            label="% of columns with no missing values",
            value=f"{no_missing.mean():.2f}%",
            border=True,
            help="Percentage of columns with no missing values",
        )


@st.cache_data
def compute_missing_columns(data: pd.DataFrame, missing_codes) -> pd.DataFrame:
    """Compute the summary of missing values in each column.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.
    missing_codes : pd.DataFrame
        The missing codes and labels for the dataset.

    Returns
    -------
    pd.DataFrame
        The summary of missing values in each column.
    """
    # Create a table of number of missing values and percentage of missing values
    mv_data = data.isnull().sum()
    mv_data = pd.DataFrame({"Column": mv_data.index, "Null Values": mv_data.values})
    mv_data["% Null Values"] = (mv_data["Null Values"] / len(data)) * 100

    # Add total missing values and percentage of total missing values
    mv_data["Total Missing"] = mv_data["Null Values"]
    mv_data["% Total Missing"] = 0

    # remove row if Missing Labels or Missing Codes columns is missing
    missing_codes = missing_codes.dropna(subset=["Missing Labels", "Missing Codes"])

    for i in range(len(missing_codes)):
        miss_label = missing_codes["Missing Labels"][i]
        miss_codes = missing_codes["Missing Codes"][i].split(",")
        new_col = data.apply(lambda x: x.isin(miss_codes)).sum()  # noqa: B023

        new_col = pd.DataFrame(
            {"Column": new_col.index, f"{miss_label}": new_col.values}
        )
        new_col[f"% {miss_label}"] = (new_col[f"{miss_label}"] / len(data)) * 100

        # update the total missing values
        mv_data["Total Missing"] += new_col[f"{miss_label}"]

        # join new column to mv_data using column name
        mv_data = mv_data.merge(new_col, on="Column", how="left")

    # calculate percentage of total missing values
    mv_data["% Total Missing"] = (mv_data["Total Missing"] / len(data)) * 100
    # update the column order
    mv_data = mv_data[
        [
            "Column",
            "Total Missing",
            "% Total Missing",
        ]
        + [
            col
            for col in mv_data.columns
            if col not in ["Column", "Total Missing", "% Total Missing"]
        ]
    ]

    return mv_data


@st.cache_data
def compute_filtered_missing_columns(data: pd.DataFrame, mv_threshold: int) -> tuple:
    """Compute filtered datasets and statistics based on filtered result columns."""
    # Filter based on total missing percentage
    mv_data_filtered = data[data["% Total Missing"] >= mv_threshold]

    perc_cols = [col for col in data.columns if "%" in col]
    vmin_val = mv_data_filtered[perc_cols].min().min()
    vmax_val = mv_data_filtered[perc_cols].max().max()

    return mv_data_filtered, perc_cols, vmin_val, vmax_val


def missing_columns(data: pd.DataFrame, missing_codes, setting_file) -> None:
    """Generate a table showing the percentage of missing values in each column."""
    # display the table
    st.write("---")
    st.markdown("## Missingness by column")

    _, _, _, slider_col = st.columns(4)

    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="missing") or {}
    )
    mv_threshold = default_settings.get("mv_threshold", 0)
    with slider_col:
        mv_threshold = st.slider(
            label="Filter Report by % missing:",
            help="Select the threshold for filtering columns based on missing percentage of missing values",
            min_value=0,
            max_value=100,
            value=mv_threshold,
            key="mv_threshold",
            on_change=trigger_save,
            kwargs={"state_name": "mv_threshold_save"},
        )
        if (
            "mv_threshold_save" in st.session_state
        ) and st.session_state.mv_threshold_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"mv_threshold": mv_threshold},
            )
        st.session_state["mv_threshold_save"] = False

    mv_data = compute_missing_columns(data=data, missing_codes=missing_codes)
    # Filter based on total missing percentage
    mv_data_filtered, perc_cols, vmin_val, vmax_val = compute_filtered_missing_columns(
        data=mv_data, mv_threshold=mv_threshold
    )

    cmap = sns.light_palette("pink", as_cmap=True)
    st.dataframe(
        mv_data_filtered.style.format(
            subset=perc_cols, precision=2
        ).background_gradient(
            subset=perc_cols, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Column": st.column_config.Column(pinned=True),
            "Total Missing": st.column_config.Column(pinned=True),
            "% Total Missing": st.column_config.Column(pinned=True),
        },
    )


@st.cache_data
def compute_missing_over_time(data: pd.DataFrame, select_date_col: str) -> pd.DataFrame:
    """Compute the missingness over time based on the selected date column."""
    # extract dateonly from selected date column
    miss_trend_data = data.copy()
    miss_trend_data["missingness_trend_date"] = data[select_date_col].dt.date
    miss_trend_date_count = miss_trend_data["missingness_trend_date"]

    # generate a new dataset aggregating missingness trend date by date count
    miss_trend_date_count = miss_trend_date_count.value_counts().reset_index()

    # calculate missingness over time
    stat_cols = [col for col in data.columns if col != "missingness_trend_date"]
    missingness_over_time = miss_trend_data.groupby("missingness_trend_date")[
        stat_cols
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

    return missingness_over_time


def missing_over_time(data: pd.DataFrame, setting_file) -> None:
    """Generate a report on missing data over time."""
    # missingness over time
    st.write("---")
    st.markdown("## Missingness over time")

    # get the date columns from dataset
    date_cols = data.select_dtypes(include=["datetime64"]).columns

    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="missing") or {}
    )
    select_date_col = default_settings.get("select_date_col", None)
    dc1, _ = st.columns([0.3, 0.7])
    with dc1:
        select_date_col_index = (
            date_cols.tolist().index(select_date_col)
            if select_date_col and select_date_col in date_cols
            else None
        )
        select_date_col = st.selectbox(
            "Select date column",
            options=date_cols,
            index=select_date_col_index,
            key="select_date_col",
            help="Select the date column to compute missingness over time",
            on_change=trigger_save,
            kwargs={"state_name": "select_date_col_save"},
        )
        if (
            "select_date_col_save" in st.session_state
        ) and st.session_state.select_date_col_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"select_date_col": select_date_col},
            )
            st.session_state["select_date_col_save"] = False

    if not select_date_col:
        st.info(
            "Missingness over time requires a date column to be selected. Got to :material/settings: settings to select a date column."
        )
        return

    missingness_over_time = compute_missing_over_time(
        data=data, select_date_col=select_date_col
    )

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
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data
def compute_missing_compare(
    data: pd.DataFrame, group_by_col: str, compare_col: str
) -> tuple:
    """Compute the missingness comparison between groups.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.
    group_by_col : str
        The column to group the data by.
    compare_col : str
        The column to compare the missingness.

    Returns
    -------
        tuple
            dataframe - The summary of missing values in each column.
            minimum value in dataframe
            maximum value in dataframe
    """
    if group_by_col:
        group_by_data = data[group_by_col].value_counts(dropna=False).reset_index()
        group_by_data.columns = [group_by_col, "values (count)"]
        group_by_data["values (%)"] = (
            group_by_data["values (count)"] / len(data)
        ) * 100

    if compare_col:
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

    return group_by_data, vmin_val, vmax_val


def missing_compare(data: pd.DataFrame, setting_file: str) -> None:
    """Generate a report comparing missing data in the dataset."""
    # missing data comparison
    st.write("---")
    st.markdown("## Compare missing data within groups")

    mc_1, mc_2 = st.columns([0.3, 0.7])

    with mc_1:
        # allow only categorical columns for grouping
        allowed_cols = data.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()

        # get default settings for group_by_col and compare_col
        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="missing") or {}
        )
        group_by_col = default_settings.get("group_by_col", None)
        group_by_col_index = (
            allowed_cols.index(group_by_col)
            if group_by_col and group_by_col in allowed_cols
            else None
        )
        group_by_col = st.selectbox(
            label="Select column to group missing data by",
            options=allowed_cols,
            index=group_by_col_index,
            help="Select the column to group missing data by",
            key="group_by_col",
            on_change=trigger_save,
            kwargs={"state_name": "group_by_col_save"},
        )
        if (
            "group_by_col_save" in st.session_state
        ) and st.session_state.group_by_col_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"group_by_col": group_by_col},
            )
            st.session_state["group_by_col_save"] = False
        allowed_cols = [col for col in data.columns if col != group_by_col]

    with mc_2:
        compare_col = default_settings.get("compare_col", None)
        compare_col = st.multiselect(
            label="Select column to compare missing data",
            options=allowed_cols,
            disabled=not group_by_col,
            default=compare_col,
            help="Select the column to compare missing data",
            key="compare_col",
            on_change=trigger_save,
            kwargs={"state_name": "compare_col_save"},
        )
        if (
            "compare_col_save" in st.session_state
        ) and st.session_state.compare_col_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"compare_col": compare_col},
            )
            st.session_state["compare_col_save"] = False

    if group_by_col:
        group_by_data, vmin_val, vmax_val = compute_missing_compare(
            data=data, group_by_col=group_by_col, compare_col=compare_col
        )

        if not compare_col:
            st.dataframe(group_by_data, use_container_width=True, hide_index=True)
        else:
            cmap = sns.light_palette("pink", as_cmap=True)
            st.dataframe(
                group_by_data.style.format(subset=compare_col, precision=2)
                .format(subset=["values (count)"], thousands=",")
                .format(subset=["values (%)"], precision=2)
                .background_gradient(
                    subset=compare_col, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
                ),
                use_container_width=True,
                column_config={
                    "values (count)": st.column_config.Column(pinned=True),
                    "values (%)": st.column_config.Column(pinned=True),
                },
            )

    else:
        st.warning(
            "Select a column to group missing data by and a column to compare missing data."
        )


@st.cache_data
def compute_missing_correlation(data: pd.DataFrame, null_cols: str) -> pd.DataFrame:
    """Compute the correlation of missing data in the dataset.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.
    color_map : str
        The color map to use for the heatmap.

    Returns
    -------
    pd.DataFrame
        The correlation of missing data in the dataset.
    """
    nullity_corr = data[null_cols].isnull().corr()
    nullity_corr = nullity_corr.where(
        np.tril(np.ones(nullity_corr.shape)).astype(np.bool)
    )

    return nullity_corr


@st.cache_data
def get_null_list(data: pd.DataFrame, all_cols: bool) -> list:
    """Get list of columns depending on trigger for all columns"""
    if all_cols:
        col_options = data.columns
    else:
        col_options = data.columns[data.isnull().any() & data.notnull().any()].to_list()

    return col_options


def missing_correlation(data: pd.DataFrame, color_map: str, setting_file: str) -> None:
    """Generate a report on missing data correlation."""
    ## nullity correlation
    st.write("---")
    st.markdown("## Nullity correlation")

    mc1, mc2 = st.columns([0.1, 0.9])
    with mc1:
        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="missing") or {}
        )
        all_cols = default_settings.get("all_cols", False)
        all_cols = st.toggle(
            label="allow any columns",
            help="Select to allow the selection of any columns in the dataset. By default, only columns \
                with at least one missing value and at least one non-missing value are allowed.",
            on_change=trigger_save,
            kwargs={"state_name": "all_cols_save"},
        )

        if ("all_cols_save" in st.session_state) and st.session_state.all_cols_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"all_cols": all_cols},
            )
            st.session_state["all_cols_save"] = False

        col_options = get_null_list(data=data, all_cols=all_cols)

    with mc2:
        null_cols_sel = default_settings.get("null_cols_sel", None)
        null_cols_sel = st.multiselect(
            label="Select columns for nullity correlation",
            options=col_options,
            help="Select columns to calculate nullity correlation, by default all columns with missing values are selected",
            default=null_cols_sel,
            key="null_cols_sel",
            on_change=trigger_save,
            kwargs={"state_name": "null_cols_sel_save"},
        )
        if (
            "null_cols_sel_save" in st.session_state
        ) and st.session_state.null_cols_sel_save:
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"null_cols_sel": null_cols_sel},
            )
            st.session_state["null_cols_sel_save"] = False

    if null_cols_sel and len(null_cols_sel) > 1:
        nullity_corr = compute_missing_correlation(data=data, null_cols=null_cols_sel)

        fig = px.imshow(nullity_corr, color_continuous_scale=color_map)
        fig.update_layout(width=1000, height=1000)
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("Select at least two columns to calculate nullity correlation.")


@st.cache_data
def compute_missing_matrix(data: pd.DataFrame, sort_by_col: str) -> pd.DataFrame:
    """Compute the missingness matrix for the dataset.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.
    group_by_col : str
        The column to group the data by.

    Returns
    -------
    pd.DataFrame
        The missingness matrix for the dataset.
    """
    null_data = data.copy()
    if sort_by_col:
        null_data.set_index(sort_by_col, inplace=True)
        null_data.sort_index(inplace=True)

    # convert data into a giant matrix of 1s and 0s depending on missingness
    nullity_matrix = null_data.isnull().astype(int)

    return nullity_matrix


def missing_matrix(data: pd.DataFrame, color_map: str, setting_file: str) -> None:
    """Generate a report on missing data matrix.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to compute the summary for.
    color_map : str
        The color map to use for the heatmap.
    setting_file : str
        Setting file
        The file to save the settings to.

    Returns
    -------
        None
    """
    st.write("---")
    st.markdown("## Nullity matrix")

    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="missing") or {}
    )
    sort_by_col = default_settings.get("sort_by_col", None)
    sort_by_col_index = (
        data.columns.tolist().index(sort_by_col) if sort_by_col else None
    )
    sort_by_col = st.selectbox(
        label="Select columns to group nullity matrix by",
        options=data.columns,
        index=sort_by_col_index,
        help="Select columns to group nullity matrix by",
        key="sort_by_col",
        on_change=trigger_save,
        kwargs={"state_name": "sort_by_col_save"},
    )

    if ("sort_by_col_save" in st.session_state) and st.session_state.sort_by_col_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="missing",
            check_settings={"sort_by_col": sort_by_col},
        )
        st.session_state["sort_by_col_save"] = False

    if sort_by_col:
        st.info(body=f"Matrix is sorted by {sort_by_col}", icon=":material/info:")

    nullity_matrix = compute_missing_matrix(data=data, sort_by_col=sort_by_col)

    # display as heatmap
    fig1 = px.imshow(nullity_matrix, color_continuous_scale=color_map)
    fig1.layout.coloraxis.showscale = False
    fig1.update_layout(width=1000, height=1000)
    st.plotly_chart(fig1, use_container_width=True)


# define function to create summary report
def missing_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_name: str
) -> None:  # noqa: D417, RUF100
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

    missing_setting_file = get_cache_path(
        project_id, "settings", f"missing_settings_{page_name}.json"
    )

    missing_codes = missing_settings(missing_setting_file=missing_setting_file)
    missing_summary(data=data)
    missing_columns(data=data, missing_codes=missing_codes, setting_file=setting_file)
    missing_compare(data=data, setting_file=setting_file)
    missing_over_time(data=data, setting_file=setting_file)
    missing_correlation(data=data, color_map=sns_colormap, setting_file=setting_file)
    missing_matrix(data=data, color_map=sns_colormap, setting_file=setting_file)
