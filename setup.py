from setuptools import setup, find_packages


setup(
    name='django_backup_s3',
    version='1.0',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'python-dateutil==1.5',
        'hurry.filesize==0.9'
    ]
)
