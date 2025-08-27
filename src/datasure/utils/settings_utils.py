import hashlib
import json
import os
from functools import lru_cache
from typing import Any

import streamlit as st

from .duckdb_utils import duckdb_get_table

# Security configuration constants
SECURITY_SETTINGS = {
    "file_upload": {
        "max_file_size_mb": {
            "csv": 100,
            "xlsx": 50,
            "xls": 50,
            "json": 10,
            "dta": 100,
        },
        "enable_virus_scanning": False,  # Disabled by default for compatibility
        "enable_content_validation": True,
        "enable_mime_validation": True,
        "max_concurrent_uploads": 3,
        "max_rows": 1000000,
        "max_columns": 1000,
        "allowed_extensions": ["csv", "xlsx", "xls", "json", "dta"],
        "enable_file_hashing": True,
        "enable_suspicious_content_detection": True,
    },
    "data_processing": {
        "max_dataframe_memory_mb": 1024,  # 1GB limit
        "enable_chunk_processing": True,
        "chunk_size_rows": 10000,
    },
}


@st.cache_data
def save_check_settings(settings_file, check_name, check_settings) -> None:
    """Save the settings for a check to a dictionary.

    Parameters
    ----------
    settings_dict (dict): The JSON file to which the settings will be added.
    check_name (str): The name of the check.
        The name of the check for which the settings will be saved.
    check_settings (dict): The settings for the check.
        The settings to save for the check.

    Returns
    -------
    None

    """
    if not os.path.exists(settings_file):
        with open(settings_file, "w") as f:
            json.dump({}, f)

    with open(settings_file) as f:
        settings_dict = json.load(f)

    if check_name in settings_dict:
        settings_dict[check_name].update(check_settings)
    else:
        settings_dict[check_name] = check_settings

    # save the dictionary to the file
    with open(settings_file, "w") as f:
        json.dump(settings_dict, f)


# @st.cache_data
def load_check_settings(settings_file, check_name) -> tuple:
    """Load the settings for a check from a dictionary.

    Parameters
    ----------
    settings_dict (dict): The JSON file from which the settings will be loaded.
    check_name (str): The name of the check.
        The name of the check for which the settings will be loaded.

    Returns
    -------
    tuple: The settings for the check.

    """
    # check if the file exists
    if not os.path.exists(settings_file):
        return None
    with open(settings_file) as f:
        settings_dict = json.load(f)

    return settings_dict.get(check_name)


def trigger_save(state_name: str):
    """Return a session state of True when triggered by the user."""
    st.session_state[state_name] = True


# --- Get shortened ID for text --- #
@lru_cache
def get_hash_id(name: str, length=6) -> str:
    """Generate a unique ID (maybe) for project.
    This ID will be used as project IDs (6 digits) and dataset IDs 8 digits
    """
    hash_val = hashlib.sha256(name.encode()).hexdigest()
    return hash_val[:length]


# --- Get Check Config Settings from DuckDB --- #
def get_check_config_settings(project_id: str, page_row_index: int) -> tuple:
    """Get the check configuration settings from DuckDB.

    Parameters
    ----------
    project_id (str): The ID of the project.
    page_row_index (int): The index of the row in the page.

    Returns
    -------
    tuple: The check configuration settings.
    """
    hfc_config_logs = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )

    page_name = hfc_config_logs.row(page_row_index)[0]
    survey_data_name = hfc_config_logs.row(page_row_index)[1]
    survey_key = hfc_config_logs.row(page_row_index)[2]
    survey_id = hfc_config_logs.row(page_row_index)[3]
    survey_date = hfc_config_logs.row(page_row_index)[4]
    enumerator = hfc_config_logs.row(page_row_index)[5]
    backcheck_data_name = hfc_config_logs.row(page_row_index)[6]
    tracking_data_name = hfc_config_logs.row(page_row_index)[7]

    return (
        page_name,
        survey_data_name,
        survey_key,
        survey_id,
        survey_date,
        enumerator,
        backcheck_data_name,
        tracking_data_name,
    )


def get_security_setting(category: str, setting: str, default: Any = None) -> Any:
    """Get a security setting value.

    Parameters
    ----------
    category : str
        The security category (e.g., 'file_upload', 'data_processing')
    setting : str
        The specific setting name
    default : Any
        Default value if setting not found

    Returns
    -------
    Any
        The setting value or default
    """
    try:
        return SECURITY_SETTINGS.get(category, {}).get(setting, default)
    except (KeyError, AttributeError):
        return default


def is_security_feature_enabled(feature: str) -> bool:
    """Check if a security feature is enabled.

    Parameters
    ----------
    feature : str
        The feature name (e.g., 'virus_scanning', 'content_validation')

    Returns
    -------
    bool
        True if feature is enabled
    """
    feature_mapping = {
        "virus_scanning": get_security_setting(
            "file_upload", "enable_virus_scanning", False
        ),
        "content_validation": get_security_setting(
            "file_upload", "enable_content_validation", True
        ),
        "mime_validation": get_security_setting(
            "file_upload", "enable_mime_validation", True
        ),
        "file_hashing": get_security_setting(
            "file_upload", "enable_file_hashing", True
        ),
        "suspicious_content_detection": get_security_setting(
            "file_upload", "enable_suspicious_content_detection", True
        ),
        "chunk_processing": get_security_setting(
            "data_processing", "enable_chunk_processing", True
        ),
    }

    return feature_mapping.get(feature, False)


def get_file_size_limit(file_ext: str) -> int:
    """Get file size limit in MB for a given extension.

    Parameters
    ----------
    file_ext : str
        File extension (e.g., 'csv', 'xlsx')

    Returns
    -------
    int
        Size limit in MB
    """
    size_limits = get_security_setting("file_upload", "max_file_size_mb", {})
    return size_limits.get(file_ext.lower(), 50)  # Default 50MB


def validate_security_settings() -> dict[str, Any]:
    """Validate current security settings and return status.

    Returns
    -------
    Dict[str, Any]
        Validation results and recommendations
    """
    results = {
        "valid": True,
        "warnings": [],
        "recommendations": [],
        "status": {},
    }

    # Check file upload settings
    file_upload_settings = SECURITY_SETTINGS.get("file_upload", {})

    # Virus scanning availability
    try:
        from .file_security import VirusScanner

        virus_available = VirusScanner.is_available()
        virus_enabled = file_upload_settings.get("enable_virus_scanning", False)

        results["status"]["virus_scanning"] = {
            "available": virus_available,
            "enabled": virus_enabled,
            "recommended": virus_available,
        }

        if virus_available and not virus_enabled:
            results["recommendations"].append(
                "Virus scanning is available but disabled. Consider enabling for enhanced security."
            )
    except ImportError:
        results["status"]["virus_scanning"] = {
            "available": False,
            "enabled": False,
            "recommended": False,
        }

    # Content validation
    content_validation = file_upload_settings.get("enable_content_validation", True)
    results["status"]["content_validation"] = {
        "enabled": content_validation,
        "recommended": True,
    }

    if not content_validation:
        results["warnings"].append(
            "Content validation is disabled. This may allow malicious files."
        )

    # File size limits
    size_limits = file_upload_settings.get("max_file_size_mb", {})
    for ext, limit in size_limits.items():
        if limit > 200:  # Warn for very large limits
            results["warnings"].append(
                f"Large file size limit for {ext}: {limit}MB. Consider reducing for better performance."
            )

    return results
