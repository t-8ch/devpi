import execnet
import json
import os
import py
import logging
from .validation import normalize_name
from pkg_resources import parse_version

from devpi_server.main import fatal

def do_export(path, xom):
    path = py.path.local(path)
    tw = py.io.TerminalWriter()
    if path.check() and path.listdir():
        fatal("export directory %s must not exist or be empty" % path)
    path.ensure(dir=1)
    tw.line("creating %s" % path)
    dumper = Exporter(tw, xom)
    dumper.dump_all(path)
    return 0

def do_import(path, xom):
    logging.basicConfig(level="INFO", format='%(message)s')
    path = py.path.local(path)
    tw = py.io.TerminalWriter()

    if not path.check():
        fatal("path for importing not found: %s" %(path))

    entries = xom.keyfs.basedir.listdir()
    if 0 and entries:
        offending = [x.basename for x in entries
                        if x.check(dotfile=0)]
        if "root" in offending:
            root = xom.keyfs.basedir.join("root")
            if root.listdir() == [root.join("pypi")]:
                offending.remove("root")
        if offending:
            fatal("serverdir must be empty: %s (found %s)"
                    %(xom.config.serverdir, offending))
    importer = Importer(tw, xom)
    importer.import_all(path)
    return 0


class Exporter:
    DUMPVERSION = "1"
    def __init__(self, tw, xom):
        self.tw = tw
        self.config = xom.config
        self.db = xom.db
        self.keyfs = xom.keyfs
        self.filestore = xom.releasefilestore

        self.export = {}
        self.export_users = self.export["users"] = {}
        self.export_indexes = self.export["indexes"] = {}

    def copy_file(self, source, dest):
        dest.dirpath().ensure(dir=1)
        source.copy(dest)
        self.tw.line("copied %s to %s" %(source, dest.relto(self.basepath)))
        return dest.relto(self.basepath)

    def warn(self, msg):
        self.tw.line(msg, red=True)

    def completed(self, msg):
        self.tw.line("dumped %s" % msg, bold=True)

    def dump_all(self, path):
        self.basepath = path
        self.export["dumpversion"] = self.DUMPVERSION
        self.export["secret"] = self.config.secret
        users = self.export_users
        for username in self.db.user_list():
            userdir = path.join(username)
            data = self.db.user_get(username, credentials=True)
            indexes = data.pop("indexes", {})
            self.export_users[username] = data
            self.completed("user %r" % username)
            for indexname, indexconfig in indexes.items():
                stage = self.db.getstage(username, indexname)
                if stage.ixconfig["type"] != "mirror":
                    indexdir = userdir.ensure(indexname, dir=1)
                    IndexDump(self, stage, indexdir).dump()
        self._write_json(path.join("dataindex.json"), self.export)


    def _write_json(self, path, data):
        writedata = json.dumps(data, indent=2)
        path.dirpath().ensure(dir=1)
        self.tw.line("writing %s, length %s" %(path.relto(self.basepath),
                                               len(writedata)))
        path.write(writedata)


class IndexDump:
    def __init__(self, exporter, stage, basedir):
        self.exporter = exporter
        self.stage = stage
        self.basedir = basedir
        indexmeta = exporter.export_indexes[stage.name] = {}
        indexmeta["projects"] = projects = {}
        indexmeta["indexconfig"] = stage.ixconfig
        indexmeta["files"] = []
        self.indexmeta = indexmeta

    def dump(self):
        xxx
        for projectname in self.stage.getprojectnames_perstage():
            data = self.stage.get_projectconfig_perstage(projectname)
            self.indexmeta["projects"][projectname] = data
            for version, versiondata in data.items():
                self.dump_releasefiles(projectname, versiondata)
            self.dump_docfile(projectname)
        self.exporter.completed("index %r" % self.stage.name)

    def dump_releasefiles(self, projectname, versiondata):
        files = versiondata.pop("+files", {})
        for basename, file in files.items():
            entry = self.exporter.filestore.getentry(file)
            file_meta = entry._mapping
            assert entry.iscached(), entry.FILE.filepath
            rel = self.exporter.copy_file(
                entry.FILE.filepath,
                self.basedir.join(projectname, entry.basename))
            self.add_filedesc("releasefile", projectname, rel,
                               entrymapping=file_meta)
            self.dump_attachments(entry)

    def add_filedesc(self, type, projectname, relpath, **kw):
        assert self.exporter.basepath.join(relpath).check()
        d = kw.copy()
        d["type"] = type
        d["projectname"] = projectname
        d["relpath"] = relpath
        self.indexmeta["files"].append(d)
        self.exporter.completed("%s: %s " %(type, relpath))

    def dump_attachments(self, entry):
        basedir = self.exporter.basepath.join("attach", entry.md5)
        filestore = self.exporter.filestore
        for type in filestore.iter_attachment_types(md5=entry.md5):
            for i, attachment in enumerate(filestore.iter_attachments(
                    md5=entry.md5, type=type)):
                data = json.dumps(attachment)
                p = basedir.ensure(type, str(i))
                p.write(data)
                basedir.ensure(type, str(i)).write(data)
                self.exporter.completed("wrote attachment %s [%s]" %
                                 (p.relto(self.basedir), entry.basename))

    def dump_docfile(self, projectname):
        content = self.stage.get_doczip(projectname)
        if content:
            p = self.basedir.join(projectname + ".zip")
            with p.open("wb") as f:
                f.write(content)
            relpath = p.relto(self.exporter.basepath)
            self.add_filedesc("doczip", projectname, relpath)

