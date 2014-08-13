from devpi_server.log import configure_logging
from devpi_server.main import XOM, set_default_indexes
from devpi_server.config import PluginManager, load_setuptools_entrypoints
from devpi_common.types import cached_property

import base64
import os
import py
import sys

plugins = load_setuptools_entrypoints()
hook = PluginManager(plugins)


class Args:
    master_url = ''
    outside_url = ''
    debug = True
    bypass_cdn = False
    replica_cert = False
    index_projects = True


class Config:
    serverdir = 'devpi'
    serverdir = py.path.local(os.path.expanduser(serverdir))
    secretfile = serverdir.join(".secret")
    hook = hook
    args = Args()

    @cached_property
    def secret(self):
        if not self.secretfile.check():
            self.secretfile.dirpath().ensure(dir=1)
            self.secretfile.write(base64.b64encode(os.urandom(32)))
            s = py.std.stat
            self.secretfile.chmod(s.S_IRUSR|s.S_IWUSR)
        return self.secretfile.read()

config = Config()
configure_logging(config)
xom = XOM(config)
with xom.keyfs.transaction(write=True):
    set_default_indexes(xom.model)
xom.pypimirror.init_pypi_mirror(xom.proxy)
# with xom.keyfs.transaction(write=True):
#     results = xom.config.hook.devpiserver_run_commands(xom)
#     if [x for x in results if x is not None]:
#         errors = list(filter(None, results))
#         if errors:
#             print(errors)
#             sys.exit(errors[0])
#         # sys.exit(0)
application = xom.create_app()
