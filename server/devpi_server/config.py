from __future__ import unicode_literals
import base64
import os.path
import argparse

import py
from devpi_common.types import cached_property
from .log import threadlog
import devpi_server
from devpi_common.url import URL

log = threadlog

def get_default_serverdir():
    return os.environ.get("DEVPI_SERVERDIR", "~/.devpi/server")

def addoptions(parser):
    web = parser.addgroup("web serving options")
    web.addoption("--host",  type=str,
            default="localhost",
            help="domain/ip address to listen on")

    web.addoption("--port",  type=int,
            default=3141,
            help="port to listen for http requests.")

    web.addoption("--outside-url",  type=str, dest="outside_url",
            metavar="URL",
            default=None,
            help="the outside URL where this server will be reachable. "
                 "Set this if you proxy devpi-server through a web server "
                 "and the web server does not set or you want to override "
                 "the custom X-outside-url header.")

    web.addoption("--debug", action="store_true",
            help="run wsgi application with debug logging")


    mirror = parser.addgroup("pypi mirroring options (root/pypi)")
    mirror.addoption("--refresh", type=float, metavar="SECS",
            default=60,
            help="interval for consulting changelog api of pypi.python.org")

    mirror.addoption("--bypass-cdn", action="store_true",
            help="set this if you want to bypass pypi's CDN for access to "
                 "simple pages and packages, in order to rule out cache-"
                 "invalidation issues.  This will only work if you "
                 "are not using a http proxy.")

    deploy = parser.addgroup("deployment and data options")

    deploy.addoption("--version", action="store_true",
            help="show devpi_version (%s)" % devpi_server.__version__)

    deploy.addoption("--master", action="store", dest="master_url",
            help="run as a replica of the specified master server",
            default=None)

    deploy.addoption("--replica-cert", action="store", dest="replica_cert",
            metavar="pem_file",
            help="when running as a replica, use the given .pem file as the "
                 "SSL client certificate to authenticate to the server "
                 "(EXPERIMENTAL)",
            default=None)

    deploy.addoption("--gen-config", dest="genconfig", action="store_true",
            help="(unix only ) generate example config files for "
                 "nginx/supervisor/crontab, taking other passed options "
                 "into account (e.g. port, host, etc.)"
    )

    deploy.addoption("--secretfile", type=str, metavar="path",
            default="{serverdir}/.secret",
            help="file containing the server side secret used for user "
                 "validation. If it does not exist, a random secret "
                 "is generated on start up and used subsequently. ")

    deploy.addoption("--upgrade-state", action="store_true",
            dest="upgrade_state",
            help="upgrade server state if possible. ")

    deploy.addoption("--export", type=str, metavar="PATH",
            help="export devpi-server database state into PATH. "
                 "This will export all users, indices (except root/pypi),"
                 " release files, test results and documentation. "
    )
    deploy.addoption("--import", type=str, metavar="PATH",
            dest="import_",
            help="import devpi-server database from PATH where PATH "
                 "is a directory which was created by a "
                 "'devpi-server --export PATH' operation, "
                 "using the same or an earlier devpi-server version. "
                 "Note that you can only import into a fresh server "
                 "state directory (positional argument to devpi-server).")

    deploy.addoption("--passwd", action="store", metavar="USER",
            help="set password for user USER (interactive)")

    deploy.addoption("--serverdir", type=str, metavar="DIR", action="store",
            default=None,
            help="directory for server data.  By default, "
                 "$DEVPI_SERVERDIR is used if it exists, "
                 "otherwise the default is '~/.devpi/server'")

    bg = parser.addgroup("background server")
    bg.addoption("--start", action="store_true",
            help="start the background devpi-server")
    bg.addoption("--stop", action="store_true",
            help="stop the background devpi-server")
    bg.addoption("--status", action="store_true",
            help="show status of background devpi-server")
    bg.addoption("--log", action="store_true",
            help="show logfile content of background server")
    #group.addoption("--pidfile", action="store",
    #        help="set pid file location")
    #group.addoption("--logfile", action="store",
    #        help="set log file file location")

def load_setuptools_entrypoints():
    try:
        from pkg_resources import iter_entry_points, DistributionNotFound
    except ImportError:
        return # XXX issue a warning
    for ep in iter_entry_points('devpi_server'):
        try:
            plugin = ep.load()
        except DistributionNotFound:
            continue
        yield plugin, ep.dist


def try_argcomplete(parser):
    try:
        import argcomplete
    except ImportError:
        pass
    else:
        argcomplete.autocomplete(parser)

