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
            mail_managers('Backup failed', str(e), None)
            raise

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
        return "db-%s-%s.sql" % (settings.DATABASE_NAME, self.get_today_string())

    def get_today_string(self):
        return str(datetime.date.today())

    def create_temp_dir(self):
        temp_dir = "temp"

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.mkdir(temp_dir)
        return temp_dir

    def mysql_backup(self, output_file):
        if settings.DATABASE_ENGINE != 'mysql':
            raise Exception("Only mysql is supported for backup")

        command_string = 'mysqldump --user=%s --password=%s %s > %s' % (
            settings.DATABASE_USER, settings.DATABASE_PASSWORD, settings.DATABASE_NAME, output_file
        )
        status = os.system(command_string)
        if status != 0:
            raise Exception("Mysqldump failed for database %s" % settings.DATABASE_NAME)

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

        #from django.core.files.storage import FileSystemStorage
        #return FileSystemStorage("backup")

    def gzip_upload_files(self, temp_dir):
        if not hasattr(settings, 'BACKUP_FILE_PATHS'):
            return ''

        upload_paths = settings.BACKUP_FILE_PATHS
        if not upload_paths:
            return ''

        target_file = os.path.join(
            temp_dir,
            "uploads-%s-%s.tar.gz" % (settings.DATABASE_NAME, self.get_today_string())
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
