from io import StringIO
import streamlit as st
import pandas as pd
import os
import re
import zipfile

# --- Get List of sheet from excel ---#

def get_excel_sheet_names(file_path: str) -> list:
    
	"""
	SOURCES:
	Code is from the following source:
	https://stackoverflow.com/questions/20105118/extracting-list-of-sheet-names-from-openpyxl

	Import an excel file and return the list of sheet names

	PARAMS:
	-------
	file_path: str : path to the excel file
    """

	sheets = []
	with zipfile.ZipFile(file_path, 'r') as zip_ref: xml = zip_ref.read("xl/workbook.xml").decode("utf-8")
	for s_tag in  re.findall("<sheet [^>]*", xml) : sheets.append(  re.search('name="[^"]*', s_tag).group(0)[6:])
	return sheets