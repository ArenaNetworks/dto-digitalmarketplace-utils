"""
Common utils for Digital Marketplace apps.
"""

from setuptools import setup

setup(
    name='dto-digitalmarketplace-utils',
    version='25.23.0',
    url='https://github.com/arenanetworks/dto-digitalmarketplace-utils',
    license='MIT',
    author='GDS Developers',
    description='Common utils for Digital Marketplace apps.',
    long_description=__doc__,
    packages=['dmutils', 'react'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'boto',
        'boto3',
        'contextlib2',
        'cryptography',
        'Flask',
        'six',
        'pyyaml',
        'python-json-logger',
        'inflection',
        'flask-cache',
        'flask_featureflags',
        'flask-login',
        'flask-script',
        'monotonic',
        'markdown',
        'pytz',
        'wtforms',
        'waitress',
        'workdays',
        'pendulum',
        'rollbar',
        'blinker'
    ]
)
