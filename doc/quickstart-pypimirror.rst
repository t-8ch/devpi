.. include:: links.rst

Quickstart: running a pypi mirror on your laptop
----------------------------------------------------

This quickstart document let's you quickly run and manage ``devpi-server``
for serving an efficient self-updating PyPI caching mirror on your laptop,
suitable for offline operations after an initial cache fill.

Installing devpi-server
++++++++++++++++++++++++++++++++++

Install the ``devpi-server`` package on our machine::

    pip install -q -U devpi-server

Show version::

    $ devpi-server --version
    2.0.2

.. note::

    This tutorial does not require you to install or use the ``devpi-client``
    package.  Consult :doc:`quickstart-releaseprocess`` to learn more 
    about how you can use the ``devpi`` command line tool to
    manage working with uploads, tests and multiple indexes.


start background devpi-server process
++++++++++++++++++++++++++++++++++++++++++++++

To start ``devpi-server`` in the background issue::
    
    $ devpi-server --start
    2014-08-06 21:36:09,039 INFO  NOCTX DB: Creating schema
    2014-08-06 21:36:09,101 INFO  [Wtx-1] setting password for user u'root'
    2014-08-06 21:36:09,102 INFO  [Wtx-1] created user u'root' with email None
    2014-08-06 21:36:09,102 INFO  [Wtx-1] created root user
    2014-08-06 21:36:09,102 INFO  [Wtx-1] created root/pypi index
    2014-08-06 21:36:09,122 INFO  [Wtx-1] fswriter0: committed: keys: u'.config',u'root/.config'
    starting background devpi-server at http://localhost:3141
    /tmp/home/.devpi/server/.xproc/devpi-server$ /home/hpk/venv/0/bin/devpi-server
    process u'devpi-server' started pid=14440
    devpi-server process startup detected
    logfile is at /tmp/home/.devpi/server/.xproc/devpi-server/xprocess.log

You now have a server listning on ``http://localhost:3141``.

.. _`install_first`:

install your first package with pip/easy_install
+++++++++++++++++++++++++++++++++++++++++++++++++++++

Both pip_ and easy_install_ support the ``-i`` option to specify
an index server url.  We use it to point installers to a special
``root/pypi`` index, served by ``devpi-server`` by default. 
Let's install the ``simplejson`` package as a test from our cache::

    $ pip install -i http://localhost:3141/root/pypi/ simplejson
    Downloading/unpacking simplejson
      http://localhost:3141/root/pypi/simplejson/ uses an insecure transport scheme (http). Consider using https if localhost:3141 has it available
      Running setup.py (path:/tmp/docenv/build/simplejson/setup.py) egg_info for package simplejson
        
    Installing collected packages: simplejson
      Running setup.py install for simplejson
        building 'simplejson._speedups' extension
        x86_64-linux-gnu-gcc -pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -Wstrict-prototypes -fPIC -I/usr/include/python2.7 -c simplejson/_speedups.c -o build/temp.linux-x86_64-2.7/simplejson/_speedups.o
        x86_64-linux-gnu-gcc -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions -Wl,-Bsymbolic-functions -Wl,-z,relro -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -Wall -Wstrict-prototypes -D_FORTIFY_SOURCE=2 -g -fstack-protector --param=ssp-buffer-size=4 -Wformat -Werror=format-security build/temp.linux-x86_64-2.7/simplejson/_speedups.o -o build/lib.linux-x86_64-2.7/simplejson/_speedups.so
        
    Successfully installed simplejson
    Cleaning up...

.. note::

    The "insecure transport" warning is an issue with
    pip-1.5.6 which will hopefully be fixed sometime,
    see `issue1456 <https://github.com/pypa/pip/issues/1456>`_.

Let's uninstall it::

    $ pip uninstall -y simplejson
    Uninstalling simplejson:
      Successfully uninstalled simplejson

and then re-install it with ``easy_install``::

    $ easy_install -i http://localhost:3141/root/pypi/+simple/ simplejson
    Searching for simplejson
    Reading http://localhost:3141/root/pypi/+simple/simplejson/
    Best match: simplejson 3.6.0
    Downloading http://localhost:3141/root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz#md5=20e1880a8c6120b54077bfac50306823
    Processing simplejson-3.6.0.tar.gz
    Writing /tmp/easy_install-ZoxkxS/simplejson-3.6.0/setup.cfg
    Running simplejson-3.6.0/setup.py -q bdist_egg --dist-dir /tmp/easy_install-ZoxkxS/simplejson-3.6.0/egg-dist-tmp-cB4XVv
    zip_safe flag not set; analyzing archive contents...
    simplejson.tests.__init__: module references __file__
    Adding simplejson 3.6.0 to easy-install.pth file
    
    Installed /tmp/docenv/lib/python2.7/site-packages/simplejson-3.6.0-py2.7-linux-x86_64.egg
    Processing dependencies for simplejson
    Finished processing dependencies for simplejson

Feel free to install any other package.  If you encounter lookup/download
issues when installing a public pypi package, please report the offending
package name to the `devpi issue tracker`_, at best including
the output of ``devpi-server --log``.  We constantly aim to get the
mirroring 100% bug free and compatible to pypi.python.org.

.. _perminstallindex:

permanent index configuration for pip
+++++++++++++++++++++++++++++++++++++++++++++++++++++

To avoid having to re-type index URLs with ``pip`` or ``easy-install`` ,
you can configure pip by setting the index-url entry in your
``$HOME/.pip/pip.conf`` (posix) or ``$HOME/pip/pip.ini`` (windows).
Let's do it for the ``root/pypi`` index::
    
    # $HOME/.pip/pip.conf
    [global]
    index-url = http://localhost:3141/root/pypi/+simple/

Alternatively, you can add a special environment variable
to your shell settings (e.g. ``.bashrc``):

   export PIP_INDEX_URL=http://localhost:3141/root/pypi/+simple/


permanent index configuration for easy_install
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++

You can configure ``easy_install`` by an entry in 
the ``$HOME/.pydistutils.cfg`` file::
    
    # $HOME/.pydistutils.cfg:
    [easy_install]
    index_url = http://localhost:3141/root/pypi/+simple/


Checking and stopping the background server
++++++++++++++++++++++++++++++++++++++++++++

At any time you can check the background server status with::

    $ devpi-server --status
    server is running with pid 14440

Or stop it::
    
    $ devpi-server --stop
    killed server pid=14440

Finally, you can also look at the logfile of the background server
(also after it has been stopped)::

    $ devpi-server --log
    last lines of devpi-server log
    2014-08-06 21:36:17,671 INFO  [req3] GET /root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz
    2014-08-06 21:36:17,710 INFO  [req3] [Wtx2] reading remote: https://pypi.python.org/packages/source/s/simplejson/simplejson-3.6.0.tar.gz, target root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz
    2014-08-06 21:36:17,878 INFO  [req3] [Wtx2] fswriter3: committed: keys: u'root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz', files_commit: +files/root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz
    2014-08-06 21:36:19,715 INFO  [req4] GET /root/pypi/+simple/simplejson/
    2014-08-06 21:36:19,822 INFO  [req5] GET /root/pypi/+f/20e/1880a8c6120b5/simplejson-3.6.0.tar.gz
    logfile at: /tmp/home/.devpi/server/.xproc/devpi-server/xprocess.log

running devpi-server permanently
+++++++++++++++++++++++++++++++++

If you want to configure a permanent devpi-server install,
you can go to :ref:`quickstart-server` to learn more.
