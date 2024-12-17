<<<<<<< HEAD
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st


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
=======
import pandas as pd

import seaborn as sns
import matplotlib.pyplot as plt

import streamlit as st
from datetime import datetime

# define function to create summary report
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
