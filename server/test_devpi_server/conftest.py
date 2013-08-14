
import re
import logging
from webtest.forms import Upload
import mimetypes
import pytest
import py
from devpi_server.main import XOM, add_keys


log = logging.getLogger(__name__)

def pytest_addoption(parser):
    parser.addoption("--catchall", action="store_true", default=False,
        help="run bottle apps in catchall mode to see exceptions")
    parser.addoption("--remote", action="store_true", default=False,
        help="run tests involving remote services (pypi.python.org)")

@pytest.fixture()
def caplog(caplog):
    """ enrich the pytest-capturelog funcarg. """
    caplog.setLevel(logging.DEBUG)
    def getrecords(msgrex=None):
        if msgrex is not None:
            msgrex = re.compile(msgrex)
        recs = []
        for rec in caplog.records():
            if msgrex is not None and not msgrex.search(rec.getMessage()):
                continue
            recs.append(rec)
        return recs
    caplog.getrecords = getrecords
    return caplog

@pytest.fixture
def xom_notmocked(request):
    from devpi_server.main import parseoptions, XOM
    config = parseoptions(["devpi-server"])
    xom = XOM(config)
    request.addfinalizer(xom.shutdown)
    return xom

@pytest.fixture
def xom(request, keyfs, filestore, httpget):
    from devpi_server.main import parseoptions, XOM
    from devpi_server.extpypi import ExtDB
    config = parseoptions(["devpi-server"])
    xom = XOM(config)
    xom.keyfs = keyfs
    xom.releasefilestore = filestore
    xom.httpget = httpget
    xom.extdb = ExtDB(xom=xom)
    xom.extdb.setextsimple = httpget.setextsimple
    xom.extdb.url2response = httpget.url2response
    request.addfinalizer(xom.shutdown)
    return xom

@pytest.fixture
def httpget(pypiurls):
    url2response = {}
    class MockHTTPGet:
        def __init__(self):
            self.url2response = {}

        def __call__(self, url, allow_redirects=False):
            class mockresponse:
                def __init__(xself, url):
                    fakeresponse = self.url2response.get(url)
                    if fakeresponse is None:
                        fakeresponse = dict(status_code = 404)
                    xself.__dict__.update(fakeresponse)
                    xself.url = url
                    xself.allow_redirects = allow_redirects
                def __repr__(xself):
                    return "<mockresponse %s url=%s>" % (xself.status_code,
                                                         xself.url)
            r = mockresponse(url)
            log.debug("returning %s", r)
            return r

        def mockresponse(self, url, **kw):
            if "status_code" not in kw:
                kw["status_code"] = 200
            log.debug("set mocking response %s %s", url, kw)
            self.url2response[url] = kw

        def setextsimple(self, name, text=None, pypiserial=10000, **kw):
            headers = kw.setdefault("headers", {})
            headers["X-PYPI-LAST-SERIAL"] = pypiserial
            return self.mockresponse(pypiurls.simple + name + "/",
                                      text=text, **kw)

        def setextfile(self, path, content, **kw):
            headers = {"content-length": len(content),
                       "content-type": mimetypes.guess_type(path),
                       "last-modified": "today",}
            if path.startswith("/") and pypiurls.base.endswith("/"):
                path = path.lstrip("/")
            return self.mockresponse(pypiurls.base + path,
                                     raw=py.io.BytesIO(content),
                                     headers=headers,
                                     **kw)


    return MockHTTPGet()

@pytest.fixture
def filestore(keyfs):
    from devpi_server.filestore import ReleaseFileStore
    return ReleaseFileStore(keyfs)

@pytest.fixture
def keyfs(tmpdir):
    from devpi_server.keyfs import KeyFS
    keyfs = KeyFS(tmpdir.join("keyfs"))
    add_keys(keyfs)
    return keyfs

@pytest.fixture
def extdb(xom):
    return xom.extdb

