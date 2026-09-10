# ========================================
# File: test_database.py
# ========================================

from app.database.database import Database


def main():

    db = Database()

    print("Testing database connection...")

    result = db.fetch_one(
        "SELECT COUNT(*) FROM documents"
    )

    print("Result:")
    print(result)

    if result is not None:
        print("Database connection successful.")
    else:
        print("No result returned.")


if __name__ == "__main__":
    main()