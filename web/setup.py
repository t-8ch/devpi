from setuptools import setup


setup(
    name="devpi-web",
    description="devpi-web: a web view for devpi-server",
    url="http://doc.devpi.net",
    version='2.0.0.dev4',
    maintainer="Holger Krekel",
    maintainer_email="holger@merlinux.eu",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application"] + [
            "Programming Language :: Python :: %s" % x
            for x in "2.7 3.3".split()],
    entry_points={
        'devpi_server': [
            "devpi-web = devpi_web.main"]},
    install_requires=[
        'Whoosh',
        'devpi-server>=2.0.0.dev4',
        'docutils>=0.11',
        'pygments>=1.6',
        'pyramid',
        'pyramid-chameleon'],
    include_package_data=True,
    zip_safe=False,
    packages=['devpi_web', 'devpi_web.vendor'])
