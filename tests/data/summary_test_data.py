"""Module for creating test datasets for summary tests."""

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def create_test_dataset(size=1000, seed=42):
    """Create a test dataset with specified number of observations.

    Args:
        size (int, optional): Number of observations to generate. Defaults to 1000.
        seed (int, optional): Random seed for reproducibility. Defaults to 42.

    Returns
    -------
        pd.DataFrame: Test dataset with datetime, enum_id, and enum_name columns.
    """
    # Set random seeds for reproducibility
    np.random.seed(seed)
    random.seed(seed)

    # Generate datetime range
    start_date = datetime(2023, 4, 1)
    end_date = datetime(2023, 5, 15)

    # Generate random datetimes
    dates = []
    for _ in range(size):
        date = start_date + timedelta(
            days=random.randint(0, (end_date - start_date).days),
            hours=random.randint(8, 18),  # Mostly 9 AM to 5 PM
            minutes=random.randint(0, 59),
        )
        dates.append(date)

    # Add some outlier times (before 9 AM and after 5 PM)
    outlier_indices = random.sample(range(size), 20)
    for idx in outlier_indices:
        dates[idx] = dates[idx].replace(hour=random.choice([6, 7, 19, 20]))

    # Create enumerator data
    enum_ids = list(range(1, 11))  # 10 enumerators
    enum_names = [
        "John Smith",
        "Mary Johnson",
        "David Williams",
        "Patricia Brown",
        "Robert Jones",
        "Linda Davis",
        "Michael Miller",
        "Sarah Wilson",
        "James Taylor",
        "Jennifer Anderson",
    ]

    # Create the dataset
    data = {
        "datetime": dates,
        "enum_id": [random.choice(enum_ids) for _ in range(size)],
    }

    df = pd.DataFrame(data)

    # Add enum_name based on enum_id
    enum_dict = dict(zip(enum_ids, enum_names, strict=False))
    df["enum_name"] = df["enum_id"].map(enum_dict)

    return df


if __name__ == "__main__":
    # Example usage
    test_data = create_test_dataset()
    print("Dataset shape:", test_data.shape)
    print("\nFirst few rows:")
    print(test_data.head())
    print("\nDate range:")
    print("Start:", test_data["datetime"].min())
    print("End:", test_data["datetime"].max())
