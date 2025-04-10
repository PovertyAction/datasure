import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


# define function to create summary report
def descriptive_report(data, page_num) -> None:  # noqa: D417, RUF100
    """
    Visualize the distribution of categorical and numeric variables in the dataframe.

    Parameters
    ----------
    data : pd.DataFrame
        The input dataframe to visualize.

    Returns
    -------
    None

    """
    selected_cols = []

    with st.expander("Descriptive Statistics Settings", expanded=True):
        st.markdown("## Configure settings for descriptive statistics")

        survey_cols = data.columns

        # Let users select columns for analysis (max 10)
        selected_cols = st.multiselect(
            "Select columns to include in descriptive statistics (maximum 10)",
            options=list(survey_cols),
            default=[],
            max_selections=10,
        )

    # Check if any columns were selected
    if not selected_cols:
        st.warning(
            "No columns selected. Please select up to 10 columns in the settings above."
        )
        return

    # Filter data to only include selected columns
    data_filtered = data[selected_cols]

    # Separate categorical and numeric columns
    cat_vars = data_filtered.select_dtypes(
        include=["object", "category"]
    ).columns.tolist()
    num_vars = data_filtered.select_dtypes(
        include=["int64", "float64"]
    ).columns.tolist()

    # For numeric variables that are in selected_cols but not in num_vars or cat_vars
    extra_cols = [
        col for col in selected_cols if col not in cat_vars and col not in num_vars
    ]
    if extra_cols:
        # Try to identify if these should be numeric or categorical
        for col in extra_cols:
            try:
                # Convert to numeric if possible
                data_filtered[col] = pd.to_numeric(data_filtered[col])
                num_vars.append(col)
            except:
                # Otherwise treat as categorical
                cat_vars.append(col)

    # Create tabs for categorical and numeric plots
    tab1, tab2 = st.tabs(["Categorical Variables", "Numeric Variables"])

    with tab1:
        st.header("Categorical Variables Analysis")

        if len(cat_vars) == 0:
            st.info("No categorical variables among the selected columns.")
        else:
            st.write(
                f"Displaying analyses for {len(cat_vars)} selected categorical variables."
            )

            # MOVED UP: Selection between one-way and two-way table at the beginning
            analysis_type = st.radio(
                "Analysis type for all categorical variables:",
                options=["One-way Table", "Two-way Table (Cross-tabulation)"],
                key="cat_analysis_type",
                horizontal=True,
            )

            # For two-way tables, select a variable for cross-tabulation
            cross_tab_col = None
            if analysis_type == "Two-way Table (Cross-tabulation)":
                # Get all columns from the original dataset for cross-tabulation
                all_cols = data.columns.tolist()

                cross_tab_col = st.selectbox(
                    "Cross-tabulate all categorical variables with:",
                    options=all_cols,
                    key="cat_crosstab_global",
                )

            # Process each categorical variable
            for var in cat_vars:
                st.subheader(var)

                if analysis_type == "One-way Table":
                    # Calculate value counts
                    value_counts = data_filtered[var].value_counts().reset_index()
                    value_counts.columns = [var, "Count"]
                    value_counts["Percentage"] = (
                        value_counts["Count"] / value_counts["Count"].sum() * 100
                    ).round(2)

                    # Display table
                    st.dataframe(value_counts, width=600)

                else:  # Two-way Table (Cross-tabulation)
                    # Skip cross-tabulation with itself
                    if var == cross_tab_col:
                        st.warning(
                            f"Cannot cross-tabulate '{var}' with itself. Please select a different variable for cross-tabulation."
                        )
                        continue

                    # Check if cross_tab_col is in the data
                    if cross_tab_col not in data.columns:
                        st.error(
                            f"Selected column '{cross_tab_col}' not found in dataset"
                        )
                        continue

                    # Generate cross-tabulation
                    try:
                        # Ensure both variables are in the filtered data
                        if cross_tab_col not in data_filtered.columns:
                            # Create a temporary df with both columns
                            temp_df = pd.DataFrame(
                                {
                                    var: data_filtered[var],
                                    cross_tab_col: data[cross_tab_col],
                                }
                            )

                            cross_tab = pd.crosstab(
                                temp_df[var],
                                temp_df[cross_tab_col],
                                margins=True,
                                margins_name="Total",
                            )
                        else:
                            cross_tab = pd.crosstab(
                                data_filtered[var],
                                data_filtered[cross_tab_col],
                                margins=True,
                                margins_name="Total",
                            )

                        st.write(f"Cross-tabulation of '{var}' with '{cross_tab_col}'")
                        st.dataframe(cross_tab)
                    except Exception as e:
                        st.error(f"Error creating cross-tabulation: {e!s}")

                st.markdown("---")

    with tab2:
        st.header("Numeric Variables Analysis")

        if len(num_vars) == 0:
            st.info("No numeric variables among the selected columns.")
        else:
            st.write(
                f"Displaying analyses for {len(num_vars)} selected numeric variables."
            )

            # Global settings for numeric variables
            col1, col2 = st.columns(2)

            with col1:
                treat_as_global = st.radio(
                    "Treat all numeric variables as:",
                    options=["Continuous", "Categorical"],
                    key="num_treat_global",
                    horizontal=True,
                )

            with col2:
                if treat_as_global == "Continuous":
                    display_type_global = st.radio(
                        "Display type for all numeric variables:",
                        options=["Table", "Graph"],
                        key="num_display_global",
                        horizontal=True,
                    )
                else:
                    # For categorical, only show Table options
                    display_type_global = "Table"

            # For Table options, choose table type (oneway or twoway)
            table_type_global = None
            cross_tab_col_num = None

            if display_type_global == "Table":
                table_type_global = st.radio(
                    "Table type for all numeric variables:",
                    options=["One-way Table", "Two-way Table (Cross-tabulation)"],
                    key="num_table_global",
                    horizontal=True,
                )

                # For two-way tables, set up cross-tabulation
                if table_type_global == "Two-way Table (Cross-tabulation)":
                    # Get all columns from the original df for cross-tabulation
                    all_cols = data.columns.tolist()

                    cross_tab_col_num = st.selectbox(
                        "Cross-tabulate all numeric variables with:",
                        options=all_cols,
                        key="num_crosstab_global",
                    )

            # For continuous variables with statistics
            stats_to_show_global = None
            if (
                treat_as_global == "Continuous"
                and display_type_global == "Table"
                and table_type_global == "One-way Table"
            ):
                # Allow users to select which statistics to display for all variables
                stats_to_show_global = st.multiselect(
                    "Statistics to display for all numeric variables:",
                    options=[
                        "Mean",
                        "Median",
                        "Standard Deviation",
                        "Min",
                        "Max",
                        "Quartiles",
                    ],
                    default=["Mean", "Median", "Standard Deviation", "Min", "Max"],
                    key="stats_global",
                )

            # Process each numeric variable
            for var in num_vars:
                st.subheader(var)

                # For Table option
                if display_type_global == "Table":
                    if table_type_global == "One-way Table":
                        if treat_as_global == "Continuous":
                            # Calculate statistics based on global selection
                            stats_dict = {}

                            if "Mean" in stats_to_show_global:
                                stats_dict["Mean"] = data_filtered[var].mean()
                            if "Median" in stats_to_show_global:
                                stats_dict["Median"] = data_filtered[var].median()
                            if "Standard Deviation" in stats_to_show_global:
                                stats_dict["Standard Deviation"] = data_filtered[
                                    var
                                ].std()
                            if "Min" in stats_to_show_global:
                                stats_dict["Min"] = data_filtered[var].min()
                            if "Max" in stats_to_show_global:
                                stats_dict["Max"] = data_filtered[var].max()
                            if "Quartiles" in stats_to_show_global:
                                q1 = data_filtered[var].quantile(0.25)
                                q3 = data_filtered[var].quantile(0.75)
                                stats_dict["25% Quartile"] = q1
                                stats_dict["75% Quartile"] = q3
                                stats_dict["IQR"] = q3 - q1

                            # Display statistics as table
                            stats_df = pd.DataFrame(
                                stats_dict.items(), columns=["Statistic", "Value"]
                            )
                            st.dataframe(stats_df, width=600)
                        else:
                            # For categorical one-way table
                            cat_values = data_filtered[var].astype("category")
                            value_counts = cat_values.value_counts().reset_index()
                            value_counts.columns = [var, "Count"]
                            value_counts["Percentage"] = (
                                value_counts["Count"]
                                / value_counts["Count"].sum()
                                * 100
                            ).round(2)
                            st.dataframe(value_counts, width=600)

                    else:  # Two-way Table (Cross-tabulation)
                        # Skip cross-tabulation with itself
                        if var == cross_tab_col_num:
                            st.warning(
                                f"Cannot cross-tabulate '{var}' with itself. Please select a different variable for cross-tabulation."
                            )
                            continue

                        # Check if cross_tab_col_num is in the data
                        if cross_tab_col_num not in data.columns:
                            st.error(
                                f"Selected column '{cross_tab_col_num}' not found in dataset"
                            )
                            continue

                        # Generate cross-tabulation
                        try:
                            # Ensure both variables are in the filtered data
                            if cross_tab_col_num not in data_filtered.columns:
                                # Create a temporary df with both columns
                                temp_df = pd.DataFrame(
                                    {
                                        var: data_filtered[var],
                                        cross_tab_col_num: data[cross_tab_col_num],
                                    }
                                )

                                cross_tab = pd.crosstab(
                                    temp_df[var],
                                    temp_df[cross_tab_col_num],
                                    margins=True,
                                    margins_name="Total",
                                )
                            else:
                                cross_tab = pd.crosstab(
                                    data_filtered[var],
                                    data_filtered[cross_tab_col_num],
                                    margins=True,
                                    margins_name="Total",
                                )

                            st.write(
                                f"Cross-tabulation of '{var}' with '{cross_tab_col_num}'"
                            )
                            st.dataframe(cross_tab)
                        except Exception as e:
                            st.error(f"Error creating cross-tabulation: {e!s}")

                # For Graph option - only available for continuous variables
                elif display_type_global == "Graph":
                    # Creating histogram with green color scheme
                    try:
                        fig, ax = plt.subplots(figsize=(10, 6))

                        counts, bins, patches = ax.hist(
                            data_filtered[var].dropna(),
                            bins=12,
                            color="#4C9A4C",
                            edgecolor="white",
                            alpha=0.7,
                        )

                        # Set labels and title
                        ax.set_xlabel(var)
                        ax.set_title(f"Distribution of {var}")

                        # Remove top and right spines
                        ax.spines["top"].set_visible(False)
                        ax.spines["right"].set_visible(False)

                        st.pyplot(fig)

                        # Calculate and display basic statistics alongside histogram
                        basic_stats = {
                            "Mean": data_filtered[var].mean(),
                            "Median": data_filtered[var].median(),
                            "Standard Deviation": data_filtered[var].std(),
                            "Min": data_filtered[var].min(),
                            "Max": data_filtered[var].max(),
                        }
                        stats_df = pd.DataFrame(
                            basic_stats.items(), columns=["Statistic", "Value"]
                        )
                        st.dataframe(stats_df, width=600)
                    except Exception as e:
                        st.error(f"Error creating histogram: {e!s}")

                st.markdown("---")
