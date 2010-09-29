from distutils.core import setup


setup(
    name='django_backup',
    version='1.0',
    py_modules=[
        'django_backup.models',
        'django_backup.management.commands.backup'
    ],
    packages=['django_backup.management'],
)
