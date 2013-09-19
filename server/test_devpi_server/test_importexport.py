import pytest
from devpi_server.importexport import *
from devpi_server.main import main, Fatal
import devpi_server

def test_not_exists(tmpdir, xom):
    p = tmpdir.join("hello")
    with pytest.raises(Fatal):
         do_import(p, xom)

def test_import_wrong_dumpversion(tmpdir, xom):
    tmpdir.join("dumpversion").write("1lk23j123")
    with pytest.raises(Fatal):
        do_import(tmpdir, xom)

def test_empty_export(tmpdir, xom):
    ret = do_export(tmpdir, xom)
    assert not ret
    assert tmpdir.join("dumpversion").read() == Exporter.DUMPVERSION
    with pytest.raises(Fatal):
        do_export(tmpdir, xom)

def test_import_on_existing_server_data(tmpdir, xom):
    assert not do_export(tmpdir, xom)
    with pytest.raises(Fatal):
        do_import(tmpdir, xom)

class TestIndexTree:
    def test_basic(self):
        tree = IndexTree()
        tree.add("name1", ["name2"])
        tree.add("name2", ["name3"])
        tree.add("name3", None)
        assert list(tree.iternames()) == ["name3", "name2", "name1"]

    def test_multi_inheritance(self):
        tree = IndexTree()
        tree.add("name1", ["name2", "name3"])
        tree.add("name2", ["name4"])
        tree.add("name3", [])
        tree.add("name4", [])
        names = list(tree.iternames())
        assert len(names) == 4
        assert names.index("name1") > names.index("name2")
        assert names.index("name2") > names.index("name4")
        assert names.index("name1") == 3


class TestImportExport:
    @pytest.fixture
    def impexp(self, makemapp, gentmp):
        class ImpExp:
            def __init__(self):
                self.exportdir = gentmp()
                self.mapp1 = makemapp(options=[
                    "--export", self.exportdir]
                )

            def export(self):
                assert self.mapp1.xom.main() == 0

            def new_import(self):
                mapp2 = makemapp(options=("--import", str(self.exportdir)))
                assert mapp2.xom.main() == 0
                return mapp2
        return ImpExp()

    def test_two_indexes_inheriting(self, impexp):
        mapp1 = impexp.mapp1
        mapp1.create_and_login_user("exp")
        mapp1.create_index("dev5")
        mapp1.create_index("dev6", indexconfig=dict(bases="exp/dev5"))
        impexp.export()
        mapp2 = impexp.new_import()
        assert "exp" in mapp2.getuserlist()
        indexlist = mapp2.getindexlist("exp")
        assert indexlist["exp/dev6"]["bases"] == ["exp/dev5"]
        assert "exp/dev6" in indexlist
        assert mapp2.xom.config.secret == mapp1.xom.config.secret

    def test_upload_releasefile_with_attachment(self, impexp):
        mapp1 = impexp.mapp1
        mapp1.create_and_login_user("exp")
        mapp1.create_index("dev5")
        mapp1.use("exp/dev5")
        mapp1.upload_file_pypi("hello-1.0.tar.gz", "content",
                     "hello", "1.0")

        md5 = py.std.md5.md5("content").hexdigest()
        num = mapp1.xom.releasefilestore.add_attachment(
                    md5=md5, type="toxresult", data="123")
        impexp.export()
        mapp2 = impexp.new_import()
        stage = mapp2.xom.db.getstage("exp/dev5")
        entries = stage.getreleaselinks("hello")
        assert len(entries) == 1
        assert entries[0].FILE.get() == "content"
        x = mapp2.xom.releasefilestore.get_attachment(
            md5=md5, type="toxresult", num=num)
        assert x == "123"

    def test_user_no_index_login_works(self, impexp):
        mapp1 = impexp.mapp1
        mapp1.create_and_login_user("exp", "pass")
        impexp.export()
        mapp2 = impexp.new_import()
        mapp2.login("exp", "pass")

    def test_10_upload_docs_no_version(self, impexp):
        mapp1 = impexp.mapp1
        api = mapp1.create_and_use()
        # in devpi-server 1.0 one could upload a doc
        # without ever registering the project, leading to empty
        # versions.  We simulate it here because 1.1 http API
        # prevents this case.
        stage = mapp1.xom.db.getstage(api.stagename)
        stage._register_metadata({"name": "hello", "version": ""})
        impexp.export()
        mapp2 = impexp.new_import()
        stage = mapp2.xom.db.getstage(api.stagename)
        assert not stage.get_project_info("hello")

    def test_10_upload_un_normalized_names(self, impexp):
        mapp1 = impexp.mapp1
        api = mapp1.create_and_use()
        # in devpi-server 1.0 one could register X_Y and X-Y names
        # and they would get registeded under different names.
        # We simulate it here because 1.1 http API prevents this case.
        stage = mapp1.xom.db.getstage(api.stagename)
        stage._register_metadata({"name": "hello_x", "version": "1.0"})
        stage._register_metadata({"name": "hello-X", "version": "1.1"})
        stage._register_metadata({"name": "Hello-X", "version": "1.2"})
        impexp.export()
        mapp2 = impexp.new_import()
        stage = mapp2.xom.db.getstage(api.stagename)
        def n(name):
            return stage.get_project_info(name).name
        assert n("hello-x") == "Hello-X"
        assert n("Hello_x") == "Hello-X"


def test_normalize_index_projects(xom):
    tw = py.io.TerminalWriter()
    importer = Importer_1(tw, xom)
    index = {
                "hello": {"1.0": {"name": "hello"}},
                "Hello": {"1.9": {"name": "Hello"}},
                "hellO": {"0.9": {"name": "hellO"}},
                "world": {"1.0": {"name": "world"}},
                "World": {"0.9": {"name": "World"}},
    }
    newindex = importer.normalize_index_projects(index)
    assert len(newindex) == 2
    assert len(newindex["Hello"]) == 3
    for ver in ("0.9", "1.0", "1.9"):
        assert newindex["Hello"][ver]["name"] == "Hello"
    assert len(newindex["world"]) == 2
    assert newindex["world"]["0.9"]["name"] == "world"
    assert newindex["world"]["1.0"]["name"] == "world"
