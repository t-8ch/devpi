import os
import re
import sys
import py
from devpi.upload.setuppy import __file__ as fn_setup
from devpi.use import Current
from devpi import log
from devpi.util import version as verlib
from devpi import cached_property
from subprocess import PIPE, STDOUT

fn_setup = fn_setup.rstrip("oc")



def main(hub, args):
    # for now we use distutils/setup.py for register/upload commands.

    # we are going to invoke python setup.py register|sdist|upload
    # but we want to push to our local devpi server,
    # so we need to monkeypatch distutils in the setup.py process

    #newest_version = hub.remoteindex.getnewestversion(

    hub.require_valid_current_with_index()
    setup = hub.cwd.join("setup.py")
    if not setup.check():
        hub.fatal("no setup.py found in", hub.cwd)
    checkout = Checkout(hub, hub.cwd)
    uploadbase = hub.getdir("upload")
    exported = checkout.export(uploadbase)
    hub.info("hg-exported project to", exported)

    #set_new_version(hub, args, exported)
    if not args.onlydocs:
        exported.setup_register()
        exported.setup_upload()
    if args.onlydocs or args.withdocs:
        exported.setup_upload_docs()

def set_new_version(hub, args, exported):
    if args.setversion:
        newversion = verlib.Version(args.setversion)
        exported.change_versions(newversion)
    else:
        pkgname, version = exported.name_and_version()
        link = hub.remoteindex.getbestlink(pkgname)
        if link is None:
            log.info("no remote packages registered yet")
        else:
            indexversion = verlib.Version.frombasename(link.basename)
            if version < indexversion:
                hub.fatal(pkgname, "local", version, "lower than index",
                          indexversion)
            elif version == indexversion:
                newversion = version.autoinc()
                exported.change_versions(newversion)
                    #["setup.py", pkgname + os.sep + "__init__.py"])
                n,v = exported.name_and_version()
                assert v == newversion, (str(v), str(newversion))
            else:
                newversion = version
                log.info("good, local", version, "newer than latest remote",
                         indexversion)


def setversion(s, newversion):
    def replaceversion(match):
        vername = match.group(1)
        assign = match.group(2)
        version = match.group(3)
        if not (version[0] == version[-1]):
           return match.group(0)
        version = version[0] + str(newversion) + version[-1]
        return "%s%s%s" %(vername, assign, version)
    news = re.sub(r'''(version|__version__)(\s*=\s*)(['"]\S*['"])''',
                  replaceversion, s)
    return news


def find_parent_subpath(startpath, relpath, raising=True):
    for x in startpath.parts(reversed):
        cand = x.join(relpath)
        if cand.check():
            return cand
    if raising:
        raise ValueError("no subpath %r from %s" %(relpath, startpath))


class Checkout:
    def __init__(self, hub, setupdir):
        self.hub = hub
        self.rootpath = setupdir
        assert setupdir.join("setup.py").check(), setupdir
        self.hashg = bool(find_parent_subpath(self.rootpath,
                          ".hg", raising=False)) and py.path.local.sysfind("hg")

    def export(self, basetemp):
        if self.hashg:
            log.debug("detected hg, trying hg export")
            newrepo = basetemp.join(self.rootpath.basename)
            out = self.hub.popen_output("hg st -nmac .", cwd=self.rootpath)
            num = 0
            for fn in out.split("\n"):
                if fn.strip():
                    source = self.rootpath.join(fn)
                    dest = newrepo.join(fn)
                    dest.dirpath().ensure(dir=1)
                    source.copy(dest)
                    num += 1
            log.debug("copied", num, "files to", newrepo)
            return Exported(self.hub, newrepo, self.rootpath)
        else:
            return Exported(self.hub, self.rootpath, self.rootpath)

