<<<<<<< HEAD
import pandas as pd
=======
<<<<<<< HEAD
<<<<<<< HEAD
import matplotlib.pyplot as plt
import seaborn as sns
>>>>>>> 7f9f3dd (restructured files and folders)
import streamlit as st
import pandas as pd


# define function to create summary report
<<<<<<< HEAD
def missing_report(data, page_num) -> None:  # noqa: D417, RUF100
=======
def missing_report(data) -> None:  # noqa: D417, RUF100
<<<<<<< HEAD
>>>>>>> 7f9f3dd (restructured files and folders)
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

<<<<<<< HEAD
<<<<<<< HEAD
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

=======
>>>>>>> 7f9f3dd (restructured files and folders)
=======
        missing_codes_input = st.text_input("Enter missing codes separated by comma eg. -999, -888, 777 etc.") # noqa: F841
        if missing_codes_input:
            missing_codes = missing_codes_input.split(",") # noqa: F841
        missing_labels_input = st.text_input("Enter missing labels separated by comma eg. Missing, Not applicable, Don't know etc.") # noqa: F841
        if missing_labels_input:
            missing_labels = missing_labels_input.split(",")

>>>>>>> d267c72 (replacing missing check with mx version)
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

<<<<<<< HEAD
<<<<<<< HEAD
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
        row_dict["Total Missing (%)"] = (row_dict["Total Missing"] / total_rows) * 100
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
            pct_config = {"Variable": st.column_config.Column(width="medium")}

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
            count_config = {"Variable": st.column_config.Column(width="medium")}

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
=======
    with st.container():
        st.markdown("### Summary")
=======
    # Initialize empty lists to store results
    results = []
>>>>>>> d267c72 (replacing missing check with mx version)

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


<<<<<<< HEAD
                st.pyplot(missing_heatmap)
=======
import pandas as pd

import seaborn as sns
=======
>>>>>>> 240f636 (ruff format and lint pydms/src/checks)
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st