class Importer:
    def __init__(self, tw, xom):
        self.tw = tw
        self.xom = xom
        self.db = xom.db
        self.filestore = xom.releasefilestore
        self.tw = tw

    def read_json(self, path):
        self.tw.line("reading json: %s" %(path,))
        return json.loads(path.read("rb"))

    def warn(self, msg):
        self.tw.line(msg, red=True)

    def import_all(self, path):
        self.import_rootdir = path
        self.import_data = self.read_json(path.join("dataindex.json"))
        dumpversion = self.import_data["dumpversion"]
        if dumpversion != "1":
            fatal("incompatible dumpversion: %r" %(dumpversion,))
        self.import_users = self.import_data["users"]
        self.import_indexes = self.import_data["indexes"]
        self.xom.config.secret = secret = self.import_data["secret"]
        self.xom.config.secretfile.write(secret)

        # first create all users
        for user, userconfig in self.import_users.items():
            self.db._user_set(user, userconfig)

        # memorize index inheritance structure
        tree = IndexTree()
        tree.add("root/pypi")  # a root index
        for stagename, import_index in self.import_indexes.items():
            bases = import_index["indexconfig"].get("bases")
            tree.add(stagename, bases)

        # create stages in inheritance/root-first order
        stages = []
        for stagename in tree.iternames():
            if stagename == "root/pypi":
                assert self.db.index_exists(stagename)
                continue
            import_index = self.import_indexes[stagename]
            indexconfig = import_index["indexconfig"]
            stage = self.db.create_stage(stagename, None, **indexconfig)
            stages.append(stage)
        del tree

        # create projects and releasefiles for each index
        for stage in stages:
            assert stage.name != "root/pypi"
            indexdir = self.import_rootdir.join("users", stage.name)
            import_index = self.import_indexes[stage.name]
            projects = import_index["projects"]
            #normalized = self.normalize_index_projects(projects)
            for project, versions in projects.items():
                for version, versiondata in versions.items():
                    assert "+files" not in versiondata
                    if not versiondata.get("version"):
                        name = versiondata["name"]
                        self.warn("%r: ignoring project metadata without "
                                  "version information. " % name)
                        continue
                    stage.register_metadata(versiondata)

            # import release files
            for filedesc in import_index["files"]:
                self.import_filedesc(stage, filedesc)

    def import_filedesc(self, stage, filedesc):
        assert stage.ixconfig["type"] != "mirror"
        rel = filedesc["relpath"]
        projectname = filedesc["projectname"]
        p = self.import_rootdir.join(rel)
        assert p.check(), p
        if filedesc["type"] == "releasefile":
            mapping = filedesc["entrymapping"]
            entry = stage.store_releasefile(p.basename, p.read("rb"),
                        last_modified=mapping["last_modified"])
            assert entry.md5 == mapping["md5"]
            assert entry.size == mapping["size"]
            self.import_attachments(entry.md5)
        elif filedesc["type"] == "doczip":
            stage.store_doczip(projectname, p.read("rb"))
        else:
            fatal("unknown file type: %s" % (type,))

    def import_attachments(self, md5):
        md5dir = self.import_rootdir.join("attach", md5)
        if not md5dir.check():
            return
        for type_path in md5dir.listdir():
            type = type_path.basename
            for i in range(len(type_path.listdir())):
                attachment_data = type_path.join(str(i)).read()
                self.import_attachment(md5, type, attachment_data)

    def import_attachment(self, md5, type, attachment_data):
        self.tw.line("importing attachment %s/%s" %(md5, type))
        self.filestore.add_attachment(md5=md5, type=type, data=attachment_data)

    def normalize_index_projects(self, index):
        # index is a devpi-server 1.0 nested mapping of
        # names -> version->versiondata
        # We normalize names according to the latest version
        normname2versions = {}
        for name, versions in index.items():
            d = normname2versions.setdefault(normalize_name(name), {})
            d.update(versions)

        newindex = {}
        for name, versions in normname2versions.items():
            maxver = None
            for ver in versions:
                new = parse_version(ver)
                if maxver is None or new > parsed:
                    maxver = ver
                    parsed = new
            # set normalized name on all version specific metadata
            normalized_name = versions[maxver]["name"]
            newversions = {}
            changed = False
            for ver, verdata in versions.items():
                if verdata["name"] != normalized_name:
                    self.warn("normalizing project name: %s to %s" % (
                              verdata["name"], normalized_name))
                    verdata["name"] = normalized_name
                newversions[ver] = verdata

            newindex[normalized_name] = newversions

        return newindex



class IndexTree:
    """ sort index inheritance structure to that we can
    create in root->child order.
    """
    def __init__(self):
        self.name2children = {}
        self.name2bases = {}

    def add(self, name, bases=None):
        self.name2bases[name] = bases or []
        if not bases:
            self.name2children.setdefault(None, []).append(name)
        else:
            for base in bases:
                children = self.name2children.setdefault(base, [])
                children.append(name)

    def iternames(self):
        pending = [None]
        created = set()
        while pending:
            name = pending.pop(0)
            for base in self.name2bases.get(name, []):
                if base not in created:
                    pending.append(name)
                    break
            else:
                if name not in created:
                    if name:
                        yield name
                    created.add(name)
                    for child in self.name2children.get(name, []):
                        if child not in created:
                            pending.append(child)

