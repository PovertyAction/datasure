<<<<<<< HEAD
<<<<<<< HEAD
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# define function to create duplicates report
def outliers_report(data, page_num) -> None:  # noqa: D417, RUF100
    """
    Function to create a report on survey duplicates
    Args:
=======
import streamlit as st
import pandas as pd
=======
>>>>>>> e2bf5f5 (lint formatting)
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# define function to create duplicates report
def outliers_report(data, page_num) -> None:  # noqa: D417, RUF100
    """
    Function to create a report on survey duplicates
<<<<<<< HEAD
    Args:	
>>>>>>> b597f57 (adding outlier check)
=======
    Args:
>>>>>>> e2bf5f5 (lint formatting)
        data: DataFrame
    Returns:

    """
<<<<<<< HEAD
<<<<<<< HEAD
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")

        numeric_cols = data.select_dtypes(include=["int"]).columns
=======
    
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")

        numeric_cols = data.select_dtypes(include=['int']).columns
>>>>>>> b597f57 (adding outlier check)
=======
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")

        numeric_cols = data.select_dtypes(include=["int"]).columns
>>>>>>> e2bf5f5 (lint formatting)
        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to check for outliers")
<<<<<<< HEAD
<<<<<<< HEAD
        outliers_cols = st.multiselect(
            "Columns", options=numeric_cols, key="outlier_cols"
        )

        st.markdown("### Select survey ID column")
        survey_id = st.selectbox(
            "Survey ID", options=survey_cols, key="survey_id_outliers", index=None
        )

        st.markdown("### Select enumerator ID column")
        enumerator = st.selectbox(
            "Enumerator ID", options=survey_cols, key="enumerator_outliers", index=None
        )

        st.markdown("### Select survey key column")
        survey_key = st.selectbox(
<<<<<<< HEAD
            "Survey Key", options=survey_cols, key="survey_key_outliers", index=None
        )

        st.markdown("### Select date column")
        date = st.selectbox(
            "Date", options=survey_cols, key="date_outliers", index=None
        )

        st.write("---")
        st.markdown("### Outlier Options")

=======
        outliers_cols = st.multiselect("Columns", options=numeric_cols, key="outlier_cols")
=======
        outliers_cols = st.multiselect(
            "Columns", options=numeric_cols, key="outlier_cols"
        )
>>>>>>> e2bf5f5 (lint formatting)

        st.markdown("### Select survey ID column")
        survey_id = st.selectbox(
            "Survey ID", options=survey_cols, key="survey_id_outliers", index=None
        )

        st.markdown("### Select enumerator ID column")
        enumerator = st.selectbox(
            "Enumerator ID", options=survey_cols, key="enumerator_outliers", index=None
        )

        st.markdown("### Select survey key column")
        survey_key = st.selectbox(  # noqa: F841
=======
>>>>>>> a27188c (adding default values and views)
            "Survey Key", options=survey_cols, key="survey_key_outliers", index=None
        )

        st.markdown("### Select date column")
        date = st.selectbox(
            "Date", options=survey_cols, key="date_outliers", index=None
        )

        st.write("---")
        st.markdown("### Outlier Options")
<<<<<<< HEAD
        
>>>>>>> b597f57 (adding outlier check)
=======

>>>>>>> e2bf5f5 (lint formatting)
        outlier_method = st.radio(
            "Select your preferred method for outlier detection:",
            options=["Interquartile Range (IQR)", "Standard Deviation (SD)"],
        )

        if outlier_method == "Standard Deviation (SD)":
<<<<<<< HEAD
<<<<<<< HEAD
            sd_value = st.number_input(
                "Number of Standard Deviations:", value=3, key="sd_value_outliers"
            )
        else:
            iqr_value = st.number_input(  # noqa: F841
                "IQR Value:", value=1.5, key="iqr_value_outliers"
            )
=======
            sd_value = st.number_input("Number of Standard Deviations:", value = 3, key="sd_value_outliers")
        else:
            iqr_value = st.number_input("IQR Value:", value = 1.5, key="iqr_value_outliers")
>>>>>>> b597f57 (adding outlier check)
=======
            sd_value = st.number_input(
                "Number of Standard Deviations:", value=3, key="sd_value_outliers"
            )
        else:
            iqr_value = st.number_input(  # noqa: F841
                "IQR Value:", value=1.5, key="iqr_value_outliers"
            )
>>>>>>> e2bf5f5 (lint formatting)

        # add button for saving settings
        st.write("---")
        st.write("Save settings")
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
        save_settings = st.button("Save settings", key="save_settings_outliers")  # noqa: F841

    col1, col2 = st.columns(2)

    # Check that required options have been selected. If not, display a info message
    if not all(
        [outliers_cols, survey_id, enumerator, survey_key, date, outlier_method]
    ):
        st.info("Please select all required options to generate the outliers report")
        return
=======
        save_settings = st.button("Save settings", key="save_settings_duplicates")
=======
        save_settings = st.button("Save settings", key="save_settings_outliers")
>>>>>>> c8a436c (adding default values from config page)

=======
        save_settings = st.button("Save settings", key="save_settings_outliers")  # noqa: F841
>>>>>>> e2bf5f5 (lint formatting)

    col1, col2 = st.columns(2)
>>>>>>> b597f57 (adding outlier check)

    # Check that required options have been selected. If not, display a info message
    if not all(
        [outliers_cols, survey_id, enumerator, survey_key, date, outlier_method]
    ):
        st.info("Please select all required options to generate the outliers report")
        return

    with col1:
        # Define bounds
        series = data[outliers_cols].dropna()
        total_count = len(series)

        if outlier_method == "Interquartile Range (IQR)":
            Q1 = series.quantile(0.25)
            Q3 = series.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
        elif outlier_method == "Standard Deviation (SD)":
            mean = series.mean()
            std_dev = series.std()
            lower_bound = mean - sd_value * std_dev
            upper_bound = mean + sd_value * std_dev

        # Find outliers
        outliers = series[(series < lower_bound) | (series > upper_bound)]
        outliers_df = data[data[outliers_cols].isin(outliers)]

        # Prepare data for the table
<<<<<<< HEAD
<<<<<<< HEAD
        table_data = outliers_df[[survey_id, enumerator]].copy()
=======
        table_data = outliers_df[[survey_id, enum_id]].copy()
>>>>>>> b597f57 (adding outlier check)
=======
        table_data = outliers_df[[survey_id, enumerator]].copy()
>>>>>>> c8a436c (adding default values from config page)
        table_data["variable_value"] = outliers_df[outliers_cols].round(2)
        table_data["mean"] = round(series.mean(), 2)
        table_data["lower_bound"] = round(lower_bound, 2)
        table_data["upper_bound"] = round(upper_bound, 2)

        # Display using st.dataframe with proper formatting
        st.dataframe(
            table_data,
            hide_index=True,
            use_container_width=True,
            column_config={
                "variable_value": st.column_config.NumberColumn(
                    "Value", format="%.2f", width="small"
                ),
                "mean": st.column_config.NumberColumn(
                    "Mean", format="%.2f", width="small"
                ),
                "lower_bound": st.column_config.NumberColumn(
                    "Lower Bound", format="%.2f", width="small"
                ),
                "upper_bound": st.column_config.NumberColumn(
                    "Upper Bound", format="%.2f", width="small"
                ),
            },
        )

    with col2:
        # Calculate percentage of outliers
        if outliers_df.empty:
            st.write(
                "No outliers found on this variable according to the selected method and threshold."
            )
        else:
            outlier_count = len(outliers)
            outlier_percentage = (outlier_count / total_count) * 100
            formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

<<<<<<< HEAD
<<<<<<< HEAD
            st.metric(value=formatted_outlier_percentage, label="Share of outliers")
=======
            st.metric(
                value=formatted_outlier_percentage, label="Share of outliers"
            )
>>>>>>> b597f57 (adding outlier check)
=======
            st.metric(value=formatted_outlier_percentage, label="Share of outliers")
>>>>>>> e2bf5f5 (lint formatting)

        fig = go.Figure(
            data=go.Violin(
                y=data[outliers_cols],
                box_visible=True,
                line_color="black",
                meanline_visible=True,
                fillcolor="darkgreen",
                opacity=0.6,
                x0=outliers_cols,
            )
        )

        st.plotly_chart(fig, theme="streamlit", use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:

        def find_variable_patterns(columns):
            """Identify patterns in variable names based on underscores.

            Args:
                columns (list): List of column names.

            Returns
            -------
                dict: Dictionary with base patterns as keys and lists
                of matching columns as values.

            """
            patterns = defaultdict(list)
            for col in columns:
                # Split the column name on underscores
                parts = col.split("_")

                # Identify the base pattern
                base = "_".join(parts[:-1])

                # Append the column to the list for this base pattern
                patterns[base].append(col)

            # Filter out single-variable patterns
            return {k: v for k, v in patterns.items() if len(v) > 1}
<<<<<<< HEAD
<<<<<<< HEAD

=======
        
>>>>>>> b597f57 (adding outlier check)
=======

>>>>>>> e2bf5f5 (lint formatting)
        def show_pattern_selection(df, numeric_columns):
            """Display a pattern selection dropdown for variable names
            and return the selected columns and melted DataFrame.

            Args:
                df (pd.DataFrame): The input DataFrame.
                numeric_columns (list): List of numeric column names.

            Returns
            -------
                tuple: A tuple containing the selected columns and the
                melted DataFrame.

            """
            pattern_groups = find_variable_patterns(numeric_columns)
            if not pattern_groups:
                return None, None

            pattern_options = [
                f"{pattern} ({len(cols)} variables)"
                for pattern, cols in pattern_groups.items()
            ]
            pattern_to_base = {
                display: pattern
                for pattern, display in zip(
                    pattern_groups, pattern_options, strict=False
                )
            }

            selected_pattern = st.selectbox(
                """If you'd like to detect outliers based on a joint
                distribution of several variables (for example,
                same variable corresponding to different household
                members), please select the set of variables""",
                options=sorted(pattern_options),
                help="""Choose a group of related variables to analyze.
                        Only numeric variables are shown.
                        """,
            )

            if selected_pattern:
                base_pattern = pattern_to_base[selected_pattern]
                selected_cols = pattern_groups[base_pattern]

<<<<<<< HEAD
<<<<<<< HEAD
                with st.expander(f"Show selected variables for '{base_pattern}'"):
=======
                with st.expander(
                    f"Show selected variables for '{base_pattern}'"
                ):
>>>>>>> b597f57 (adding outlier check)
=======
                with st.expander(f"Show selected variables for '{base_pattern}'"):
>>>>>>> e2bf5f5 (lint formatting)
                    st.write(", ".join(selected_cols))

                df_subset = df[[survey_id, *selected_cols]]
                df_melted = pd.melt(
                    df_subset,
                    id_vars=[survey_id],
                    value_vars=selected_cols,
                    var_name="name_variable",
                    value_name="new_var",
                )
                return selected_cols, df_melted

            return None, None

        selected_cols, df_melted = show_pattern_selection(data, numeric_cols)

        if selected_cols and df_melted is not None:
            series = df_melted["new_var"].dropna()
            total_count = len(series)

            if outlier_method == "Interquartile Range (IQR)":
                Q1 = series.quantile(0.25)
                Q3 = series.quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
            elif outlier_method == "Standard Deviation (+/-)":
                mean = series.mean()
                std_dev = series.std()
                lower_bound = mean - sd_value * std_dev
                upper_bound = mean + sd_value * std_dev

            outliers = series[(series < lower_bound) | (series > upper_bound)]
            outliers_df = df_melted[df_melted["new_var"].isin(outliers)]

            table_data = outliers_df[[survey_id, "name_variable"]].copy()
            table_data["new_var"] = outliers_df["new_var"].round(2)
            table_data["mean"] = round(series.mean(), 2)
            table_data["lower_bound"] = round(lower_bound, 2)
            table_data["upper_bound"] = round(upper_bound, 2)

            st.dataframe(
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> e2bf5f5 (lint formatting)
                table_data,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "id": st.column_config.Column("ID", width="small"),
                    "name_variable": st.column_config.Column("Variable Name"),
                    "new_var": st.column_config.NumberColumn(
                        "Value", format="%.2f", width="small"
                    ),
                    "mean": st.column_config.NumberColumn(
                        "Mean", format="%.2f", width="small"
                    ),
                    "lower_bound": st.column_config.NumberColumn(
                        "Lower Bound", format="%.2f", width="small"
                    ),
                    "upper_bound": st.column_config.NumberColumn(
                        "Upper Bound", format="%.2f", width="small"
                    ),
                },
            )
<<<<<<< HEAD
=======
                        table_data,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "id": st.column_config.Column("ID", width="small"),
                            "name_variable": st.column_config.Column("Variable Name"),
                            "new_var": st.column_config.NumberColumn(
                                "Value", format="%.2f", width="small"
                            ),
                            "mean": st.column_config.NumberColumn(
                                "Mean", format="%.2f", width="small"
                            ),
                            "lower_bound": st.column_config.NumberColumn(
                                "Lower Bound", format="%.2f", width="small"
                            ),
                            "upper_bound": st.column_config.NumberColumn(
                                "Upper Bound", format="%.2f", width="small"
                            ),
                        },
                    )
            
>>>>>>> b597f57 (adding outlier check)
=======
>>>>>>> e2bf5f5 (lint formatting)

    with col2:
        # Check if outliers_df is not empty
        if outliers_df.empty:
            st.write(
                "No outliers found on this variable according to the selected method and threshold."
            )
        else:
            # Calculate percentage of outliers
            outlier_count = len(outliers)
            outlier_percentage = (outlier_count / total_count) * 100
            formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

<<<<<<< HEAD
<<<<<<< HEAD
            st.metric(value=formatted_outlier_percentage, label="Share of outliers")
=======
            st.metric(
                value=formatted_outlier_percentage, label="Share of outliers"
            )
>>>>>>> b597f57 (adding outlier check)
=======
            st.metric(value=formatted_outlier_percentage, label="Share of outliers")
>>>>>>> e2bf5f5 (lint formatting)

        # Function to find the common prefix
        def common_prefix(strs):
            """Find the longest common prefix string amongst an array
            of strings.

            Args:
                strs (list): List of strings.

            Returns
            -------
                str: The longest common prefix.

            """
            if not strs:
                return ""
            prefix = strs[0]
            for s in strs[1:]:
                while not s.startswith(prefix):
                    prefix = prefix[:-1]
                    if not prefix:
                        return ""
            return prefix

        # Get common prefix
        x_axis_label = common_prefix(selected_cols)

        fig = go.Figure(
            data=go.Violin(
                y=df_melted["new_var"],
                box_visible=True,
                line_color="black",
                meanline_visible=True,
                fillcolor="forestgreen",
                opacity=0.6,
                x0=x_axis_label,
            )
        )

<<<<<<< HEAD
<<<<<<< HEAD
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
=======
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
>>>>>>> b597f57 (adding outlier check)
=======
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
>>>>>>> e2bf5f5 (lint formatting)
