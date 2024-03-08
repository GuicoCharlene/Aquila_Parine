from django.apps import AppConfig
from django.apps import AppConfig
from .utils import check_mysql_connection

class YourAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parine_sa_batangas'

    def ready(self):
        # Call the function to check the connection when the app is ready
        check_mysql_connection()

class PQueueConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parine_queue'