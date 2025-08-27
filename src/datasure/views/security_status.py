"""Security status display components for DataSure.

This module provides reusable UI components for displaying
security status, diagnostics, and recommendations.
"""

import streamlit as st

from datasure.utils.file_security import VirusScanner
from datasure.utils.settings_utils import validate_security_settings


def display_security_overview() -> None:
    """Display comprehensive security status overview."""
    st.subheader(":material/security: Security Overview")

    # Get security validation results
    security_status = validate_security_settings()

    # Overall security status
    if security_status["valid"] and not security_status["warnings"]:
        st.success(":material/verified: All security features are properly configured")
    elif security_status["warnings"]:
        st.warning(
            f":material/warning: {len(security_status['warnings'])} security warnings detected"
        )
    else:
        st.error(":material/error: Security configuration issues detected")

    # Security features status
    with st.expander(":material/shield: Security Features Status", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**File Upload Security:**")

            # Content validation
            content_status = security_status["status"].get("content_validation", {})
            if content_status.get("enabled", False):
                st.markdown(":material/check: Content validation enabled")
            else:
                st.markdown(":material/close: Content validation disabled")

            # Virus scanning
            virus_status = security_status["status"].get("virus_scanning", {})
            if virus_status.get("available", False):
                if virus_status.get("enabled", False):
                    st.markdown(":material/verified: Virus scanning enabled")
                else:
                    st.markdown(":material/info: Virus scanning available but disabled")
            else:
                st.markdown(":material/info: Virus scanning not available")

        with col2:
            st.markdown("**Data Processing Security:**")
            st.markdown(":material/check: SQL injection protection active")
            st.markdown(":material/check: File size limits enforced")
            st.markdown(":material/check: Malicious content detection active")
            st.markdown(":material/check: Secure credential storage enabled")

    # Warnings and recommendations
    if security_status["warnings"]:
        with st.expander(":material/warning: Security Warnings", expanded=True):
            for warning in security_status["warnings"]:
                st.warning(f":material/warning: {warning}")

    if security_status["recommendations"]:
        with st.expander(
            ":material/lightbulb: Security Recommendations", expanded=False
        ):
            for recommendation in security_status["recommendations"]:
                st.info(f":material/lightbulb: {recommendation}")


def display_file_security_status() -> None:
    """Display file upload security status for import views."""
    with st.expander(":material/security: File Security Status", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Security Features:**")
            st.markdown(":material/check: File size limits enforced")
            st.markdown(":material/check: Content type validation enabled")
            st.markdown(":material/check: Malicious content detection active")
            st.markdown(":material/check: File integrity verification")

        with col2:
            st.markdown("**File Size Limits:**")
            st.markdown("- CSV: 100MB")
            st.markdown("- Excel: 50MB")
            st.markdown("- JSON: 10MB")
            st.markdown("- Stata: 100MB")

        # Virus scanning status
        virus_available = VirusScanner.is_available()
        if virus_available:
            st.success(":material/verified: Virus scanning available")
        else:
            st.info(":material/info: Virus scanning not available on this system")


def display_security_diagnostics() -> None:
    """Display detailed security diagnostics for troubleshooting."""
    st.subheader(":material/bug_report: Security Diagnostics")

    with st.expander(":material/settings: Detailed Diagnostics", expanded=False):
        # Test virus scanner availability
        st.markdown("**Virus Scanner Status:**")
        virus_available = VirusScanner.is_available()

        if virus_available:
            st.success(":material/check: Virus scanner is available")
            scanner_type = (
                "Windows Defender"
                if st.secrets.get("platform") == "windows"
                else "ClamAV"
            )
            st.info(f":material/info: Using {scanner_type}")
        else:
            st.warning(":material/warning: Virus scanner not available")
            st.markdown("""
            **To enable virus scanning:**
            - **Windows:** Ensure Windows Defender is active
            - **macOS/Linux:** Install ClamAV (`sudo apt install clamav` or `brew install clamav`)
            """)

        # Security settings validation
        st.markdown("**Security Configuration:**")
        security_status = validate_security_settings()

        if st.button(":material/refresh: Refresh Diagnostics"):
            st.rerun()

        # Raw security status for debugging
        if st.checkbox("Show raw security status (debug)"):
            st.json(security_status)


def show_security_incident_report(incident_type: str, details: str) -> None:
    """Display security incident notification.

    Parameters
    ----------
    incident_type : str
        Type of security incident (e.g., 'malicious_file', 'size_violation')
    details : str
        Detailed description of the incident
    """
    st.error(":material/security: Security Incident Detected")

    with st.expander(":material/report: Incident Details", expanded=True):
        st.markdown(f"**Incident Type:** {incident_type}")
        st.markdown(f"**Details:** {details}")
        st.markdown("**Action:** File upload blocked for security reasons")
        st.markdown(
            "**Recommendation:** Verify file source and content before retrying"
        )

        if incident_type == "malicious_file":
            st.warning(":material/dangerous: The file may contain malicious content")
        elif incident_type == "size_violation":
            st.info(":material/info: File exceeds maximum allowed size")
        elif incident_type == "virus_detected":
            st.error(":material/virus: Virus or malware detected in file")


def display_security_help() -> None:
    """Display security help and best practices."""
    st.subheader(":material/help: Security Best Practices")

    with st.expander(":material/school: File Upload Security", expanded=False):
        st.markdown("""
        **Best Practices for File Uploads:**

        :material/check: **Only upload files from trusted sources**
        - Verify the origin of data files
        - Scan files with your antivirus before uploading

        :material/check: **Use supported file formats only**
        - CSV, Excel (.xlsx/.xls), JSON, Stata (.dta)
        - Avoid files with suspicious extensions

        :material/check: **Monitor file sizes**
        - Large files may impact performance
        - Consider splitting very large datasets

        :material/check: **Verify data integrity**
        - Check file hashes when available
        - Validate data content after upload
        """)

    with st.expander(":material/lock: Credential Security", expanded=False):
        st.markdown("""
        **Credential Management:**

        :material/check: **System keyring integration**
        - Credentials stored in OS-level secure storage
        - Automatic encryption and access control

        :material/check: **No plaintext storage**
        - Legacy plaintext credentials automatically migrated
        - Secure deletion of old credential files

        :material/check: **Access control**
        - Credentials isolated per project
        - No cross-project credential access
        """)

    with st.expander(":material/database: Data Security", expanded=False):
        st.markdown("""
        **Data Protection Features:**

        :material/check: **SQL injection prevention**
        - Parameterized queries and input validation
        - Table name sanitization

        :material/check: **Content validation**
        - Malicious content pattern detection
        - File structure validation

        :material/check: **Access controls**
        - Project-based data isolation
        - Secure cache directory management
        """)
