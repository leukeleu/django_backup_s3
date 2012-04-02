from distutils.core import setup


setup(
    name='django_backup_s3',
    version='1.0',
    py_modules=[
        'django_backup_s3.models',
        'django_backup_s3.management.commands.backup'
    ],
    packages=['django_backup_s3.management'],
)
