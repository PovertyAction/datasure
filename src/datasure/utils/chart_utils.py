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
    # Handle case where actual exceeds target
    remainder = max(0, target_value - actual_value)
    if remainder == 0:
        # If actual exceeds target, show just the actual value
        pie_values = [actual_value]
        pie_colors = [(colors or ["#2C5F2D", "#CCCCCC"])[0]]
    else:
        pie_values = [actual_value, remainder]
        pie_colors = colors or ["#2C5F2D", "#CCCCCC"]

    pie = ax.pie(
        pie_values,
        colors=pie_colors,
        startangle=90,
        labeldistance=1.15,
        counterclock=False,
    )

    # Make the background segment semi-transparent (if it exists)
    if len(pie[0]) > 1:
        pie[0][1].set_alpha(0.4)

    # Add center circle to create donut
    centre_circle = plt.Circle((0, 0), 0.7, fc="#FFFFFF")
    fig.gca().add_artist(centre_circle)

    # Add center text
    centre_text = f"{prefix}{actual_value}{suffix}"
    text_color = (colors or ["#2C5F2D", "#CCCCCC"])[0]
    ax.text(
        0,
        0,
        centre_text,
        horizontalalignment="center",
        verticalalignment="center",
        fontsize=20,
        fontweight="bold",
        color=text_color,
    )

    # Remove axes
    ax.axis("equal")
    plt.axis("off")

    return fig


def donut_chart2(
    actual_value: int,
    target_value: int = 100,
    title: str | None = None,
    prefix: str = "",
    suffix: str = "%",
    colours: list | None = None,
):
    """
    actual_value: int
    target_value: int
    title: str
    prefix: str - prefix to add to actual value eg "$"
    suffix: str - suffix to add to actual value eg "%" or "K"
    colours: list of colour codes
    """
    if colours is None:
        colours = ["#FF8000", "#E5E5E5"]

    fig = plt.figure(figsize=(10, 10), facecolor="#FFFFFF")
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title(title, fontsize=50)

    # calculate the remainder. If the actual value is greater
    # than the target value, set the remainder to 0
    remainder = target_value - actual_value if actual_value <= target_value else 0

    pie = ax.pie(
        [actual_value, remainder],
        colors=colours,
        startangle=90,
        labeldistance=1.15,
        counterclock=False,
    )

    pie[0][1].set_alpha(0.4)

    centre_circle = plt.Circle((0, 0), 0.7, fc="#FFFFFF")
    fig.gca().add_artist(centre_circle)

    if suffix == "%":
        actual_value = f"{actual_value:.2f}"

    centre_text = f"{prefix}{actual_value}{suffix}"

    ax.text(
        0,
        0.1,
        centre_text,
        horizontalalignment="center",
        verticalalignment="center",
        fontsize=60,
        fontweight="bold",
        color="#FF8000",
    )

    return fig
