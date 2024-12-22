import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
import pandas as pd

import plotly.express as px


# define function to create summary report
def descriptive_report(data) -> None:  # noqa: D417, RUF100
    
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
    
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for descriptive statistics")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to include in missing data report")

    st.markdown("## Descriptive Statistics")
                
    # Separate categorical and numeric columns
    cat_vars = data.select_dtypes(include=["object", "category"]).columns
    num_vars = data.select_dtypes(include=["int64", "float64"]).columns

    # Create tabs for categorical and numeric plots
    tab1, tab2 = st.tabs(["Categorical Variables", "Numeric Variables"])

    with tab1:
        st.header("Categorical Variables Distribution")

        # Select-multiple for categorical variables
        selected_cat_vars = st.multiselect(
            "Select Categorical Variables to Visualize",
            options=list(cat_vars),
            default=[],
        )

        for var in selected_cat_vars:
            # Check if the column has any values
            value_counts = data[var].value_counts()
            if not value_counts.empty:
                st.subheader(var)
                # Use Plotly for interactive bar chart
                fig = px.bar(
                    x=value_counts.index,
                    y=value_counts.values,
                    labels={"x": var, "y": "Count"},
                    title=f"Distribution of {var}",
                )
                fig.update_traces(marker_color="forestgreen")
                st.plotly_chart(fig)
            else:
                st.write(f"No data to plot for {var}")

    with tab2:
        st.header("Numeric Variables Distribution")

        # Select-multiple for categorical variables
        selected_num_vars = st.multiselect(
            "Select Categorical Variables to Visualize",
            options=list(num_vars),
            default=[],
        )

        # Plot all numeric variables
        for var in selected_num_vars:
            st.subheader(var)
            fig, ax = plt.subplots(figsize=(6, 3))
            sns.histplot(data[var], kde=True, ax=ax, color="forestgreen")
            ax.set_xlabel(var)
            ax.set_ylabel("Density")
            try:
                ax.set_xlim(0, data[var].max() * 1.2)
            except ValueError:
                ax.set_xlim(0, 100)
            plt.tight_layout()
            st.pyplot(fig)


