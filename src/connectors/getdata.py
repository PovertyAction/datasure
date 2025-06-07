import json
import os

import polars as pl


def get_import_cache(project_id: str) -> pl.DataFrame:
    """Retrieve cached import data."""
    cache_file = f"cache/{project_id}/settings/import_cache.json"
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            import_cache = json.load(f)
    else:
        import_cache = {
            "refresh": False,
            "load": False,
            "type": "",
            "alias": "",
            "filename": "",
            "sheet_name": "",
            "server": "",
            "form_id": "",
            "private_key": "",
            "save_to": "",
            "attachments": False,
        }
    import_cache = pl.DataFrame(import_cache)
    import_cache = import_cache.filter(pl.col("alias") != "")

    return import_cache
