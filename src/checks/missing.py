import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
import pandas as pd


# define function to create summary report
def missing_report(data) -> None:  # noqa: D417, RUF100
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

        missing_codes_input = st.text_input("Enter missing codes separated by comma eg. -999, -888, 777 etc.") # noqa: F841
        if missing_codes_input:
            missing_codes = missing_codes_input.split(",") # noqa: F841
        missing_labels_input = st.text_input("Enter missing labels separated by comma eg. Missing, Not applicable, Don't know etc.") # noqa: F841
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

    # Initialize empty lists to store results
    results = []

    for column in data.columns:
        # Count not coded missing (NA, empty spaces, empty strings)
        not_coded = (
            data[column].isna().sum()
            + (data[column] == " ").sum()
            + (data[column] == "").sum()
        )

        # Initialize dictionary for the row
        row_dict = {
            "Variable": column,
            "Total Missing": not_coded,  # Initialize with not_coded
            "Not Coded": not_coded,
        }

        # Add counts and update total for each code/label pair
        for code, label in zip(missing_codes, missing_labels, strict=False):
            count = (data[column] == code).sum()
            row_dict[f"{label} ({code})"] = count
            row_dict["Total Missing"] += count  # Add to total

        # Calculate and add percentages
        total_rows = len(data)
        row_dict["Total Missing (%)"] = (
            row_dict["Total Missing"] / total_rows
        ) * 100
        row_dict["Not Coded (%)"] = (not_coded / total_rows) * 100

        # Add percentages for each code/label pair
        for code, label in zip(missing_codes, missing_labels, strict=False):
            count = row_dict[f"{label} ({code})"]
            row_dict[f"{label} ({code}) (%)"] = (count / total_rows) * 100

        results.append(row_dict)

    # Create DataFrame from results
    missing_data = pd.DataFrame(results)

    # Create the slider
    missing_threshold = st.slider(
        "Variables with % of missing values above:", 0, 100, 1
    )

    # Filter based on total missing percentage
    missing_data_filtered = missing_data[
        missing_data["Total Missing (%)"] >= missing_threshold
    ]

    if not missing_data_filtered.empty:
        # Create two tabs
        tab1, tab2 = st.tabs(["Percentages", "Total Count"])

        with tab1:
            # Create list of columns for percentages
            pct_columns = [
                "Variable",
                "Total Missing (%)",
                "Not Coded (%)",
            ]
            pct_columns.extend(
                [
                    f"{label} ({code}) (%)"
                    for code, label in zip(missing_codes, missing_labels, strict=False)
                ]
            )

            # Display percentages DataFrame
            percentages_df = missing_data_filtered[pct_columns]

            # Create column config for percentages
            pct_config = {
                "Variable": st.column_config.Column(width="medium")
            }

            # Add percentage format for all percentage columns
            for col in pct_columns[1:]:  # Skip 'Column'
                pct_config[col] = st.column_config.NumberColumn(
                    format="%.1f%%", width="small"
                )

            st.dataframe(
                percentages_df,
                hide_index=True,
                use_container_width=True,
                column_config=pct_config,
            )

        with tab2:
            # Create list of columns for counts
            count_columns = ["Variable", "Total Missing", "Not Coded"]
            count_columns.extend(
                [
                    f"{label} ({code})"
                    for code, label in zip(missing_codes, missing_labels, strict=False)
                ]
            )

            # Display counts DataFrame
            counts_df = missing_data_filtered[count_columns]

            # Create column config for counts
            count_config = {
                "Variable": st.column_config.Column(width="medium")
            }

            # Add number format for all count columns
            for col in count_columns[1:]:  # Skip 'Column'
                count_config[col] = st.column_config.NumberColumn(
                    format="%d", width="small"
                )

            st.dataframe(
                counts_df,
                hide_index=True,
                use_container_width=True,
                column_config=count_config,
            )

    else:
        st.write(
            "There are no variables with more than",
            missing_threshold,
            "% missing values.",
        )


    st.write(
        "Note: The calculations for 'Not Coded' includes values of ' . ', 'NA' and empty cells."
    )
