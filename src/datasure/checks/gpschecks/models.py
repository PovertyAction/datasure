"""Constants for the gpschecks module."""

TAB_NAME: str = "gpschecks"


## Constants

MAPBOX_STYLE = "mapbox://styles/mapbox/light-v9"

# Distinct color palette (RGBA) for categorical coloring on maps
_CATEGORY_COLORS: list[list[int]] = [
    [31, 119, 180, 200],
    [255, 127, 14, 200],
    [44, 160, 44, 200],
    [214, 39, 40, 200],
    [148, 103, 189, 200],
    [140, 86, 75, 200],
    [227, 119, 194, 200],
    [127, 127, 127, 200],
    [188, 189, 34, 200],
    [23, 190, 207, 200],
]
