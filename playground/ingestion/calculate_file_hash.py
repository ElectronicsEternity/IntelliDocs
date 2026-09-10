# ============================================
# calculate_file_hash.py
# Playground - SHA256 File Hash
# ============================================
from pathlib import Path

# IntelliDocs project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Documents folder
DOCUMENTS_FOLDER = PROJECT_ROOT / "documents"

# PDF to test
pdf = DOCUMENTS_FOLDER / "Employment Act 1955.pdf"

import hashlib

# Number of bytes to read at a time
FILE_READ_CHUNK_SIZE = 4096


# Generate a SHA256 hash for a file
def calculate_file_hash(file_path: Path) -> str:

    # Create a SHA256 hash object
    sha256 = hashlib.sha256()

    # Open the file in binary mode
    with open(file_path, "rb") as file:

        # Read the file in fixed-size chunks
        while chunk := file.read(FILE_READ_CHUNK_SIZE):

            # Update the hash with the current chunk
            sha256.update(chunk)

    # Return the completed hash
    return sha256.hexdigest()


# Main entry pointcls
def main():

    # Select a PDF to hash
    pdf = Path("documents/Akta Kerja 1955 (Akta 265)_0.pdf")

    # Generate the hash
    file_hash = calculate_file_hash(pdf)

    # Display the result
    print()
    print(f"Filename : {pdf.name}")
    print(f"SHA256   : {file_hash}")


# Execute only when this file is run directly
if __name__ == "__main__":
    main()