from .models import Kiosk
import logging
from django.db import connection, OperationalError
import os

logger = logging.getLogger(__name__)

def check_mysql_connection():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row:
                logger.info("MySQL connection is successful!")
            else:
                logger.warning("MySQL connection is not established.")
    except OperationalError as e:

        logger.error("Operational Error connecting to MySQL: %s", e)
    except Exception as e:

        logger.error("Error connecting to MySQL: %s", e)

