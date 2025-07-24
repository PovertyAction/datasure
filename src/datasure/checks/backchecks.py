import os

import pandas as pd
import plotly.express as px
import streamlit as st

from datasure.utils import (
    get_check_config_settings,
    load_check_settings,
    save_check_settings,
    trigger_save,
)

IGNORE_MISSING_VALUES = "ignore_missing_values"
DO_NOT_COMPARE_VALUES = "Do not compare if the values contain:"
TREAT_VALUES_AS_SAME = "Treat these values as the same:"
NO_BACKCHECK_COLUMNS_SET = "Backcheck columns settings required. Go to the :material/settings: Backcheck columns settings section above."


##### Backchecks #####


@st.cache_data
def load_default_backcheck_settings(
    project_id: str, setting_file: str, page_num: int
) -> tuple:
    """Load default settings for backcheck report.

    Parameters
    ----------
    project_id : str
        Project ID.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the report.

    Returns
    -------
    tuple
        Default settings for backcheck report.
    """
    # Get config page defaults
    (
        _,
        _,
        config_survey_key,
        config_survey_id,
        config_survey_date,
        config_enumerator,
        _,
        _,
    ) = get_check_config_settings(
        project_id=project_id,
        page_row_index=page_num - 1,
    )

    if setting_file and os.path.exists(setting_file):
        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="backchecks")
            or {}
        )
    else:
        default_settings = {}

    return (
        default_settings.get("date", config_survey_date),
        default_settings.get("enumerator", config_enumerator),
        default_settings.get("backchecker"),
        default_settings.get("survey_id", config_survey_id),
        default_settings.get("survey_key", config_survey_key),
        default_settings.get("backcheck_goal", 0),
        default_settings.get("drop_duplicates", True),
    )


def _handle_meta_settings(survey_cols, date, setting_file):
    """Handle metadata column settings."""
    default_date_index = (
        survey_cols.get_loc(date) if date and date in survey_cols else None
    )
    date = st.selectbox(
        "Date",
        options=survey_cols,
        help="Column containing survey date",
        key="date_backcheck",
        index=default_date_index,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_date"},
    )
    if "backcheck_date" in st.session_state and st.session_state.backcheck_date:
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"date": date},
        )
        st.session_state.backcheck_date = False
    return date


def _handle_enum_settings(
    survey_cols, backcheck_cols_list, enumerator, backchecker, setting_file
):
    """Handle enumerator column settings."""
    default_enumerator_index = (
        survey_cols.get_loc(enumerator)
        if enumerator and enumerator in survey_cols
        else None
    )
    enumerator = st.selectbox(
        "Enumerator",
        options=survey_cols,
        help="Column containing survey enumerator",
        key="enumerator_backcheck",
        index=default_enumerator_index,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_enumerator"},
    )
    if (
        "backcheck_enumerator" in st.session_state
        and st.session_state.backcheck_enumerator
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"enumerator": enumerator},
        )
        st.session_state.backcheck_enumerator = False

    default_backchecker_index = (
        backcheck_cols_list.get_loc(backchecker)
        if backchecker and backchecker in backcheck_cols_list
        else None
    )
    backchecker = st.selectbox(
        "Back Checker",
        options=backcheck_cols_list,
        help="Column containing back check enumerator",
        key="backchecker_backcheck",
        index=default_backchecker_index,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_backchecker"},
    )
    if (
        "backcheck_backchecker" in st.session_state
        and st.session_state.backcheck_backchecker
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"backchecker": backchecker},
        )
        st.session_state.backcheck_backchecker = False
    return enumerator, backchecker


def _handle_agg_settings(survey_cols, survey_id, survey_key, setting_file):
    """Handle aggregation column settings."""
    default_survey_id_index = (
        survey_cols.get_loc(survey_id)
        if survey_id and survey_id in survey_cols
        else None
    )
    survey_id = st.selectbox(
        "Survey ID (required)",
        options=survey_cols,
        help="Column containing survey ID",
        key="surveyid_backcheck",
        index=default_survey_id_index,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_survey_id"},
    )
    if (
        "backcheck_survey_id" in st.session_state
        and st.session_state.backcheck_survey_id
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"survey_id": survey_id},
        )
        st.session_state.backcheck_survey_id = False

    default_survey_key_index = (
        survey_cols.get_loc(survey_key)
        if survey_key and survey_key in survey_cols
        else None
    )
    survey_key = st.selectbox(
        "Survey Key (required)",
        options=survey_cols,
        help="Column containing survey key",
        key="surveykey_backcheck",
        index=default_survey_key_index,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_survey_key"},
    )
    if (
        "backcheck_survey_key" in st.session_state
        and st.session_state.backcheck_survey_key
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"survey_key": survey_key},
        )
        st.session_state.backcheck_survey_key = False
    return survey_id, survey_key


