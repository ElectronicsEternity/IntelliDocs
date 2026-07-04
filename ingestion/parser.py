# Import Path for handling file and folder paths in a platform-independent way
from pathlib import Path

# Import PyMuPDF library (imported as fitz)
import fitz


# Class responsible for reading and extracting text from PDF files
class PDFParser:

    # Constructor - receives the path of the PDF to process
    def __init__(self, pdf_path: Path):

        # Store the PDF path so other methods can access it
        self.pdf_path = pdf_path

    # Extract text from every page in the PDF
    def extract_text(self) -> list[dict]:

        # Create an empty list to store extracted pages
        pages = []

        # Open the PDF safely (automatically closes after processing)
        with fitz.open(self.pdf_path) as document:

            # Loop through every page in the PDF
            for page_index in range(document.page_count):

                # Load the current page
                page = document.load_page(page_index)

                # Extract all text from the current page
                text = page.get_text("text")

                # Store page number and extracted text
                pages.append({
                    "page_number": page_index + 1,
                    "text": text.strip()
                })

        # Return all extracted pages
        return pages


# Retrieve every PDF file inside the specified folder
def get_pdf_files(directory: Path) -> list[Path]:

    # Return all PDF files sorted alphabetically
    return sorted(directory.glob("*.pdf"))


# Main entry point for testing
def main():

    # Define the folder containing PDFs
    documents_folder = Path("documents")

    # Retrieve all PDF files
    pdf_files = get_pdf_files(documents_folder)

    # Stop execution if no PDFs exist
    if not pdf_files:
        print("No PDF files found.")
        return

    # Select the first PDF for testing
    pdf = pdf_files[0]

    # Display which PDF is being processed
    print(f"Processing: {pdf.name}")

    # Create a parser object
    parser = PDFParser(pdf)

    # Extract text from every page
    pages = parser.extract_text()

    # Display total pages extracted
    print(f"Total Pages: {len(pages)}")

    # Print a separator
    print("\n========== PAGE 1 ==========\n")

    # Display the first page
    print(pages[0]["text"])


# Execute only when this file is run directly
if __name__ == "__main__":
    main()