@pytest.fixture
def pypiurls():
    from devpi_server.extpypi import PYPIURL_SIMPLE, PYPIURL
    class PyPIURL:
        def __init__(self):
            self.base = PYPIURL
            self.simple = PYPIURL_SIMPLE
    return PyPIURL()

@pytest.fixture
def db(xom):
    from devpi_server.db import DB
    from devpi_server.main import set_default_indexes
    db = DB(xom)
    set_default_indexes(db)
    return db

@pytest.fixture
def mapp(testapp):
    return Mapp(testapp)

class Mapp:
    def __init__(self, testapp):
        self.testapp = testapp

    def delete_user(self, user, code=200):
        r = self.testapp.delete_json("/%s" % user, expect_errors=True)
        assert r.status_code == code

    def getapi(self, relpath="/"):
        path = relpath.strip("/")
        if not path:
            path = "/+api"
        else:
            path = "/%s/+api" % path
        r = self.testapp.get(path)
        assert r.status_code == 200
        class API:
            def __init__(self):
                self.__dict__.update(r.json["result"])
        return API()

    def login(self, user="root", password="", code=200):
        api = self.getapi()
        r = self.testapp.post_json(api.login,
                                  {"user": user, "password": password},
                                  expect_errors=True)
        assert r.status_code == code
        if code == 200:
            self.testapp.set_auth(user, r.json["password"])
            self.auth = user, r.json["password"]

    def login_root(self):
        self.login("root", "")

    def getuserlist(self):
        r = self.testapp.get("/", {"indexes": False}, {"Accept": "*/json"})
        assert r.status_code == 200
        return r.json["result"]

    def getindexlist(self, user=None):
        if user is None:
            user = self.testapp.auth[0]
        r = self.testapp.get("/%s/" % user, {"Accept": "*/json"})
        assert r.status_code == 200
        return r.json["result"]

    def change_password(self, user, password):
        auth = self.testapp.auth
        r = self.testapp.patch_json("/%s" % user, dict(password=password))
        assert r.status_code == 200
        self.testapp.auth = (self.testapp.auth[0],
                             r.json["result"]["password"])

    def create_user(self, user, password, email="hello@example.com", code=201):
        reqdict = dict(password=password)
        if email:
            reqdict["email"] = email
        r = self.testapp.put_json("/%s" % user, reqdict, expect_errors=True)
        assert r.status_code == code
        if code == 201:
            res = r.json["result"]
            assert res["username"] == user
            assert res.get("email") == email

    def modify_user(self, user, code=200, password=None, email=None):
        reqdict = {}
        if password:
            reqdict["password"] = password
        if email:
            reqdict["email"] = email
        r = self.testapp.patch_json("/%s" % user, reqdict, expect_errors=True)
        assert r.status_code == code
        if code == 200:
            res = r.json["result"]
            assert res["username"] == user
            for name, val in reqdict.items():
                assert res[name] == val

    def create_user_fails(self, user, password, email="hello@example.com"):
        with pytest.raises(webtest.AppError) as excinfo:
            self.create_user(user, password)
        assert "409" in excinfo.value.args[0]

    def create_and_login_user(self, user="someuser", password="123"):
        self.create_user(user, password)
        self.login(user, password)

    def getjson(self, path, code=200):
        r = self.testapp.get_json(path, {}, expect_errors=True)
        assert r.status_code == code
        return r.json

    def create_index(self, indexname, indexconfig=None, code=200):
        if indexconfig is None:
            indexconfig = {}
        if "/" in indexname:
            user, index = indexname.split("/")
        else:
            user, password = self.testapp.auth
            index = indexname
        r = self.testapp.put_json("/%s/%s" % (user, index), indexconfig,
                                  expect_errors=True)
        assert r.status_code == code
        if code in (200,201):
            assert r.json["result"]["type"] == "stage"
        if code in (400,):
            return r.json["message"]

    def delete_index(self, indexname, code=201):
        if "/" in indexname:
            user, index = indexname.split("/")
        else:
            user, password = self.testapp.auth
            index = indexname
        r = self.testapp.delete_json("/%s/%s" % (user, index),
                                     expect_errors=True)
        assert r.status_code == code

    def set_uploadtrigger_jenkins(self, indexname, triggerurl):
        indexurl = "/" + indexname
        r = self.testapp.get_json(indexurl)
        result = r.json["result"]
        result["uploadtrigger_jenkins"] = triggerurl
        r = self.testapp.patch_json(indexurl, result)
        assert r.status_code == 200

    def set_acl(self, indexname, users, acltype="upload"):
        r = self.testapp.get_json("/%s" % indexname)
        result = r.json["result"]
        if not isinstance(users, list):
            users = users.split(",")
        assert isinstance(users, list)
        result["acl_upload"] = users
        r = self.testapp.patch_json("/%s" % (indexname,), result)
        assert r.status_code == 200

    def get_acl(self, indexname, acltype="upload"):
        r = self.testapp.get_json("/%s" % indexname)
        return r.json["result"].get("acl_" + acltype, None)

    def create_project(self, indexname, projectname, code=201):
        user, password = self.testapp.auth
        r = self.testapp.put_json("/%s/%s/%s" % (user, indexname,
                                  projectname), {}, expect_errors=True)
        assert r.status_code == code
        if code == 201:
            assert "created" in r.json["message"]

    def delete_project(self, user, index, projectname, code=200):
        r = self.testapp.delete_json("/%s/%s/%s" % (user, index,
                projectname), {}, expect_errors=True)
        assert r.status_code == code

    def upload_file_pypi(self, user, index, basename, content,
                         name, version, code=200):
        r = self.testapp.post("/%s/%s/" % (user, index),
            {":action": "file_upload", "name": name, "version": version,
             "content": Upload(basename, content)}, expect_errors=True)
        assert r.status_code == code


    def upload_doc(self, user, index, basename, content, name, version,
                         code=200):

        r = self.testapp.post("/%s/%s/" % (user, index),
            {":action": "doc_upload", "name": name, "version": version,
             "content": Upload(basename, content)}, expect_errors=True)
        assert r.status_code == code