# define function to create summary report
<<<<<<< HEAD
def missing_report(data) -> None: 

	"""
	
	Generates a report on missing data in the dataset. The report includes a summary of missing data, a table showing the percentage of missing values in each column, and an option to inspect variables with missing data.

	Parameters:
		data (pd.DataFrame): The dataset to generate the missing data report for.

	Returns:
		None
	
	"""
	
	with st.expander("settings", icon=":material/settings:"):

		st.markdown("## Configure settings for missing data report")
		
		survey_cols = data.columns

		st.write("---")
		st.markdown("### Select columns to include in missing data report")
        
		miss_cols = st.multiselect("Columns", options = survey_cols)
		if not miss_cols:
			miss_cols = survey_cols

		st.write("---")
		st.markdown("### Report filter options")
		miss_filter_options = ["All", "Top N", "Bottom N", "Greater than", "Less than"]
		miss_filter = st.selectbox("Filter by", options = miss_filter_options)
		if miss_filter and miss_filter is not "All":
			if miss_filter == "Top N" or miss_filter == "Bottom N":
				miss_filter_val = st.number_input("Number of columns", min_value = 1, value = 5)
			else:
				miss_filter_val = st.number_input("Percentage", min_value = 0, max_value = 100, value = 10)
        
	st.markdown("## Missing data")
	
	with st.container():
	
		st.markdown("### Summary")

		col_metric, row_metric, miss_metric, no_miss_metric, some_miss_metric, all_miss_metric = st.columns(6)
		# show number of columns
		col_metric.metric(label = "Columns", value = len(miss_cols), border = True)
		# show number of rows
		row_metric.metric(label = "Rows", value = len(data), border = True)
		# show percentage of missing values
		miss_metric_val = data.isnull().sum().sum()/(len(data.columns)*len(data))
		miss_metric.metric(label = "Missing", value = round(miss_metric_val * 100, 2), border = True)
		# show number of columns with no missing values
		no_miss_metric_val = len(data.columns) - len(data.columns[data.isnull().sum() > 0])
		no_miss_metric.metric(label = "No missing", value = no_miss_metric_val, border = True)
		# show number of columns with some missing values
		some_miss_metric_val = len(data.columns[data.isnull().sum() > 0])
		some_miss_metric.metric(label = "Some missing", value = some_miss_metric_val, border = True)
		# show number of columns with all missing values
		all_miss_metric_val = len(data.columns[data.isnull().sum() == len(data)])
		all_miss_metric.metric(label = "All missing", value = all_miss_metric_val, border = True)


	miss_table, miss_inspect = st.columns((0.3, 0.7))

	with miss_table:

		with st.container(border = True):
		
			st.markdown("### Missing data by column")

			# for each column, show the percentage of missing values
			missing_data = data.isnull().sum()/len(data)
			# sort data from highest to lowest
			missing_data = missing_data.sort_values(ascending = False)
			# rename columns as columns and missing values
			missing_data = missing_data.rename_axis('columns').reset_index(name='% missing')
			st.data_editor(
				missing_data, hide_index=True,
				column_config = {
					"% missing": st.column_config.ProgressColumn(
						label = "% missing", 
						help = "Percentage of missing values in the column",
						min_value = 0,
						max_value = 1.0
					),
				} 
			)

	with miss_inspect:

		with st.container(border = True):

			st.markdown("### Inspect variables with missing data")

			inspect_cols = st.multiselect("Select columns to inspect", options = miss_cols)

			st.write("---")

			if inspect_cols:
			
				# count the number columns selected
				num_cols = len(inspect_cols)

				st.write(f"Inspecting {num_cols} columns")

				inspect_vars_mc1, inspect_vars_mc2, inspect_vars_mc3 = st.columns(3)

				inspect_vars_mc1.metric(label = "\# of columns", value = num_cols, border = True)
				# total number of missing values
				inspect_vars_mc2.metric(label = "\# of missing values", value = data[inspect_cols].isnull().sum().sum(), border = True)
				# percentage of missing values
				inspect_vars_miss_perc = (data[inspect_cols].isnull().sum().sum()/(len(data)*num_cols)) * 100
				inspect_vars_mc3.metric(label = "% of missing values", value = f'{round(inspect_vars_miss_perc, 2)}%', border = True)

				if num_cols == 1:
				
					st.write("---")
					st.markdown(f"### Missing data correlation for {inspect_cols}")

					# create a table showing the correlation between missing values of selected column and all other columns, sort data from highest to lowest
					missing_data_corr = data.isnull().corr()[inspect_cols[0]].sort_values(ascending = False)

					st.data_editor(
						missing_data_corr, hide_index=False,
						column_config = {
							inspect_cols[0]: st.column_config.ProgressColumn(
								label = inspect_cols[0], 
								help = "Correlation between missing values in selected column and other columns",
								min_value = -1,
								max_value = 1.0
							),
						} 
					)

				elif num_cols > 1:

					st.write("---")
					st.markdown("### Missing data correlation for selected columns")

					# create a table showing the correlation between missing values of selected columns and all other columns, sort data from highest to lowest
					missing_data_corr = data[inspect_cols].isnull().corr()
					missing_heatmap = plt.figure(figsize=(6, 4))
					sns.heatmap(data = missing_data_corr, cmap = "rocket", annot = True)

					st.pyplot(missing_heatmap)
