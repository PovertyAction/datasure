import io

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def donut_chart(
    actual_value: int,
    target_value: int = 100,
    title: str = None,
    prefix: str = "",
    suffix: str = "%",
    colours: list = ["#2C5F2D", "#CCCCCC"],
):
    """
    Create a donut chart with the specified parameters.

    Parameters
    ----------
    actual_value: int
        The value to display (e.g., percentage complete)
    target_value: int
        The maximum value (default 100)
    title: str
        Title of the chart
    prefix: str
        Prefix to add to actual value eg "$"
    suffix: str
        Suffix to add to actual value eg "%" or "K"
    colours: list
        List of colour codes for the chart segments

    Returns
    -------
    fig: matplotlib figure
        The created figure
    """
    fig = plt.figure(
        figsize=(2, 2), dpi=100, facecolor="#FFFFFF", constrained_layout=True
    )
    ax = fig.add_subplot(1, 1, 1)

    if title:
        ax.set_title(title, fontsize=14)

    # Create the pie chart
    pie = ax.pie(
        [actual_value, target_value - actual_value],
        colors=colours,
        startangle=90,
        labeldistance=1.15,
        counterclock=False,
    )

    # Make the background segment semi-transparent
    pie[0][1].set_alpha(0.4)

    # Add center circle to create donut
    centre_circle = plt.Circle((0, 0), 0.7, fc="#FFFFFF")
    fig.gca().add_artist(centre_circle)

    # Add center text
    centre_text = f"{prefix}{actual_value}{suffix}"
    ax.text(
        0,
        0,
        centre_text,
        horizontalalignment="center",
        verticalalignment="center",
        fontsize=20,
        fontweight="bold",
        color=colours[0],
    )

    # Remove axes
    ax.axis("equal")
    plt.axis("off")

    return fig