from webtest import TestApp as TApp

class MyTestApp(TApp):
    auth = None

    def set_auth(self, user, password):
        self.auth = (user, password)

    def _gen_request(self, method, url, **kw):
        if self.auth:
            headers = kw.get("headers")
            if not headers:
                headers = kw["headers"] = {}
            auth = ("%s:%s" % self.auth).encode("base64")
            headers["Authorization"] = "Basic %s" % auth
            #print ("setting auth header %r %s %s" % (auth, method, url))
        return super(MyTestApp, self)._gen_request(method, url, **kw)

    def push(self, url, params=None, **kw):
        kw.setdefault("expect_errors", True)
        return self._gen_request("push", url, params=params, **kw)

    def get(self, *args, **kwargs):
        if "expect_errors" not in kwargs:
            kwargs["expect_errors"] = True
        return super(MyTestApp, self).get(*args, **kwargs)

    def get_json(self, *args, **kwargs):
        headers = kwargs.setdefault("headers", {})
        headers["Accept"] = "application/json"
        self.x = 1
        return super(MyTestApp, self).get(*args, **kwargs)




@pytest.fixture
def testapp(request, xom):
    app = xom.create_app(catchall=False, immediatetasks=-1)
    return MyTestApp(app)


### incremental testing

def pytest_runtest_makereport(item, call):
    if "incremental" in item.keywords:
        if call.excinfo is not None:
            parent = item.parent
            parent._previousfailed = item

def pytest_runtest_setup(item):
    if "incremental" in item.keywords:
        previousfailed = getattr(item.parent, "_previousfailed", None)
        if previousfailed is not None:
            pytest.xfail("previous test failed (%s)" %previousfailed.name)
