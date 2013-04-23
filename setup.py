#! /usr/bin/env python

import os, sys
from setuptools import setup, find_packages


if __name__ == "__main__":
    here = os.path.abspath(os.path.dirname(__file__))
    README = open(os.path.join(here, 'README.txt')).read()
    CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

    install_requires = [
            "beautifulsoup4>=4.1.3", "redis>=2.7.2",
            'pyramid', 'pyramid_debugtoolbar',
            'gunicorn',
    ]
    #if sys.version_info < (2,7):
    #    install_requires.append("argparse")

    setup(
      name="devpi-server",
      description="devpi caching indexes server",
      long_description=README + '\n\n' + CHANGES,
      version='0.6.dev10',
      maintainer="Holger Krekel",
      maintainer_email="holger@merlinux.eu",
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      license="MIT",
      classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      install_requires=install_requires,
      entry_points = {
        'console_scripts':
                    ["devpi-server = devpi_server.main:main"],
        'paste.app_factory':
                    ["main = devpi_server.wsgi:main"],
      })