def fig_to_streamlit(fig):
    """Convert a matplotlib figure to a format Streamlit can display"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    return buf


#### Survey Progress ###


def progress_report(data, page_num) -> None:
    """Display progress report

    PARAMS:
    -------

    data: pd.DataFrame : data to display
    page_num: int : page number

    Returns
    -------
    None
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to include in summary report")

        meta_col, enum_col, agg_col = st.columns(spec=3, border=True)

        with meta_col:
            # get date column name from dataset & get index
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_date_index = survey_cols.get_loc(default_date)
            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_progress",
                index=default_date_index,
            )
            data["date_only"] = data[date].dt.date

        with enum_col:
            by = st.selectbox(
                "Group by",
                options=survey_cols,
                help="Column to group summary report by by",
                key="groupby_progress",
                index=None,
            )

            # get enumerator column name from dataset & get index
            default_enumerator = st.session_state["config_pages"]["Enumerator"][
                page_num - 1
            ]
            default_enumerator_index = survey_cols.get_loc(default_enumerator)
            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_progress",
                index=default_enumerator_index,
            )
            team = st.selectbox(
                "Team",
                options=survey_cols,
                help="Column containing survey team",
                key="team_progress",
                index=None,
            )

        with agg_col:
            # get survey id column name from dataset & get index
            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_id_index = survey_cols.get_loc(default_survey_id)
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="surveyid_progress",
                index=default_survey_id_index,
            )
            # get survey key column name from dataset & get index
            default_survey_key = st.session_state["config_pages"]["Survey KEY"][
                page_num - 1
            ]
            default_survey_key_index = survey_cols.get_loc(default_survey_key)
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                help="Column containing survey key",
                key="surveykey_progress",
                index=default_survey_key_index,
            )

            consent = st.selectbox(
                "Consent",
                options=survey_cols,
                help="Column containing survey consent",
                key="consent_progress",
                index=None,
            )

            if consent:
                consent_options = data[consent].unique().tolist()
                consent_val = st.multiselect(  # noqa: F841
                    "Consent value(s)",
                    options=consent_options,
                    help="Value(s) indicating valid consent",
                    key="consent_val_progress",
                )

            outcome = st.selectbox(
                "Outcome",
                options=survey_cols,
                help="Column containing survey outcome",
                key="outcome_progress",
                index=None,
            )

            if outcome:
                outcome_options = data[outcome].unique().tolist()
                outcome_val = st.multiselect(  # noqa: F841
                    "Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_progress",
                )

        st.write("---")
        st.markdown("### Tracking Options")

        # number of interviews expected
        total_goal = st.number_input(
            "Total goal",
            min_value=0,
            help="Total number of interviews expected",
            key="total_goal_progress",
        )

        # define a save settings button
        save_settings = st.button("Save settings", key="save_settings_progress")  # noqa: F841

    # Add the summary section
    st.markdown("## Survey Summary")

    # Get required data for the summary
    total_submitted = len(data[survey_id].unique())

    # Create metrics row
    met_col1, met_col2 = st.columns(2)

    with met_col1:
        st.metric(
            label="Target Interviews",
            value=total_goal
            if "total_goal_progress" in st.session_state
            and st.session_state["total_goal_progress"] > 0
            else "N/A",
        )

    with met_col2:
        st.metric(label="Total Submitted Interviews", value=total_submitted)

    # Create charts row
    chart_cols = st.columns([1, 1])

    # Consent chart
    with chart_cols[0]:
        if (
            consent
            and "consent_val_progress" in st.session_state
            and len(st.session_state["consent_val_progress"]) > 0
        ):
            # Count total valid consents
            valid_consent_count = data[
                data[consent].isin(st.session_state["consent_val_progress"])
            ][survey_id].nunique()
            consent_percentage = (
                round((valid_consent_count / total_submitted * 100), 0)
                if total_submitted > 0
                else 0
            )

            # Create matplotlib donut chart for consent
            st.markdown(
                "<p font-size: 16px;'>Valid Consent</p>", unsafe_allow_html=True
            )
            fig = donut_chart(
                actual_value=int(consent_percentage),
                suffix="%",
                colours=["#2C5F2D", "#CCCCCC"],
            )
            # Use use_column_width parameter to make image responsive to column width
            st.image(fig_to_streamlit(fig), use_container_width=False)
            plt.close(fig)  # Close the figure to free memory
        else:
            st.info("Consent data not configured")

    # Outcome chart
    with chart_cols[1]:
        if (
            outcome
            and "outcome_val_progress" in st.session_state
            and len(st.session_state["outcome_val_progress"]) > 0
        ):
            # Count total completed surveys
            completed_count = data[
                data[outcome].isin(st.session_state["outcome_val_progress"])
            ][survey_id].nunique()
            completion_percentage = (
                round((completed_count / total_submitted * 100), 0)
                if total_submitted > 0
                else 0
            )

            # Create matplotlib donut chart for outcome
            st.markdown(
                "<p font-size: 16px;'>Survey Completion</p>", unsafe_allow_html=True
            )
            fig = donut_chart(
                actual_value=int(completion_percentage),
                suffix="%",
                colours=["#2C5F2D", "#CCCCCC"],
            )
            # Use use_column_width parameter to make image responsive to column width
            st.image(fig_to_streamlit(fig), use_container_width=False)
            plt.close(fig)  # Close the figure to free memory
        else:
            st.info("Outcome data not configured")

    # Add the Report section
    st.markdown("## Survey Progress Report")

    col1, col2 = st.columns(2)

    # Check that required options have been selected. If not, display a info message
    if not all([survey_id, survey_key, consent, outcome]):
        st.info("Please select all required options to generate the progress report")
        return

    with col1:
        # Add CSS to ensure table width matches selectbox
        st.markdown(
            """
			<style>
				.stDataFrame {
					width: 100%;
				}
				.dataframe {
					width: 100%;
				}
			</style>
		""",
            unsafe_allow_html=True,
        )

        summary = (
            data.groupby(consent, observed=True)[survey_id].nunique().reset_index()
        )
        summary.columns = ["Consent Status", "Unique ID Count"]

        st.table(summary)

        # Modify consent variable - Define values of consent/no consent
        mapping = {1: "Consent", 0: "No Consent"}
        data[consent] = data[consent].map(mapping)

        # Group by 'id' and count unique values of "key"
        unique_counts = data.groupby(survey_id)[survey_key].nunique().reset_index()
        unique_counts.columns = [survey_id, "unique_key_count"]

        # Count unique ids from the new df
        count_unique_ids = unique_counts[survey_id].nunique()

    with col2:
        # Group by 'id' and count unique values of "key"
        unique_counts = data.groupby(survey_id)[survey_key].nunique().reset_index()
        unique_counts.columns = [survey_id, "unique_key_count"]

        # Count unique ids by number of counts from the new df
        count_unique_ids = (
            unique_counts.groupby("unique_key_count").count().reset_index()
        )

        # Define the color scale
        colors = [
            "#2C5F2D",
            "#74AA76",
            "#9ECED7",
            "#4D5E90",
            "#DE9461",
            "#B9ABE6",
            "#E0C97D",
            "#636892",
        ]

        # Create the Plotly figure
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=count_unique_ids.unique_key_count,
                    values=count_unique_ids[survey_id],
                    hole=0.3,
                    marker=dict(colors=colors),
                )
            ]
        )

        # Update the layout
        fig.update_layout(
            title="Unique IDs by number of attempts",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font_color="black",
            font_family="Arial",
            font_size=14,
        )

        st.plotly_chart(fig, theme="streamlit", use_container_width=True)

        # Group by date and count number of IDs
        count_by_date = (
            data.groupby("date_only").size().reset_index(name="num_interviews")
        )

        # Calculate the average of interviews per day
        average_interviews_per_day = count_by_date["num_interviews"].mean()

        # Create the figure with secondary y-axis
        fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Second row with full width for col3
    st.write("")  # Add some space between rows
    col3 = st.container()

    with col3:
        # Create a new DataFrame for the table
        table_data = data[[survey_id, "date_only", consent]].copy()
        table_data["number_of_attempts"] = table_data[survey_id].map(
            unique_counts.set_index(survey_id)["unique_key_count"]
        )

        # Filter box styling
        st.markdown(
            """
            <style>
            .stTextInput input {
                background-color: #f0f2f6;
            }
            </style>
        """,
            unsafe_allow_html=True,
        )

        query = st.text_input("Filter by number of attempts")

        # Filter logic
        if query:
            try:
                query_num = int(query)
                filtered_table = table_data[
                    table_data["number_of_attempts"] >= query_num
                ]
            except ValueError:
                st.warning("Please enter a valid number")
                filtered_table = table_data
        else:
            filtered_table = table_data

        # Display the table with custom formatting
        st.write("Detailed Information Table:")
        st.dataframe(
            filtered_table,
            use_container_width=True,
            hide_index=True,
        )

        st.write(f"Number of entries shown: {len(filtered_table)}")

    # Add time period selection with left-aligned title
    st.markdown(
        """
        <style>
        .left-aligned {
            text-align: left;
            padding-left: 0;
            margin-left: 0;
        }
        </style>
        <h2 class="left-aligned">Interview Progress Over Time</h2>
        """,
        unsafe_allow_html=True,
    )

    time_period = st.radio(
        "Select time period:",
        options=["Day", "Week", "Month"],
        horizontal=True,
        key="time_period_selection",
    )

    # Create a copy of the dataframe with datetime index for resampling
    chart_data = data.copy()
    chart_data[date] = pd.to_datetime(chart_data[date])

    # Function to get the appropriate time period for grouping
    def get_time_period(date_col, period):
        if period == "Day":
            return date_col.dt.date
        elif period == "Week":
            return date_col.dt.to_period("W").dt.start_time.dt.date
        elif period == "Month":
            return date_col.dt.to_period("M").dt.start_time.dt.date

    # Add time period column
    chart_data["time_period"] = get_time_period(chart_data[date], time_period)

    # Group by time period and count interviews and unique enumerators
    period_stats = (
        chart_data.groupby("time_period")
        .agg(
            num_interviews=pd.NamedAgg(column=survey_id, aggfunc="count"),
            num_enumerators=pd.NamedAgg(column=enumerator, aggfunc="nunique"),
        )
        .reset_index()
    )

    # Calculate the average number of interviews
    average_interviews = period_stats["num_interviews"].mean()

    # Create the figure
    fig = go.Figure()

    # Add bar plot for interviews per time period with enumerator info in hover
    fig.add_trace(
        go.Bar(
            x=period_stats["time_period"],
            y=period_stats["num_interviews"],
            name="Interviews",
            marker_color="#2C5F2D",  # Dark green color
            hovertemplate="<b>%{x}</b><br>"
            + "Interviews: %{y}<br>"
            + "Enumerators: %{customdata}<extra></extra>",
            customdata=period_stats["num_enumerators"],  # Add enumerator data for hover
        )
    )

    # Add average interview line
    fig.add_trace(
        go.Scatter(
            x=[period_stats["time_period"].min(), period_stats["time_period"].max()],
            y=[average_interviews, average_interviews],
            mode="lines",
            name=f"Avg Interviews: {average_interviews:.2f}",
            line=dict(color="#4D5E90", width=1, dash="dash"),
        )
    )

    # Update layout
    fig.update_layout(
        title=f"Interview Progress by {time_period}",
        title_x=0,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
        margin=dict(t=50, b=50, l=50, r=50),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            title=time_period,
            showgrid=False,
            gridcolor="lightgrey",
            tickangle=-45,
            type="category",
        ),
        yaxis=dict(
            title_text="Number of Interviews",
            showgrid=False,
            gridcolor="lightgrey",
            zeroline=False,
        ),
    )

    st.plotly_chart(fig, theme=None, use_container_width=True)
