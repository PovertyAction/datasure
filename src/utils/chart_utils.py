import matplotlib.pyplot as plt


def donut_chart(
    actual_value: int,
    target_value: int = 100,
    title: str | None = None,
    prefix: str = "",
    suffix: str = "%",
    colors: list | None = None,
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
        colors=colors or ["#2C5F2D", "#CCCCCC"],
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
        color=colors[0],
    )

    # Remove axes
    ax.axis("equal")
    plt.axis("off")

    return fig
