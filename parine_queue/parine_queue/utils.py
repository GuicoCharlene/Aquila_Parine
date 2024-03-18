from .models import Kiosk
import logging
from django.db import connection, OperationalError
import os

# Create a logger instance
logger = logging.getLogger(__name__)

def check_mysql_connection():
    try:
        # Attempt to execute a simple query to check if the connection works
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row:
                logger.info("MySQL connection is successful!")
            else:
                logger.warning("MySQL connection is not established.")
    except OperationalError as e:
        # If an operational error occurs, log the error message
        logger.error("Operational Error connecting to MySQL: %s", e)
    except Exception as e:
        # If any other exception occurs, log the error message
        logger.error("Error connecting to MySQL: %s", e)

def ensure_kiosk_count():
    try:
        # Delete any existing Kiosk instances
        Kiosk.objects.all().delete()

        # Create new Kiosk instances with IDs from 1 to 3
        for kiosk_id in range(1, 4):
            Kiosk.objects.create(KioskID=kiosk_id)
            logger.info("Added Kiosk instance with KioskID %d.", kiosk_id)
    except Exception as e:
        # Log any errors that occur during the process
        logger.error("Error ensuring kiosk count: %s", e)

ensure_kiosk_count()