class Exported:
    def __init__(self, hub, rootpath, origrepo):
        self.hub = hub
        self.rootpath = rootpath
        self.origrepo = origrepo

    def __str__(self):
        return "<Exported %s>" % self.rootpath

    def detect_versioncandidates(self):
        relpaths = ["setup.py"]
        for x in self.rootpath.listdir():
            init = x.join("__init__.py")
            if init.check():
                relpaths.append(init.relto(self.rootpath))
        return relpaths

    def change_versions(self, newversion, relpaths=None):
        if relpaths is None:
            relpaths = self.detect_versioncandidates()
        for relpath in relpaths:
            cand = self.rootpath.join(relpath)
            if cand.check():
                if self.check_setversion(cand, newversion):
                    cand.copy(self.origrepo.join(relpath))
                    self.hub.info("setversion", relpath, newversion)

    def check_setversion(self, path, newversion):
        log.debug("check_setversion", path)
        content = path.read()
        newcontent = setversion(content, str(newversion))
        if newcontent != content:
            log.debug("changing", path)
            path.write(newcontent)
            return True

    def setup_fullname(self):
        setup_py = self.rootpath.join("setup.py")
        if not setup_py.check():
            self.hub.fatal("no setup.py file")
        fullname = self.hub.popen_output([sys.executable,
                                          setup_py, "--fullname"]).strip()
        self.hub.info("got local pypi-fullname", fullname)
        return fullname

    def name_and_version(self):
        return verlib.guess_pkgname_and_version(self.setup_fullname())

    def setup_register(self):
        hub = self.hub
        pypisubmit = self.hub.current.pypisubmit
        cwd = self.rootpath
        user, password = self.hub.http.auth or ("test", "test")
        if hub.args.dryrun:
            hub.info("would register package at", cwd, "to", pypisubmit)
            return
        hub.debug("registering package at", cwd, "to", pypisubmit)
        out = hub.popen_output([sys.executable, fn_setup, cwd,
             pypisubmit, user, password, "register", "-r", "devpi",],
             cwd = self.rootpath)
        if "Server response (200): OK" in out:
            hub.info("release registered", "%s-%s" % self.name_and_version())
        else:
            hub.fatal("release registration failed\n", out)

    def setup_upload(self):
        current = self.hub.current
        cwd = self.rootpath
        user, password = self.hub.http.auth
        if not user:
            self.hub.fatal("need to be logged in to perform this action")

        formats = [x.strip() for x in self.hub.args.formats.split(",")]
        for format in formats:
            if not format:
                continue
            buildcommand = []
            if format == "sdist" or format.startswith("sdist."):
                buildcommand = ["sdist"]
                parts = format.split(".", 1)
                if len(parts) > 1:
                    buildcommand.extend(["--formats", sdistformat(parts[1])])
            else:
                buildcommand.append(format)
            pre = [sys.executable, fn_setup, cwd, current.pypisubmit,
                   user, password]
            cmd = pre + buildcommand  + ["upload", "-r", "devpi",]
            out = self.hub.popen_output(cmd, cwd=cwd)
            if out is None:  # dryrun
                continue
            if "Server response (200): OK" in out:
                for line in out.split("\n")[-10:]:
                    if line.startswith("Submitting"):
                        self.hub.info(line.replace("Submitting", "submitted"))
                        break
            else:
                self.hub.fatal("could not register releasefile", out)

    def setup_upload_docs(self):
        current = self.hub.current
        cwd = self.rootpath
        user, password = self.hub.http.auth
        if not user:
            self.hub.fatal("need to be logged in to perform this action")
        if self.hub.args.dryrun:
            self.hub.info("would upload docs from", cwd, "to",
                          current.pypisubmit)
            return
        out = self.hub.popen_output(
            [sys.executable, fn_setup, cwd, current.pypisubmit,
             user, password,
             "sdist", "upload_docs", "-r", "devpi",],
            cwd=cwd)
        if "Server response (200): OK" in out:
            for line in out.split("\n")[-10:]:
                if line.startswith("Submitting"):
                    self.hub.info(line.replace("Submitting", "submitted"))
                    return
        else:
            self.hub.fatal("could not upload docs", out)


sdistformat2option = {
    "tgz": "gztar",  # gzipped tar-file
    "tar": "tar",    # un-compressed tar
    "zip": "zip",    # comparessed zip file
    "tz": "ztar",    # compressed tar file
    "tbz": "bztar",  # bzip2'ed tar-file
}

#def getallformats():
#    return set(sdistformat2option) + set(sdistformat2option.values())

def sdistformat(format):
    """ return sdist format option. """
    res = sdistformat2option.get(format, None)
    if res is None:
        if res not in sdistformat2option.values():
            raise ValueError("unknown sdist format option: %r" % res)
        res = format
    return res
