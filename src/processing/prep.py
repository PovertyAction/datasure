import pandas as pd


def prep_load_log(label) -> pd.DataFrame:
    """Load existing log or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of logs
    """
    # load form details from last session
    try:
        file = pd.read_json(f"cache/pyDMS_prep_cache_{label}.json")
        logs = file.to_dict()
        return pd.DataFrame(logs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["action", "description"])
