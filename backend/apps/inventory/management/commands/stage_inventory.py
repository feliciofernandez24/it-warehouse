"""Local-operator preparation only; does not open a database connection."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.inventory.staging.common import StagingError
from apps.inventory.staging.normalization import aggregate, preview
from apps.inventory.staging.reader import read_workbook
from apps.inventory.staging.storage import capture


class Command(BaseCommand):
    help = "Validate authoritative workbook; sanitized dry-run, optionally private file capture."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("workbook")
        parser.add_argument("--capture-root",
                            help="Existing owner-only 0700 absolute directory outside repository.")

    def handle(self, *args, **options):
        try:
            result = preview(read_workbook(options["workbook"]))
            if options["capture_root"]:
                capture(result, options["capture_root"], repository=(Path(settings.BASE_DIR).parent if Path(settings.BASE_DIR).name == "backend"
                                       else Path(settings.BASE_DIR)))
            self.stdout.write(json.dumps(aggregate(result), sort_keys=True))
        except StagingError as error:
            raise CommandError(error.code) from None
        except (OSError, ValueError, KeyError):
            raise CommandError("STAGING_FAILED") from None
