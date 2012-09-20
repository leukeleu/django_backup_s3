from datetime import date

from dateutil.relativedelta import relativedelta

from boto.s3.connection import S3Connection
from boto.utils import parse_ts

from hurry.filesize import size

from django.conf import settings
from django.core.management.base import NoArgsCommand


class Command(NoArgsCommand):
    """
    Remove old backups from S3
    """
    def handle_noargs(self, **options):
        connection = S3Connection(settings.BACKUP_S3_ACCESS_KEY, settings.BACKUP_S3_SECRET_KEY)
        bucket = connection.get_bucket(settings.BACKUP_S3_BUCKET)

        count_deleted = 0
        size_deleted = 0
        for key in bucket.list():
            file_datetime = parse_ts(key.last_modified)

            # Time is appararently two hours earlier than local time
            file_date = (file_datetime + relativedelta(hours=2)).date()

            if not must_keep_file(file_date):
                count_deleted += 1
                size_deleted += key.size
                key.delete()

        print "%d files are deleted with a total size of %s" % (count_deleted, size(size_deleted))


def must_keep_file(file_date):
    """
    0 - 3 months
        -> keep

    3 - 12 months
        -> keep if date is a monday

    12 -
        -> keep if first of month
    """
    delta = relativedelta(date.today(), file_date)

    if delta.years >= 1:
        # File is older than a year
        # Keep first of month
        return file_date.day == 1
    elif delta.months >= 3:
        # File is older than 3 months
        # Keep first of month and mondays
        return (file_date.weekday() == 0) or (file_date.day == 1)
    else:
        # File is less old than 3 months
        # Always keep
        return True