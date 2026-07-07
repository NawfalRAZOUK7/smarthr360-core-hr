from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hr'

    def ready(self):
        # Connect SCD2 history signals (see hr/signals.py).
        from . import signals  # noqa: F401
