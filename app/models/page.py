# Import dataclass decorator to automatically generate constructor and other methods
from dataclasses import dataclass


# Define a simple data model for a PDF page
@dataclass
class Page:

    # Store the page number within the PDF
    page_number: int

    # Store the extracted text from the page
    text: str