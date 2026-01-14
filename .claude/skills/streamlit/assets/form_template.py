"""
Streamlit Form Template

Template for creating forms with validation and state management.
"""

import re
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="Form Example", page_icon="📝", layout="wide")


# Initialize session state
def init_session_state():
    """Initialize form-related session state."""
    if "form_initialized" not in st.session_state:
        st.session_state.form_initialized = True
        st.session_state.form_submitted = False
        st.session_state.form_data = {}
        st.session_state.form_errors = {}


# Validation functions
def validate_email(email):
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_phone(phone):
    """Validate phone number format."""
    # Simple validation - at least 10 digits
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 10


def validate_age(age):
    """Validate age is reasonable."""
    return 0 < age < 120


# Form submission handler
def handle_form_submit():
    """Process form submission with validation."""
    errors = {}

    # Validate name
    if not st.session_state.form_name.strip():
        errors["name"] = "Name is required"

    # Validate email
    email = st.session_state.form_email
    if not email:
        errors["email"] = "Email is required"
    elif not validate_email(email):
        errors["email"] = "Invalid email format"

    # Validate age
    age = st.session_state.form_age
    if not validate_age(age):
        errors["age"] = "Age must be between 1 and 119"

    # Validate phone (optional field)
    phone = st.session_state.get("form_phone", "")
    if phone and not validate_phone(phone):
        errors["phone"] = "Invalid phone number format"

    # Store errors
    st.session_state.form_errors = errors

    # If no errors, mark as submitted
    if not errors:
        st.session_state.form_submitted = True
        st.session_state.form_data = {
            "name": st.session_state.form_name,
            "email": st.session_state.form_email,
            "age": st.session_state.form_age,
            "phone": phone,
            "country": st.session_state.form_country,
            "interests": st.session_state.form_interests,
            "newsletter": st.session_state.form_newsletter,
            "comments": st.session_state.get("form_comments", ""),
            "submitted_at": datetime.now().isoformat(),
        }


def reset_form():
    """Reset form state."""
    st.session_state.form_submitted = False
    st.session_state.form_data = {}
    st.session_state.form_errors = {}


# Main app
def main():
    """Main application."""
    init_session_state()

    st.title("📝 Form Example")

    # Show success message if form was submitted
    if st.session_state.form_submitted:
        st.success("✓ Form submitted successfully!")

        st.subheader("Submitted Data")
        st.json(st.session_state.form_data)

        if st.button("Submit Another Form"):
            reset_form()
            st.rerun()

        return

    # Show form
    st.markdown("Fill out the form below. Required fields are marked with *")

    with st.form("user_form"):
        # Name (required)
        st.text_input("Name *", key="form_name")
        if "name" in st.session_state.form_errors:
            st.error(st.session_state.form_errors["name"])

        # Email (required)
        st.text_input("Email *", key="form_email", placeholder="user@example.com")
        if "email" in st.session_state.form_errors:
            st.error(st.session_state.form_errors["email"])

        # Age (required)
        st.number_input("Age *", min_value=1, max_value=120, value=25, key="form_age")
        if "age" in st.session_state.form_errors:
            st.error(st.session_state.form_errors["age"])

        # Phone (optional)
        st.text_input(
            "Phone (optional)", key="form_phone", placeholder="(555) 123-4567"
        )
        if "phone" in st.session_state.form_errors:
            st.error(st.session_state.form_errors["phone"])

        # Country (required)
        st.selectbox(
            "Country *",
            options=["Select...", "USA", "Canada", "UK", "Australia", "Other"],
            key="form_country",
        )

        # Interests (optional, multiple)
        st.multiselect(
            "Interests (optional)",
            options=["Technology", "Sports", "Music", "Travel", "Reading", "Art"],
            key="form_interests",
        )

        # Newsletter checkbox
        st.checkbox("Subscribe to newsletter", value=True, key="form_newsletter")

        # Comments (optional)
        st.text_area(
            "Additional comments (optional)",
            height=100,
            key="form_comments",
            placeholder="Any additional information...",
        )

        # Divider
        st.divider()

        # Submit button row
        col1, col2, _ = st.columns([1, 1, 2])

        with col1:
            submitted = st.form_submit_button(  # noqa: F841
                "Submit", on_click=handle_form_submit, type="primary"
            )

        with col2:
            cleared = st.form_submit_button("Clear")

        if cleared:
            st.rerun()

    # Form instructions
    with st.expander("ℹ️ Form Instructions"):  # noqa: RUF001
        st.markdown("""
        **Required Fields:**
        - Name: Your full name
        - Email: Valid email address
        - Age: Must be between 1 and 119
        - Country: Select from dropdown

        **Optional Fields:**
        - Phone: If provided, must be at least 10 digits
        - Interests: Select multiple options
        - Comments: Any additional information
        """)

    # Debug section
    if st.checkbox("Show Debug Info"):
        st.subheader("Debug Information")
        st.write("Form submitted:", st.session_state.form_submitted)
        st.write("Current errors:", st.session_state.form_errors)
        st.write("Form data:", st.session_state.form_data)


if __name__ == "__main__":
    main()
