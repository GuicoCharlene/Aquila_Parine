import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parine_queue.settings')
django.setup()

# Now you can access Django settings
