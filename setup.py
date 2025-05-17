from setuptools import find_packages, setup

setup(
    name="dms-dashboard",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.2.2",
        "streamlit>=1.41.1",
        "plotly>=5.24.1",
        "scikit-learn>=1.5.2",
        "geopy>=2.4.1",
    ],
)