def parseoptions(argv, addoptions=addoptions, hook=None):
    parser = MyArgumentParser(
        description="Start a server which serves multiples users and "
                    "indices. The special root/pypi index is a real-time "
                    "mirror of pypi.python.org and is created by default. "
                    "All indices are suitable for pip or easy_install usage "
                    "and setup.py upload ... invocations."
    )

    addoptions(parser)
    if hook:
        hook.devpiserver_add_parser_options(parser)
    try_argcomplete(parser)
    raw = [str(x) for x in argv[1:]]
    args = parser.parse_args(raw)
    args._raw = raw
    config = Config(args, hook=hook)
    return config

class MyArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        if "defaultget" in kwargs:
            self._defaultget = kwargs.pop("defaultget")
        else:
            self._defaultget = {}.__getitem__
        super(MyArgumentParser, self).__init__(*args, **kwargs)

    def addoption(self, *args, **kwargs):
        opt = super(MyArgumentParser, self).add_argument(*args, **kwargs)
        self._processopt(opt)
        return opt

    def _processopt(self, opt):
        try:
            opt.default = self._defaultget(opt.dest)
        except KeyError:
            pass
        if opt.help and opt.default:
            opt.help += " [%s]" % opt.default

    def addgroup(self, *args, **kwargs):
        grp = super(MyArgumentParser, self).add_argument_group(*args, **kwargs)
        def group_addoption(*args2, **kwargs2):
            opt = grp.add_argument(*args2, **kwargs2)
            self._processopt(opt)
            return opt
        grp.addoption = group_addoption
        return grp


class ConfigurationError(Exception):
    """ incorrect configuration or environment settings. """

class PluginManager:
    def __init__(self, plugins):
        self._plugins = plugins

    def _call_plugins(self, _name, **kwargs):
        results = []
        for plug, distinfo in self._plugins:
            meth = getattr(plug, _name, None)
            if meth is not None:
                name = "%s.%s" % (
                            getattr(plug, "__class__", plug).__name__,
                            meth.__name__)
                with threadlog.around("debug", "call: %s ", name):
                    results.append(meth(**kwargs))
            #else:
            #    threadlog.error("no plugin hook %s on %s", _name, plug)
        return results

    def devpiserver_pyramid_configure(self, config, pyramid_config):
        return self._call_plugins("devpiserver_pyramid_configure",
                                  config=config, pyramid_config=pyramid_config)

    def devpiserver_add_parser_options(self, parser):
        return self._call_plugins("devpiserver_add_parser_options",
                                  parser=parser)

    def devpiserver_run_commands(self, xom):
        return self._call_plugins("devpiserver_run_commands",
                                  xom=xom)

    def devpiserver_on_upload(self, stage, projectname, version, link):
        return self._call_plugins("devpiserver_on_upload",
                                  stage=stage, projectname=projectname,
                                  version=version, link=link)

    def devpiserver_on_changed_versiondata(self, stage, projectname, version,
                                           metadata):
        return self._call_plugins("devpiserver_on_changed_versiondata",
                                  stage=stage, projectname=projectname,
                                  version=version, metadata=metadata)

    def devpiserver_pypi_initial(self, stage, name2serials):
        return self._call_plugins("devpiserver_pypi_initial",
                                  stage=stage,
                                  name2serials=name2serials)


class Config:
    def __init__(self, args, hook):
        self.args = args
        if self.args.master_url:
            self.master_url = URL(self.args.master_url)
        serverdir = args.serverdir
        if serverdir is None:
            serverdir = get_default_serverdir()
        self.serverdir = py.path.local(os.path.expanduser(serverdir))

        if args.secretfile == "{serverdir}/.secret":
            self.secretfile = self.serverdir.join(".secret")
        else:
            self.secretfile = py.path.local(
                    os.path.expanduser(args.secretfile))

        self.hook = hook

    @cached_property
    def secret(self):
        if not self.secretfile.check():
            self.secretfile.dirpath().ensure(dir=1)
            self.secretfile.write(base64.b64encode(os.urandom(32)))
            s = py.std.stat
            self.secretfile.chmod(s.S_IRUSR|s.S_IWUSR)
        return self.secretfile.read()

def getpath(path):
    return py.path.local(os.path.expanduser(str(path)))

def render(tw, confname, format=None, **kw):
    result = render_string(confname, format=format, **kw)
    return result

def render_string(confname, format=None, **kw):
    template = confname + ".template"
    from pkg_resources import resource_string
    templatestring = resource_string("devpi_server.cfg", template)
    if not py.builtin._istext(templatestring):
        templatestring = py.builtin._totext(templatestring, "utf-8")

    kw = dict((x[0], str(x[1])) for x in kw.items())
    if format is None:
        result = templatestring.format(**kw)
    else:
        result = templatestring % kw
    return result
