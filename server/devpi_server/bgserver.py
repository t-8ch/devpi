
"""
interact/control devpi-server background process.
"""
import sys, os, time
import py
if sys.version_info >= (3, 0):
    from urllib import parse as urlp
else:
    import urlparse as urlp

from devpi_server.vendor.xprocess import XProcess
import requests

default_rooturl = "http://localhost:3141"

def getnetloc(url, scheme=False):
    parsed = urlp.urlparse(url)
    netloc = parsed.netloc
    if netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme:
        netloc = "%s://%s" %(parsed.scheme, netloc)
    return netloc

class BackgroundServer:
    def __init__(self, tw, xprocdir):
        self.tw = tw
        self._extlogfiles = {}
        self.xproc = XProcess(config=self, rootdir=xprocdir)
        self.info = self.xproc.getinfo("devpi-server")

    def fatal(self, msg):
        self.tw.line(msg, red=True)
        raise SystemExit(1)

    def line(self, msg, **kw):
        self.tw.line(msg, **kw)

    def _waitup(self, url, count=500):
        # try for 20 seconds to start devpi-server (which remotely
        # receives a serials list which may take a while)
        while count > 0:
            try:
                r = requests.get(url)
            except requests.exceptions.ConnectionError as e:
                time.sleep(0.1)
                count -= 1
            else:
                return True
        return False

    def start(self, args):
        filtered_args = [x for x in args._raw if x != "--start"]
        devpi_server = py.path.local.sysfind("devpi-server")
        if devpi_server is None:
            self.fatal("cannot find devpi-server binary, no auto-start")
        def prepare_devpiserver(cwd):
            url = "http://%s:%s" % (args.host, args.port)
            self.line("starting background devpi-server at %s" % url)
            argv = [devpi_server, ] + filtered_args
            #self.line("command: %s" % (argv,))
            #self.line("command: %s" % argv)
            return (lambda: self._waitup(url), argv)
        self.xproc.ensure("devpi-server", prepare_devpiserver)
        info = self.xproc.getinfo("devpi-server")
        self.pid = info.pid
        self.logfile = info.logpath
        self.line("logfile is at %s" % self.logfile)

    def stop(self):
        info = self.xproc.getinfo("devpi-server")
        ret = info.kill()
        if ret == 1:
            self.line("killed server pid=%s" % info.pid)
            return 0
        elif ret == -1:
            self.line("failed to kill server pid=%s" % info.pid, red=True)
            return 1
        self.line("no server found", red=True)
        return 0

    def log(self):
        logpath = self.info.logpath
        if not logpath.check():
            self.line("no logfile found at: %s" % logpath, red=True)
            return
        with logpath.open("r") as f:
            try:
                f.seek(-30*100, 2)
            except IOError:
                pass
            self.line("last lines of devpi-server log", bold=True)
            lines = f.readlines()
            for line in lines[1:]:
                self.line(line.rstrip())
            self.line("logfile at: %s" % logpath, bold=True)

