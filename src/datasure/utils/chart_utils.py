import matplotlib.pyplot as plt


def donut_chart(
    actual_value: float,
    target_value: float = 100,
    title: str | None = None,
    prefix: str = "",
    suffix: str = "%",
    colors: list | None = None,
):
    """
    Create a donut chart with the specified parameters.

    Parameters
    ----------
    actual_value: float
        The value to display (e.g., percentage complete). Rendered to two
        decimal places when suffix is "%".
    target_value: float
        The maximum value (default 100)
    title: str
        Title of the chart
    prefix: str
        Prefix to add to actual value eg "$"
    suffix: str
        Suffix to add to actual value eg "%" or "K"
    colors: list
        Two colour codes: [value segment, background segment]. The value
        colour is also used for the centre text.

    Returns
    -------
    fig: matplotlib figure
        The created figure
    """
    if colors is None:
        colors = ["#FF8000", "#E5E5E5"]

    fig = plt.figure(figsize=(10, 10), facecolor="#FFFFFF")
    ax = fig.add_subplot(1, 1, 1)

    if title:
        ax.set_title(title, fontsize=50)

    # If the actual value exceeds the target, show a full ring
    remainder = max(0, target_value - actual_value)

    pie = ax.pie(
        [actual_value, remainder],
        colors=colors,
        startangle=90,
        labeldistance=1.15,
        counterclock=False,
    )

    # Make the background segment semi-transparent
    pie[0][1].set_alpha(0.4)

    # Add center circle to create the donut hole
    centre_circle = plt.Circle((0, 0), 0.7, fc="#FFFFFF")
    fig.gca().add_artist(centre_circle)

    display_value = f"{actual_value:.2f}" if suffix == "%" else actual_value
    centre_text = f"{prefix}{display_value}{suffix}"
    ax.text(
        0,
        0.1,
        centre_text,
        horizontalalignment="center",
        verticalalignment="center",
        fontsize=60,
        fontweight="bold",
        color=colors[0],
    )

    ax.axis("equal")
    plt.axis("off")

    return fig
