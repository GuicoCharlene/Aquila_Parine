from django.db import connection, OperationalError
from django.conf import settings

def check_mysql_connection():
    try:
        # Attempt to execute a simple query to check if the connection works
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row:
                print("MySQL connection is successful!")
            else:
                print("MySQL connection is not established.")
    except OperationalError as e:
        # If an operational error occurs, print the error message
        print("Operational Error connecting to MySQL:", e)
    except Exception as e:
        # If any other exception occurs, print the error message
        print("Error connecting to MySQL:", e)