def _handle_tracking_options(
    setting_file, backcheck_goal, drop_duplicates, date, survey_id
):
    """Handle tracking options settings."""
    backcheck_goal = st.number_input(
        "Target number of backchecks",
        min_value=0,
        help="Total number of backchecks expected",
        key="total_goal_backcheck",
        value=backcheck_goal,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_goal"},
    )
    if "backcheck_goal" in st.session_state and st.session_state.backcheck_goal:
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"backcheck_goal": backcheck_goal},
        )
        st.session_state.backcheck_goal = False

    st.write("How would you like to handle duplicates?")
    drop_duplicates = st.toggle(
        label="Drop duplicates",
        value=drop_duplicates,
        key="drop_duplicates_backcheck",
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_drop_duplicates"},
    )
    if drop_duplicates and (not date or not survey_id):
        st.info(
            "Please select date and survey id columns to drop duplicates correctly."
        )

    if (
        "backcheck_drop_duplicates" in st.session_state
        and st.session_state.backcheck_drop_duplicates
    ):
        save_check_settings(
            settings_file=setting_file,
            check_name="backchecks",
            check_settings={"drop_duplicates": drop_duplicates},
        )
        st.session_state.backcheck_drop_duplicates = False
    return backcheck_goal, drop_duplicates


def backcheck_report_settings(
    project_id: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    setting_file: str,
    page_num: int,
) -> tuple:
    """Load settings for backcheck report.

    Parameters
    ----------
    project_id : str
        Project ID.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the report.

    Returns
    -------
    tuple
        Settings for backcheck report.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")

        survey_cols = survey_data.columns
        backcheck_cols_list = backcheck_data.columns
        common_cols = [col for col in survey_data.columns if col in backcheck_cols_list]

        settings = load_default_backcheck_settings(project_id, setting_file, page_num)
        (
            date,
            enumerator,
            backchecker,
            survey_id,
            survey_key,
            backcheck_goal,
            drop_duplicates,
        ) = settings

        agg_col, enum_col, meta_col = st.columns(spec=3, border=True)

        with meta_col:
            date = _handle_meta_settings(survey_cols, date, setting_file)

        with enum_col:
            enumerator, backchecker = _handle_enum_settings(
                survey_cols, backcheck_cols_list, enumerator, backchecker, setting_file
            )

        with agg_col:
            survey_id, survey_key = _handle_agg_settings(
                survey_cols, survey_id, survey_key, setting_file
            )

        st.write("---")
        st.markdown("### Tracking Options")
        backcheck_goal, drop_duplicates = _handle_tracking_options(
            setting_file, backcheck_goal, drop_duplicates, date, survey_id
        )

        st.write("")

    return (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
        common_cols,
    )


def process_duplicate_data(
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    date: str,
    drop_duplicates: bool,
) -> tuple:
    """Process and handle duplicates in survey and backcheck data.

    Parameters
    ----------
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    date : str
        Date column name.
    drop_duplicates : bool
        Whether to drop duplicates.

    Returns
    -------
    tuple
        Processed survey and backcheck data.
    """
    survey_data = survey_data.sort_values(by=date, ascending=False).drop_duplicates(
        subset=[survey_id], keep="first"
    )
    backcheck_data = backcheck_data.sort_values(
        by=date, ascending=False
    ).drop_duplicates(subset=[survey_id], keep="first")

    return survey_data, backcheck_data


@st.cache_data
def compute_backcheck_overview(
    survey_df_bc: pd.DataFrame,
    backcheck_df_bc: pd.DataFrame,
    merged_df: pd.DataFrame,
    enumerator: str | None,
    backcheck_goal: int,
    min_backcheck_rate: float,
) -> tuple:
    """Compute overview metrics for backcheck report.

    Parameters
    ----------
    survey_df_bc : pd.DataFrame
        Survey data with prefixes.
    backcheck_df_bc : pd.DataFrame
        Backcheck data with prefixes.
    merged_df : pd.DataFrame
        Merged survey and backcheck data.
    enumerator : str
        Enumerator column name.
    backcheck_goal : int
        Target number of backchecks.
    min_backcheck_rate : float
        Minimum backcheck rate percentage.

    Returns
    -------
    tuple
        Overview metrics.
    """
    total_backchecks = len(backcheck_df_bc)

    # Handle case when backchecks > target
    backcheck_goal_update = (
        max(backcheck_goal, total_backchecks)
        if backcheck_goal > 0
        else total_backchecks
    )
    # Calculate backcheck rate by enumerator
    if enumerator:
        backcheck_sum_df = (
            survey_df_bc.groupby("_svy_" + enumerator)
            .size()
            .reset_index(name="total_surveys")
        )

        backcheck_sum_df = backcheck_sum_df.merge(
            merged_df.groupby("_svy_" + enumerator)
            .size()
            .reset_index(name="total_backchecks"),
            left_on="_svy_" + enumerator,
            right_on="_svy_" + enumerator,
            how="outer",
        )

        backcheck_sum_df["backcheck_rate"] = (
            backcheck_sum_df["total_backchecks"] / backcheck_sum_df["total_surveys"]
        ) * 100

        bc_target_met_df = backcheck_sum_df[
            backcheck_sum_df["backcheck_rate"] >= min_backcheck_rate
        ]

        num_enumerators_bc = bc_target_met_df["_svy_" + enumerator].nunique()
        total_enumerators = len(survey_df_bc["_svy_" + enumerator].unique())

    else:
        num_enumerators_bc = 0
        total_enumerators = 0
    return (
        total_backchecks,
        backcheck_goal_update,
        num_enumerators_bc,
        total_enumerators,
    )


@st.cache_data
def generate_column_summary(
    column_config_data: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    summary_col: str | None,
) -> tuple:
    """Generate a summary for each column configuration.

    Parameters
    ----------
    column_config_data : pd.DataFrame
        DataFrame containing column configuration.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    enumerator : str
        Enumerator column name.
    backchecker : str
        Backchecker column name.
    summary_col : str, optional
        Column name to group results by.

    Returns
    -------
    tuple
        Summary DataFrame and merged results DataFrame.
    """
    # Update datasets with prefixes
    survey_data = survey_data.add_prefix("_svy_").rename(
        columns={"_svy_" + survey_id: survey_id}
    )
    backcheck_data = backcheck_data.add_prefix("_bc_").rename(
        columns={"_bc_" + survey_id: survey_id}
    )

    if enumerator:
        enumerator = "_svy_" + enumerator
    if backchecker:
        backchecker = "_bc_" + backchecker

    summary_data = []
    merged_results_df = pd.DataFrame()

    for _, row in column_config_data.iterrows():
        column_name = row["column"]
        column_type = row["category"]
        ok_range = row["ok_range"]
        comparison_condition = row["comparison_condition"]

        # Prepare survey and backcheck data
        svy_col = f"_svy_{column_name}"
        bc_col = f"_bc_{column_name}"

        # Create merged dataframe for this column
        merged_svy_bc_df = _create_merged_comparison_df(
            survey_data,
            backcheck_data,
            survey_id,
            enumerator,
            backchecker,
            svy_col,
            bc_col,
            summary_col,
        )

        # Apply comparison logic
        merged_svy_bc_df["comparison_result"] = merged_svy_bc_df.apply(
            lambda row,
            s=svy_col,
            b=bc_col,
            r=ok_range,
            c=comparison_condition: _compare_values(row, s, b, r, c),
            axis=1,
        )

        merged_svy_bc_df["variable"] = svy_col.replace("_svy_", "")
        merged_svy_bc_df_clean = merged_svy_bc_df.copy()
        merged_svy_bc_df_clean = merged_svy_bc_df_clean.rename(
            columns={
                svy_col: "survey value",
                bc_col: "backcheck value",
            }
        )

        # Add to results
        merged_results_df = pd.concat(
            [merged_results_df, merged_svy_bc_df_clean], ignore_index=True
        )

        # Calculate summary statistics
        summary_stats = _calculate_column_summary_stats(
            merged_svy_bc_df,
            column_name,
            column_type,
            survey_data[svy_col],
            summary_col,
        )
        summary_data.extend(summary_stats)

    # Clean merged table results (only if DataFrame is not empty)
    if not merged_results_df.empty:
        merged_results_df = merged_results_df.rename(
            columns={
                enumerator: "Enumerator",
                backchecker: "Back Checker",
            }
        )
        enum_bc_cols = [survey_id]
        if enumerator:
            enum_bc_cols.append("Enumerator")
        if backchecker:
            enum_bc_cols.append("Back Checker")

        other_cols = [
            col for col in merged_results_df.columns if col not in enum_bc_cols
        ]
        merged_results_df = merged_results_df[enum_bc_cols + other_cols]

    return pd.DataFrame(summary_data), merged_results_df


def _create_merged_comparison_df(
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    svy_col: str,
    bc_col: str,
    summary_col: str | None,
) -> pd.DataFrame:
    """Create merged dataframe for comparison."""
    # Determine columns to include
    if enumerator:
        svy_summary_cols = [survey_id, enumerator, svy_col]
    else:
        svy_summary_cols = [survey_id, svy_col]
    if backchecker:
        bc_summary_cols = [survey_id, backchecker, bc_col]
    else:
        bc_summary_cols = [survey_id, bc_col]

    if summary_col:
        if summary_col == backchecker:
            summary_cols = [
                c
                for c in backcheck_data.columns
                if backchecker in c and c not in bc_summary_cols
            ]
            bc_summary_cols.extend(
                [c for c in summary_cols if c not in bc_summary_cols]
            )

        else:
            summary_cols = [c for c in survey_data.columns if summary_col in c]
            svy_summary_cols.extend(summary_cols)

    # Remove duplicates
    svy_summary_cols = list(set(svy_summary_cols))
    bc_summary_cols = list(set(bc_summary_cols))

    # Get data for columns
    survey_col_data = survey_data[svy_summary_cols]
    backcheck_col_data = backcheck_data[bc_summary_cols]

    # Merge datasets
    merged_df = pd.merge(survey_col_data, backcheck_col_data, on=survey_id, how="inner")

    return merged_df


def _compare_values(
    row, svy_col: str, bc_col: str, ok_range: str, comparison_condition: str
) -> str:
    """Compare values based on conditions and ranges."""
    if comparison_condition:
        # Handle missing values
        if comparison_condition == IGNORE_MISSING_VALUES:
            if pd.isna(row[svy_col]) or pd.isna(row[bc_col]):
                return "not_compared"

        # Handle values to exclude
        elif DO_NOT_COMPARE_VALUES in str(comparison_condition):
            exclude_values = comparison_condition.split(":")[1].strip().split(",")
            if (
                str(row[svy_col]) in exclude_values
                or str(row[bc_col]) in exclude_values
            ):
                return "not_compared"

        # Handle values to treat as same
        elif TREAT_VALUES_AS_SAME in str(comparison_condition):
            same_values = comparison_condition.split(":")[1].strip().split(",")
            svy_val = str(row[svy_col])
            bc_val = str(row[bc_col])
            if svy_val in same_values and bc_val in same_values:
                return "not_different"

    # Handle ok_ranges
    if ok_range:
        try:
            svy_val = float(row[svy_col])
            bc_val = float(row[bc_col])
            diff = abs(svy_val - bc_val)

            if "%" in ok_range:  # Percentage range
                allowed_diff = float(ok_range.replace("%", "")) / 100 * svy_val
                return "not_different" if diff <= allowed_diff else "different"
            elif "[" in ok_range:  # Range
                min_val, max_val = map(float, ok_range.strip("[]").split(","))
                return "not_different" if min_val <= diff <= max_val else "different"
            else:  # Absolute value
                allowed_diff = float(ok_range)
                return "not_different" if diff <= allowed_diff else "different"
        except (ValueError, TypeError):
            return "not_compared"

    # Default comparison
    return (
        "not_different"
        if str(row[svy_col]).strip() == str(row[bc_col]).strip()
        else "different"
    )


def _calculate_column_summary_stats(
    merged_df: pd.DataFrame,
    column_name: str,
    column_type: int,
    survey_col_data: pd.Series,
    summary_col: str,
) -> list:
    """Calculate summary statistics for a column."""
    data_types_dict = {
        "float64": "Numeric",
        "int64": "Numeric",
        "object": "String",
        "datetime64[ns]": "Date",
    }
    data_type = data_types_dict.get(survey_col_data.dtype.name, "String")

    summary_data = []

    # get corresponding summary column name in merged_df
    if summary_col:
        matching_cols = [col for col in merged_df.columns if summary_col in col]
        summary_col_name = matching_cols[0] if matching_cols else None

        if summary_col_name:
            # Group by summary column
            merged_df = merged_df.rename(columns={summary_col_name: summary_col})
            for group_name, group_df in merged_df.groupby(summary_col):
                stats = _compute_group_stats(
                    group_df, merged_df, summary_col, group_name
                )
                summary_data.append(
                    {
                        "column": column_name,
                        "data type": data_type,
                        "category": column_type,
                        summary_col: group_name,
                        **stats,
                    }
                )
    else:
        # Overall statistics
        stats = _compute_overall_stats(merged_df)
        summary_data.append(
            {
                "column": column_name,
                "data type": data_type,
                "category": column_type,
                **stats,
            }
        )

    return summary_data


def _compute_group_stats(
    group_df: pd.DataFrame, merged_df: pd.DataFrame, summary_col: str, group_name
) -> dict:
    """Compute statistics for a specific group."""
    total_surveys = len(merged_df[merged_df[summary_col] == group_name])
    total_backchecks = len(group_df)
    total_compared = len(group_df[group_df["comparison_result"] != "not_compared"])
    total_different = len(group_df[group_df["comparison_result"] == "different"])
    error_rate = (total_different / total_compared * 100) if total_compared > 0 else 0

    return {
        "# surveys": total_surveys,
        "# backchecks": total_backchecks,
        "# compared": total_compared,
        "# different": total_different,
        "error rate": f"{error_rate:.2f}%",
    }


def _compute_overall_stats(merged_df: pd.DataFrame) -> dict:
    """Compute overall statistics."""
    total_compared = len(merged_df[merged_df["comparison_result"] != "not_compared"])
    total_different = len(merged_df[merged_df["comparison_result"] == "different"])
    error_rate = (total_different / total_compared * 100) if total_compared > 0 else 0

    return {
        "# surveys": len(merged_df),
        "# backchecks": len(merged_df),
        "# compared": total_compared,
        "# different": total_different,
        "error rate": f"{error_rate:.2f}%",
    }


def display_category_error_rates(column_category_summary: pd.DataFrame) -> None:
    """Display error rates for each backcheck category.

    Parameters
    ----------
    column_category_summary : pd.DataFrame
        Summary data for all categories.
    """
    for category in [1, 2, 3]:
        category_summary = column_category_summary[
            column_category_summary["category"] == category
        ]
        if category_summary.shape[0] > 0:
            st.write(f"Backcheck category {category} error rates")
            col1, col2, col3 = st.columns(3)

            category_error_rate = (
                category_summary["# different"].sum()
                / category_summary["# compared"].sum()
            ) * 100

            col1.metric(
                f"Number of category {category} columns",
                len(category_summary["column"].unique()),
            )
            col2.metric(
                f"Number of category {category} values compared",
                category_summary["# compared"].sum(),
            )
            col3.metric(
                f"% of category {category} error rate",
                f"{category_error_rate:.0f}%",
            )
            st.write("")


def display_overview_charts(
    total_backchecks: int,
    backcheck_goal: int,
    num_enumerators_bc: int,
    total_enumerators: int,
) -> None:
    """Display overview charts for backcheck progress.

    Parameters
    ----------
    total_backchecks : int
        Total number of backchecks completed.
    backcheck_goal : int
        Target number of backchecks.
    num_enumerators_bc : int
        Number of enumerators who met backcheck target.
    total_enumerators : int
        Total number of enumerators.
    """
    cl1, cl2, cl3 = st.columns(3)
    chart_colors = ["#35904A", "lightgrey"]

    with cl1:
        if backcheck_goal == 0:
            st.warning("Please set a target for backchecks")
        else:
            # Create donut chart for backcheck progress
            fig = px.pie(
                names=["Backchecked", "Not backchecked"],
                values=[total_backchecks, backcheck_goal - total_backchecks],
                hole=0.6,
                title="% of surveys backchecked",
            )
            fig.update_layout(
                width=400,
                height=350,
                showlegend=False,
                title=dict(
                    xanchor="left",
                    y=0.9,
                    yanchor="top",
                    font=dict(weight="normal"),
                ),
            )
            fig.update_traces(
                textinfo="none",
                marker=dict(colors=chart_colors),
                direction="clockwise",
            )
            fig.add_annotation(
                dict(
                    text=f"{(total_backchecks / backcheck_goal) * 100:.0f}%",
                    x=0.5,
                    y=0.5,
                    font_size=30,
                    showarrow=False,
                )
            )
            st.plotly_chart(fig)

    with cl3:
        # Create pie chart for enumerator backcheck coverage
        if total_enumerators == 0:
            st.write("**% of enumerators backchecked**")
            st.info(
                "Percentage of enumerators backchecked requires an enumerator column. Go to :material/settings: settings above."
            )
        else:
            fig_enum = px.pie(
                names=["Backchecked", "Not backchecked"],
                values=[num_enumerators_bc, total_enumerators - num_enumerators_bc],
                hole=0.6,
                title="% of enumerators backchecked",
            )
            fig_enum.update_layout(
                width=400,
                height=350,
                showlegend=False,
                title=dict(
                    xanchor="left", y=0.9, yanchor="top", font=dict(weight="normal")
                ),
            )
            fig_enum.update_traces(
                textinfo="none",
                marker=dict(colors=chart_colors),
                direction="clockwise",
            )
            fig_enum.add_annotation(
                dict(
                    text=f"{(num_enumerators_bc / total_enumerators) * 100:.0f}%",
                    x=0.5,
                    y=0.5,
                    font_size=30,
                    showarrow=False,
                )
            )
            st.plotly_chart(fig_enum)


def display_error_trends(
    error_trends_summary: pd.DataFrame,
    date: str,
) -> None:
    """Display error trends over time.

    Parameters
    ----------
    error_trends_summary : pd.DataFrame
        Error trends data.
    date : str
        Date column name.
    """
    if error_trends_summary.empty:
        st.write("Error Trends")
        st.info(NO_BACKCHECK_COLUMNS_SET)
        return

    st.subheader("Error Trends")
    trend_cols = st.columns([2, 1])

    date_columns = [col for col in error_trends_summary if date in col]
    if not date_columns:
        st.error(
            f"No columns in the data match the date string '{date}'. Please check your date column name."
        )
        return
    date_col = date_columns[0]
    category_list = error_trends_summary["category"].unique().tolist()

    error_trends_summary[date_col] = pd.to_datetime(error_trends_summary[date_col])

    with trend_cols[0]:
        selected_categories = st.multiselect(
            "Select backcheck categories",
            options=category_list,
            default=category_list,
            key="trend_categories",
        )

    with trend_cols[1]:
        time_period_options = ["Daily"]
        if error_trends_summary[date_col].dt.to_period("W-SUN").nunique() > 1:
            time_period_options.append("Weekly")
        if error_trends_summary[date_col].dt.to_period("M").nunique() > 1:
            time_period_options.append("Monthly")

        time_period = st.selectbox(
            "Select time period",
            options=time_period_options,
            key="time_period",
        )

    if selected_categories:
        trends_df = error_trends_summary[
            error_trends_summary["category"].isin(selected_categories)
        ].copy()
        trends_df["date"] = pd.to_datetime(trends_df[date_col])

        # Filter based on time period
        if time_period == "Weekly":
            trends_df["date"] = trends_df["date"].dt.to_period("W-SUN").dt.start_time
        elif time_period == "Monthly":
            trends_df["date"] = trends_df["date"].dt.to_period("M").astype(str)
        else:
            trends_df["date"] = trends_df["date"].dt.date

        # Calculate error rates
        error_trends_df = (
            trends_df.groupby(["date", "category"])
            .aggregate({"# compared": "sum", "# different": "sum"})
            .reset_index()
        )
        error_trends_df["error_rate"] = (
            error_trends_df["# different"] / error_trends_df["# compared"]
        ) * 100
        error_trends_df["error_rate"] = error_trends_df["error_rate"].fillna(0).round(0)

        # Create line chart
        fig = px.line(
            error_trends_df,
            x="date",
            y="error_rate",
            color="category",
            title=f"{time_period} Error Rate Trends by Category",
            labels={
                "date": "Date",
                "error_rate": "Error Rate (%)",
                "category": "Category",
            },
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Error Rate (%)",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)


def display_statistics_tables(
    enumerator_statistics: pd.DataFrame,
    backchecker_statistics: pd.DataFrame,
    comparison_df: pd.DataFrame,
    enumerator: str | None,
    backchecker: str | None,
) -> None:
    """Display enumerator, backchecker, and comparison statistics.

    Parameters
    ----------
    enumerator_statistics : pd.DataFrame
        Enumerator statistics.
    backchecker_statistics : pd.DataFrame
        Backchecker statistics.
    comparison_df : pd.DataFrame
        Comparison details.
    enumerator : str
        Enumerator column name.
    """
    # Enumerator Statistics
    st.subheader("Enumerator Statistics")
    if enumerator is not None:
        selected_enum_list = st.multiselect(
            "Filter enumerators:",
            enumerator_statistics[enumerator].unique(),
        )

        if selected_enum_list:
            filtered_enumerator_stats = enumerator_statistics[
                enumerator_statistics[enumerator].isin(selected_enum_list)
            ]
        else:
            filtered_enumerator_stats = enumerator_statistics

        st.dataframe(
            filtered_enumerator_stats,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Enumerator statistics require an enumerator column. Go to :material/settings: settings above to select an enumerator column."
        )

    # Backchecker Statistics
    st.subheader("Backchecker Statistics")
    if backchecker is not None:
        selected_bcer_list = st.multiselect(
            "Filter back checkers:",
            backchecker_statistics["Back Checker"].unique(),
        )

        if selected_bcer_list:
            filtered_backchecker_stats = backchecker_statistics[
                backchecker_statistics["Back Checker"].isin(selected_bcer_list)
            ]
        else:
            filtered_backchecker_stats = backchecker_statistics

        st.dataframe(
            filtered_backchecker_stats,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Backchecker statistics require a backchecker column. Go to :material/settings: settings above to select a back checker column."
        )
    st.write("")

    # Comparison Details
    st.subheader("Comparison Details")
    if comparison_df.empty:
        st.info(
            "Backcheck columns not set. Go to :material/settings: settings above to set backcheck columns."
        )
    else:
        selected_var_list = st.multiselect(
            "Select variables to display:",
            comparison_df["variable"].unique(),
        )

        if selected_var_list:
            filtered_comparison_df = comparison_df[
                comparison_df["variable"].isin(selected_var_list)
            ]
        else:
            filtered_comparison_df = comparison_df

        st.dataframe(filtered_comparison_df, use_container_width=True, hide_index=True)


def backchecks_report(
    project_id: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    setting_file: str,
    page_num: int,
) -> None:
    """
    Create a backcheck report for a given survey and backcheck data.

    PARAMS:
    -------
    project_id: str
        Project ID
    survey_data: pd.DataFrame
        Survey data to be used for backcheck report
    backcheck_data: pd.DataFrame
        Backcheck data to be used for backcheck report
    page_num: int
        Page number for the backcheck report

    Returns
    -------
    None
    """
    # Get settings
    (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
        common_cols,
    ) = backcheck_report_settings(
        project_id, survey_data, backcheck_data, setting_file, page_num
    )

    # Check that required options have been selected
    if not survey_key or not survey_id:
        st.info(
            "Please select Survey Key and Survey ID columns in the settings section to generate the backcheck report."
        )
        return

    if backcheck_data.empty:
        st.info("No back check data available")
        return

    # Process duplicate data
    if drop_duplicates and survey_id and date:
        survey_data, backcheck_data = process_duplicate_data(
            survey_data, backcheck_data, survey_id, date, drop_duplicates
        )

    # Merge survey and backcheck data - handle missing optional columns
    survey_cols_for_merge = [survey_id]
    if enumerator and enumerator not in survey_cols_for_merge:
        survey_cols_for_merge.append(enumerator)
    if date and date not in survey_cols_for_merge:
        survey_cols_for_merge.append(date)

    survey_df_bc = survey_data[survey_cols_for_merge].add_prefix("_svy_")
    survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)

    backcheck_cols_for_merge = [survey_id]
    if backchecker and backchecker not in backcheck_cols_for_merge:
        backcheck_cols_for_merge.append(backchecker)
    if date and date not in backcheck_cols_for_merge:
        backcheck_cols_for_merge.append(date)

    backcheck_df_bc = backcheck_data[backcheck_cols_for_merge].add_prefix("_bc_")
    backcheck_df_bc.rename(columns={"_bc_" + survey_id: survey_id}, inplace=True)

    merged_df = pd.merge(survey_df_bc, backcheck_df_bc, on=survey_id, how="inner")

    # Column category selection
    with st.expander(
        "Backcheck columns settings", expanded=False, icon=":material/settings:"
    ):
        # Initialize session state for table data if not already present
        if "column_config_data" not in st.session_state:
            st.session_state.column_config_data = pd.DataFrame(
                columns=["column", "category", "ok_range", "comparison_condition"]
            )

        # Display the table and allow user interaction
        with st.popover(
            "Add a backcheck column",
            icon=":material/add:",
            use_container_width=True,
        ):
            column_name = st.selectbox(
                "column",
                options=common_cols,
                help="Select a column to configure",
                key="column",
            )
            column_type = st.selectbox(
                "category",
                options=[1, 2, 3],
                help="Select the backcheck category of the column",
                key="category",
            )
            ok_range_type = st.selectbox(
                "ok_range",
                options=["None", "absolute value", "range", "percentage"],
                help="Select the type of range condition",
                key="ok_range",
            )
            if ok_range_type == "absolute value":
                absolute_ok_range = st.number_input(
                    label="Absolute Value",
                    min_value=0,
                    help="Enter the absolute value",
                )
                ok_range = f"{absolute_ok_range}"
            elif ok_range_type == "percentage":
                ok_range_percentage = st.number_input(
                    "Percentage", min_value=0, help="Enter a percentage value"
                )
                ok_range = f"{ok_range_percentage}%"
            elif ok_range_type == "range":
                range_min = st.number_input(
                    "Minimum Value",
                    max_value=0,
                    help="Enter the minimum value (less than zero)",
                )
                range_max = st.number_input(
                    "Maximum Value",
                    min_value=0,
                    help="Enter the maximum value (greater than zero)",
                )
                ok_range = f"[{range_min} , {range_max}]"
            else:
                ok_range = ""

            compare_condition = st.selectbox(
                label="comparison_condition",
                options=[
                    "None",
                    "Do not compare missing values or null values",
                    "Do not compare if the values contain:",
                    "Treat these values as the same:",
                ],
                help="Specify any additional conditions",
                key="comparison_condition",
            )
            if compare_condition == "Do not compare if the values contain:":
                contains_condition = st.text_input(
                    "Enter values not to compare separated by a comma",
                    help="Values not to compare if they contain these values",
                )
                comparison_condition = f"{compare_condition} {contains_condition}"
            elif compare_condition == "Treat these values as the same:":
                same_condition = st.text_input(
                    "Enter values separated by a comma",
                    help="Enter values separated by a comma",
                )
                comparison_condition = f"{compare_condition} {same_condition}"
            elif compare_condition == "Do not compare missing values or null values":
                comparison_condition = "ignore_missing_values"
            else:
                comparison_condition = ""

            if st.button("Add Column"):
                new_row = {
                    "column": column_name,
                    "category": column_type,
                    "ok_range": ok_range,
                    "comparison_condition": comparison_condition,
                }
                st.session_state.column_config_data = pd.concat(
                    [
                        st.session_state.column_config_data,
                        pd.DataFrame([new_row]),
                    ],
                    ignore_index=True,
                )

        # Create an editable dataframe
        bc_column_config_df = st.data_editor(
            st.session_state.column_config_data,
            num_rows="dynamic",
            use_container_width=True,
        )

    # Generate the column summary without group value
    if not bc_column_config_df.empty:
        column_category_summary, svy_bc_comparison_df = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator if enumerator else None,
            backchecker=backchecker if backchecker else None,
            summary_col=None,
        )

        # Calculate total backcheck error rate
        if column_category_summary.shape[0] > 0:
            total_backcheck_error_rate = (
                column_category_summary["# different"].sum()
                / column_category_summary["# compared"].sum()
            ) * 100
            st.session_state.total_backcheck_error_rate = total_backcheck_error_rate
        else:
            st.session_state.total_backcheck_error_rate = "n/a"

    else:
        st.info("Configure backcheck columns above.")

    # Overview Statistics
    st.subheader("Overview")
    min_backcheck_rate = st.number_input(
        "Enter a minimum percentage target of surveys backchecked by enumerator e.g. 10%",
        min_value=0,
        max_value=100,
        value=10,
        key="total_surveys_backcheck",
        help="This is the minimum percentage of surveys that have been backchecked by enumerator",
    )

    # Compute and display overview metrics
    (
        total_backchecks,
        backcheck_goal_update,
        num_enumerators_bc,
        total_enumerators,
    ) = compute_backcheck_overview(
        survey_df_bc=survey_df_bc,
        backcheck_df_bc=backcheck_df_bc,
        merged_df=merged_df,
        enumerator=enumerator if enumerator else None,
        backcheck_goal=backcheck_goal,
        min_backcheck_rate=min_backcheck_rate,
    )

    col1, _, col3 = st.columns(3)
    col1.metric("Total number of backchecks", total_backchecks)
    with col3:
        try:
            st.metric(
                "Total backcheck error rate",
                f"{st.session_state.total_backcheck_error_rate:.0f}%",
            )
        except (AttributeError, TypeError, ValueError):
            st.metric("Total backcheck error rate", "n/a")

    # Display overview charts
    display_overview_charts(
        total_backchecks, backcheck_goal_update, num_enumerators_bc, total_enumerators
    )

    # Display category error rates
    if bc_column_config_df.empty:
        st.write("Backcheck category summary")
        st.info(NO_BACKCHECK_COLUMNS_SET)
        st.write("")
    else:
        st.write("")
        display_category_error_rates(column_category_summary)

        # Error trends
        error_trends_category_summary, _ = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator,
            backchecker=backchecker,
            summary_col=date,
        )

        display_error_trends(error_trends_category_summary, date)
        st.write("")

    # Column statistics
    if bc_column_config_df.empty:
        st.write("Column Statistics")
        st.info(NO_BACKCHECK_COLUMNS_SET)
    else:
        st.subheader("Column Statistics")
        st.dataframe(column_category_summary, use_container_width=True, hide_index=True)

    st.write("")

    # Generate statistics for enumerator if enumerator is set
    if not bc_column_config_df.empty and enumerator:
        enumerator_stats_summary, _ = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator if enumerator else None,
            backchecker=backchecker if backchecker else None,
            summary_col=enumerator if enumerator else None,
        )

        # Prepare enumerator statistics
        enumerator_statistics = (
            enumerator_stats_summary.groupby([enumerator])
            .agg(
                {
                    "# surveys": "sum",
                    "# backchecks": "sum",
                    "# compared": "sum",
                    "# different": "sum",
                }
            )
            .reset_index()
        )
        enumerator_statistics["% back checked"] = enumerator_statistics.apply(
            lambda x: f"{(x['# backchecks'] / x['# surveys']) * 100:.2f}%", axis=1
        )
        enumerator_statistics["Error Rate"] = enumerator_statistics.apply(
            lambda x: f"{(x['# different'] / x['# compared']) * 100:.2f}%", axis=1
        )
        enumerator_statistics = enumerator_statistics.rename(
            columns={
                "_svy_" + enumerator: "Enumerator",
                "# backchecks": "# back checked",
                "# compared": "# of values compared",
                "# different": "# of values different",
            }
        )
    else:
        enumerator_statistics = pd.DataFrame()

    # generate statistics for backchecker if backchecker is set
    if not bc_column_config_df.empty and backchecker:
        backchecker_statistics, _ = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator if enumerator else None,
            backchecker=backchecker if backchecker else None,
            summary_col=backchecker if backchecker else None,
        )

        # Prepare backchecker statistics
        bcer_cols = [
            col for col in backchecker_statistics.columns if backchecker in col
        ]
        if not bcer_cols:
            st.error(f"Backchecker column '{backchecker}' not found in data.")
            return
        bcer_col = bcer_cols[0]
        backchecker_statistics = backchecker_statistics.rename(
            columns={
                bcer_col: "Back Checker",
                "# backchecks": "# back checked",
                "# compared": "# values compared",
                "error rate": "Error Rate",
            }
        )
        backchecker_statistics = backchecker_statistics[
            [
                "Back Checker",
                "# back checked",
                "# values compared",
                "# different",
                "Error Rate",
            ]
        ].copy()
    else:
        backchecker_statistics = pd.DataFrame()

    # Display statistics tables
    display_statistics_tables(
        enumerator_statistics=enumerator_statistics,
        backchecker_statistics=backchecker_statistics,
        comparison_df=svy_bc_comparison_df,
        enumerator=enumerator if enumerator else None,
        backchecker=backchecker if backchecker else None,
    )

    st.write("")
