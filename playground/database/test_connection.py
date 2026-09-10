# ========================================
# File: test_connection.py
# ========================================

from app.database.connection import (
    get_connection
)


def main():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT 1;"
    )

    result = cursor.fetchone()

    print(result)

    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()