>>>>>>> ad3f479 (added summary report)
=======
def missing_report(data) -> None:  # noqa: D417
=======
>>>>>>> c350dfc (linter clean-up)
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

    with st.container():
        st.markdown("### Summary")

        (
            col_metric,
            row_metric,
            miss_metric,
            no_miss_metric,
            some_miss_metric,
            all_miss_metric,
        ) = st.columns(6)
        # show number of columns
        col_metric.metric(label="Columns", value=len(miss_cols), border=True)
        # show number of rows
        row_metric.metric(label="Rows", value=len(data), border=True)
        # show percentage of missing values
        miss_metric_val = data.isnull().sum().sum() / (len(data.columns) * len(data))
        miss_metric.metric(
            label="Missing", value=round(miss_metric_val * 100, 2), border=True
        )
        # show number of columns with no missing values
        no_miss_metric_val = len(data.columns) - len(
            data.columns[data.isnull().sum() > 0]
        )
        no_miss_metric.metric(label="No missing", value=no_miss_metric_val, border=True)
        # show number of columns with some missing values
        some_miss_metric_val = len(data.columns[data.isnull().sum() > 0])
        some_miss_metric.metric(
            label="Some missing", value=some_miss_metric_val, border=True
        )
        # show number of columns with all missing values
        all_miss_metric_val = len(data.columns[data.isnull().sum() == len(data)])
        all_miss_metric.metric(
            label="All missing", value=all_miss_metric_val, border=True
        )

    miss_table, miss_inspect = st.columns((0.3, 0.7))

    with miss_table, st.container(border=True):
        st.markdown("### Missing data by column")

        # for each column, show the percentage of missing values
        missing_data = data.isnull().sum() / len(data)
        # sort data from highest to lowest
        missing_data = missing_data.sort_values(ascending=False)
        # rename columns as columns and missing values
        missing_data = missing_data.rename_axis("columns").reset_index(name="% missing")
        st.data_editor(
            missing_data,
            hide_index=True,
            column_config={
                "% missing": st.column_config.ProgressColumn(
                    label="% missing",
                    help="Percentage of missing values in the column",
                    min_value=0,
                    max_value=1.0,
                ),
            },
        )

    with miss_inspect, st.container(border=True):
        st.markdown("### Inspect variables with missing data")

        inspect_cols = st.multiselect("Select columns to inspect", options=miss_cols)

        st.write("---")

        if inspect_cols:
            # count the number columns selected
            num_cols = len(inspect_cols)

            st.write(f"Inspecting {num_cols} columns")

            inspect_vars_mc1, inspect_vars_mc2, inspect_vars_mc3 = st.columns(3)

            inspect_vars_mc1.metric(label=r"\# of columns", value=num_cols, border=True)
            # total number of missing values
            inspect_vars_mc2.metric(
                label=r"\# of missing values",
                value=data[inspect_cols].isnull().sum().sum(),
                border=True,
            )
            # percentage of missing values
            inspect_vars_miss_perc = (
                data[inspect_cols].isnull().sum().sum() / (len(data) * num_cols)
            ) * 100
            inspect_vars_mc3.metric(
                label="% of missing values",
                value=f"{round(inspect_vars_miss_perc, 2)}%",
                border=True,
            )

            if num_cols == 1:
                st.write("---")
                st.markdown(f"### Missing data correlation for {inspect_cols}")

                # create a table showing the correlation between missing values
                # of selected column and all other columns, sort data from
                # highest to lowest
                missing_data_corr = (
                    data.isnull().corr()[inspect_cols[0]].sort_values(ascending=False)
                )

                st.data_editor(
                    missing_data_corr,
                    hide_index=False,
                    column_config={
                        inspect_cols[0]: st.column_config.ProgressColumn(
                            label=inspect_cols[0],
                            help="Correlation between missing values in selected column and other columns",
                            min_value=-1,
                            max_value=1.0,
                        ),
                    },
                )

<<<<<<< HEAD
                if num_cols == 1:
                    st.write("---")
                    st.markdown(f"### Missing data correlation for {inspect_cols}")

                    # create a table showing the correlation between missing values of selected column and all other columns, sort data from highest to lowest
                    missing_data_corr = (
                        data.isnull()
                        .corr()[inspect_cols[0]]
                        .sort_values(ascending=False)
                    )

                    st.data_editor(
                        missing_data_corr,
                        hide_index=False,
                        column_config={
                            inspect_cols[0]: st.column_config.ProgressColumn(
                                label=inspect_cols[0],
                                help="Correlation between missing values in selected column and other columns",
                                min_value=-1,
                                max_value=1.0,
                            ),
                        },
                    )

                elif num_cols > 1:
                    st.write("---")
                    st.markdown("### Missing data correlation for selected columns")

                    # create a table showing the correlation between missing values of selected columns and all other columns, sort data from highest to lowest
                    missing_data_corr = data[inspect_cols].isnull().corr()
                    missing_heatmap = plt.figure(figsize=(6, 4))
                    sns.heatmap(data=missing_data_corr, cmap="rocket", annot=True)

                    st.pyplot(missing_heatmap)
>>>>>>> 240f636 (ruff format and lint pydms/src/checks)
=======
            elif num_cols > 1:
                st.write("---")
                st.markdown("### Missing data correlation for selected columns")

                # create a table showing the correlation between missing
                # values of selected columns and all other columns, sort data
                # from highest to lowest
                missing_data_corr = data[inspect_cols].isnull().corr()
                missing_heatmap = plt.figure(figsize=(6, 4))
                sns.heatmap(data=missing_data_corr, cmap="rocket", annot=True)

                st.pyplot(missing_heatmap)
>>>>>>> a88010e (simplify SIM117 checks)
<<<<<<< HEAD
>>>>>>> 7f9f3dd (restructured files and folders)
=======
=======
    st.write(
        "Note: The calculations for 'Not Coded' includes values of ' . ', 'NA' and empty cells."
    )
>>>>>>> 2a401cd (replacing missing check with mx version)
>>>>>>> d267c72 (replacing missing check with mx version)
