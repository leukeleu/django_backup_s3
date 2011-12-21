import os
import shutil
import gzip
import datetime

from django.core.management.base import NoArgsCommand
from django.core.files.base import File
from django.conf import settings
from django.core.mail import mail_managers

from storages.backends.s3boto import S3BotoStorage


class Command(NoArgsCommand):
    """
    Store backup of database and media on s3. Only mysql database is supported.
    """
    def handle_noargs(self, **options):
        try:
            self.backup()
        except Exception, e:
            mail_managers('Backup failed for %s' % self.get_database_name(), str(e), None)
            raise

    def get_database_name(self):
        return settings.DATABASES['default']['NAME']

    def backup(self):
        # create temp dir
        temp_dir = self.create_temp_dir()

        # backup mysql
        database_dump_filename = os.path.join(temp_dir, self.get_database_filename())
        self.mysql_backup(database_dump_filename)

        # gzip backup file
        database_output_filename = self.gzip_file(database_dump_filename)

        # encrypt
        if self.must_encrypt():
            database_output_filename = self.encrypt(database_output_filename)

        # put backup file in storage
        self.store_file(database_output_filename)

        # gzip upload files
        upload_output_filename = self.gzip_upload_files(temp_dir)

        if upload_output_filename:
            # encrypt
            if self.must_encrypt():
                upload_output_filename = self.encrypt(upload_output_filename)

            # put upload files in storage
            self.store_file(upload_output_filename)

    def get_database_filename(self):
        return "db-%s-%s.sql" % (self.get_database_name(), self.get_today_string())

    def get_today_string(self):
        return str(datetime.date.today())

    def create_temp_dir(self):
        temp_dir = "temp"

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        return temp_dir

    def mysql_backup(self, output_file):
        if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.mysql':
            raise Exception("Only mysql is supported for backup")

        database_name = self.get_database_name()
        command_string = 'mysqldump --user=%s --password=%s %s > %s' % (
            settings.DATABASES['default']['USER'], settings.DATABASES['default']['PASSWORD'], database_name, output_file
        )
        status = os.system(command_string)
        if status != 0:
            raise Exception("Mysqldump failed for database %s" % database_name)

        if not os.path.exists(output_file):
            raise Exception("Database backup file not created: %s" % output_file)

    def gzip_file(self, input_filename):
        output_filename = input_filename + '.gz'

        zipfile = gzip.GzipFile(output_filename, "wb")
        try:
            input_file = open(input_filename)
            try:
                zipfile.write(input_file.read())
            finally:
                input_file.close()
        finally:
            zipfile.close()

        if not os.path.exists(output_filename):
            raise Exception("Database backup file not created: %s" % output_filename)

        return output_filename

    def store_file(self, filename):
        storage = self.get_storage()

        f = File(open(filename))
        try:
            storage.save(os.path.basename(filename), f)
        finally:
            f.close()

    def get_storage(self):
        return S3BotoStorage(
            bucket=settings.BACKUP_S3_BUCKET,
            access_key=settings.BACKUP_S3_ACCESS_KEY,
            secret_key=settings.BACKUP_S3_SECRET_KEY,
            acl='private'
        )

        # Code fragment for local testing
        # todo: make setting
        #from django.core.files.storage import FileSystemStorage
        #return FileSystemStorage("backup_files")

    def gzip_upload_files(self, temp_dir):
        upload_paths = self.get_upload_paths()

        if not upload_paths:
            return ''

        target_file = os.path.join(
            temp_dir,
            "uploads-%s-%s.tar.gz" % (self.get_database_name(), self.get_today_string())
        )

        command_string = "tar -czf %s --exclude-vcs --absolute-names %s" % (
            target_file, ' '.join(upload_paths)
        )
        status = os.system(command_string)
        if status != 0:
            raise Exception("Tarball failed")
        return target_file

    def must_encrypt(self):
        return hasattr(settings, 'BACKUP_PUBLIC_PGP_KEY')

    def encrypt(self, filename):
        command_string = "gpg --encrypt --recipient %s %s" % (settings.BACKUP_PUBLIC_PGP_KEY, filename)
        status = os.system(command_string)
        if status != 0:
            raise Exception("Encryption failed")

        output_filename = filename + '.gpg'
        if not os.path.exists(output_filename):
            raise Exception("File not found: %s" % output_filename)
        return output_filename

    def get_upload_paths(self):
        """
        Return upload paths from setting. Filter existing paths.
        """
        if not hasattr(settings, 'BACKUP_FILE_PATHS'):
            return []
        else:
            return set(
                path for path in settings.BACKUP_FILE_PATHS if os.path.exists(path)
            )
