from django.apps import AppConfig
from django.db import connection, OperationalError
from django.conf import settings
from django.apps import apps
from django.utils import timezone

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

class YourAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parine_sa_batangas'

    def ready(self):
        # Call the function to check the connection when the app is ready
        from .utils import check_mysql_connection
        check_mysql_connection()

class parine(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parine'

    def ready(self):
        from .utils import ensure_kiosk_count
        ensure_kiosk_count()
