#!/usr/bin/env python3
"""
Create Streamlit App Script

Generate a new Streamlit application from templates.
"""

import argparse
import shutil
from pathlib import Path


def create_app(app_type: str, output_path: Path, app_name: str = "My App"):
    """
    Create a new Streamlit app from template.

    Args:
        app_type: Type of app ('basic', 'multipage', 'form')
        output_path: Path where to create the app
        app_name: Name of the application
    """
    # Get script directory
    script_dir = Path(__file__).parent
    assets_dir = script_dir.parent / "assets"

    # Map app types to templates
    templates = {
        "basic": assets_dir / "app_template.py",
        "multipage": assets_dir / "multipage_template.py",
        "form": assets_dir / "form_template.py",
    }

    if app_type not in templates:
        msg = f"Unknown app type: {app_type}. Choose from: {', '.join(templates.keys())}"
        raise ValueError(msg)

    template_path = templates[app_type]

    if not template_path.exists():
        msg = f"Template not found: {template_path}"
        raise FileNotFoundError(msg)

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy template
    shutil.copy(template_path, output_path)

    # Read and customize content
    content = output_path.read_text()

    # Replace template title with custom app name
    replacements = {
        "My Streamlit App": app_name,
        "Multi-Page App": app_name,
        "Form Example": app_name,
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    # Write customized content
    output_path.write_text(content)

    print(f"✓ Created {app_type} app at: {output_path}")

    # If multipage, create pages directory
    if app_type == "multipage":
        pages_dir = output_path.parent / "pages"
        pages_dir.mkdir(exist_ok=True)
        print(f"✓ Created pages directory at: {pages_dir}")
        print("\nNext steps:")
        print(f"1. cd {output_path.parent}")
        print("2. Create page files in pages/ directory:")
        print("   - pages/1_📊_data.py")
        print("   - pages/2_📈_analysis.py")
        print("   - pages/3_⚙️_settings.py")

    # Create .streamlit directory
    streamlit_dir = output_path.parent / ".streamlit"
    streamlit_dir.mkdir(exist_ok=True)

    # Create basic config.toml if it doesn't exist
    config_path = streamlit_dir / "config.toml"
    if not config_path.exists():
        config_content = """[server]
port = 8501
headless = false

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#F63366"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"
"""
        config_path.write_text(config_content)
        print(f"✓ Created config at: {config_path}")

    print(f"\nTo run your app:")
    print(f"  streamlit run {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a new Streamlit application from template"
    )

    parser.add_argument(
        "type",
        choices=["basic", "multipage", "form"],
        help="Type of app to create",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("app.py"),
        help="Output file path (default: app.py)",
    )

    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default="My App",
        help="Application name (default: My App)",
    )

    args = parser.parse_args()

    try:
        create_app(args.type, args.output, args.name)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
