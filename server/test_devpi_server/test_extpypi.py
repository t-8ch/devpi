from __future__ import unicode_literals
import pytest

from devpi_server.extpypi import *
from devpi_server.main import Fatal, PYPIURL_XMLRPC
from test_devpi_server.conftest import getmd5


class TestIndexParsing:
    simplepy = URL("http://pypi.python.org/simple/py/")

    def test_parse_index_simple(self):
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>""")
        link, = result.releaselinks
        assert link.basename == "py-1.4.12.zip"
        assert link.md5 == "12ab"

    def test_parse_index_simple_tilde(self):
        result = parse_index(self.simplepy,
            """<a href="/~user/py-1.4.12.zip#md5=12ab">qwe</a>""")
        link, = result.releaselinks
        assert link.basename == "py-1.4.12.zip"
        assert link.url.endswith("/~user/py-1.4.12.zip#md5=12ab")

    def test_parse_index_simple_nocase(self):
        simplepy = URL("http://pypi.python.org/simple/Py/")
        result = parse_index(simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>
               <a href="../../pkg/PY-1.4.13.zip">qwe</a>
               <a href="../../pkg/pyzip#egg=py-dev">qwe</a>
        """)
        assert len(result.releaselinks) == 3

    def test_parse_index_simple_dir_egg_issue63(self):
        simplepy = URL("http://pypi.python.org/simple/py/")
        result = parse_index(simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>
               <a href="../../pkg/#egg=py-dev">qwe</a>
        """)
        assert len(result.releaselinks) == 1

    def test_parse_index_egg_svnurl(self, monkeypatch):
        # strange case reported by fschulze/witsch where
        # urlparsing will yield a fragment for svn urls.
        # it's not exactly clear how urlparse.uses_fragment
        # sometimes contains "svn" but it's good to check
        # that we are not sensitive to the issue.
        try:
            import urllib.parse as urlparse
        except ImportError:
            # PY2
            import urlparse
        monkeypatch.setattr(urlparse, "uses_fragment",
                            urlparse.uses_fragment + ["svn"])
        simplepy = URL("https://pypi.python.org/simple/zope.sqlalchemy/")
        result = parse_index(simplepy,
            '<a href="svn://svn.zope.org/repos/main/'
            'zope.sqlalchemy/trunk#egg=zope.sqlalchemy-dev" />'
        )
        assert len(result.releaselinks) == 0
        assert len(result.egglinks) == 0
        #assert 0, (result.releaselinks, result.egglinks)

    def test_parse_index_normalized_name(self):
        simplepy = URL("http://pypi.python.org/simple/ndg-httpsclient/")
        result = parse_index(simplepy, """
               <a href="../../pkg/ndg_httpsclient-1.0.tar.gz" />
        """)
        assert len(result.releaselinks) == 1
        assert result.releaselinks[0].url.endswith("ndg_httpsclient-1.0.tar.gz")

    def test_parse_index_two_eggs_same_url(self):
        simplepy = URL("http://pypi.python.org/simple/Py/")
        result = parse_index(simplepy,
            """<a href="../../pkg/pyzip#egg=py-dev">qwe2</a>
               <a href="../../pkg/pyzip#egg=py-dev">qwe</a>
        """)
        assert len(result.releaselinks) == 1

    def test_parse_index_simple_nomatch(self):
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.3.html">qwe</a>""")
        assert not result.releaselinks

    @pytest.mark.parametrize("rel", ["homepage", "download"])
    def test_parse_index_with_rel(self, rel):
        result = parse_index(self.simplepy, """
               <a href="http://pylib.org" rel="%s">whatever</a>
               <a href="http://pylib2.org" rel="%s">whatever2</a>
               <a href="http://pylib3.org">py-1.0.zip</a>
               <a href="http://pylib2.org/py-1.0.zip" rel="%s">whatever2</a>
        """ % (rel,rel, rel))
        assert len(result.releaselinks) == 1
        link, = result.releaselinks
        assert link == "http://pylib2.org/py-1.0.zip"
        assert len(result.crawllinks) == 2
        assert result.crawllinks == \
                    set(["http://pylib.org", "http://pylib2.org"])

    def test_parse_index_invalid_link(self, pypistage):
        result = parse_index(self.simplepy, '''
                <a rel="download" href="http:/host.com/123" />
        ''')
        assert result.crawllinks

    def test_parse_index_with_egg(self):
        result = parse_index(self.simplepy,
            """<a href="http://bb.org/download/py.zip#egg=py-dev" />
               <a href="http://bb.org/download/py-1.0.zip" />
               <a href="http://bb.org/download/py.zip#egg=something-dev" />
        """)
        assert len(result.releaselinks) == 2
        link, link2 = result.releaselinks
        assert link.basename == "py.zip"
        assert link.eggfragment == "py-dev"
        assert link2.basename == "py-1.0.zip"

    def test_parse_index_with_wheel(self):
        result = parse_index(self.simplepy,
            """<a href="pkg/py-1.0-cp27-none-linux_x86_64.whl" />
        """)
        assert len(result.releaselinks) == 1
        link, = result.releaselinks
        assert link.basename == "py-1.0-cp27-none-linux_x86_64.whl"

    @pytest.mark.parametrize("basename", [
        "py-1.3.1.tar.gz",
        "py-1.3.1-1.fc12.src.rpm",
        "py-docs-1.0.zip",
        "py-1.1.0.win-amd64.exe",
        "py.tar.gz",
        "py-0.8.msi",
        "py-0.10.0.dmg",
        "py-0.8.deb",
        "py-12.0.0.win32-py2.7.msi",
        "py-1.3.1-1.0rc4.tar.gz", "py-1.0.1.tar.bz2"])
    def test_parse_index_with_valid_basenames(self, basename):
        result = parse_index(self.simplepy, '<a href="pkg/%s" />' % basename)
        assert len(result.releaselinks) == 1
        link, = result.releaselinks
        assert link.basename == basename

    def test_parse_index_with_num_in_projectname(self):
        simple = URL("http://pypi.python.org/simple/py-4chan/")
        result = parse_index(simple, '<a href="pkg/py-4chan-1.0.zip"/>')
        assert len(result.releaselinks) == 1
        assert result.releaselinks[0].basename == "py-4chan-1.0.zip"

    def test_parse_index_unparseable_url(self):
        simple = URL("http://pypi.python.org/simple/x123/")
        result = parse_index(simple, '<a href="http:" />')
        assert len(result.releaselinks) == 0


    def test_parse_index_ftp_ignored_for_now(self):
        result = parse_index(self.simplepy,
            """<a href="http://bb.org/download/py-1.0.zip" />
               <a href="ftp://bb.org/download/py-1.0.tar.gz" />
               <a rel="download" href="ftp://bb.org/download/py-1.1.tar.gz" />
        """)
        assert len(result.releaselinks) == 1
        link, = result.releaselinks
        assert link.basename == "py-1.0.zip"

    def test_parse_index_with_two_eggs_ordering(self):
        # it seems that pip/easy_install in some cases
        # rely on the exact ordering of eggs in the html page
        # for example with nose, there are two eggs and the second/last
        # one is chosen due to the internal pip/easy_install algorithm
        result = parse_index(self.simplepy,
            """<a href="http://bb.org/download/py.zip#egg=py-dev" />
               <a href="http://other/master#egg=py-dev" />
        """)
        assert len(result.releaselinks) == 2
        link1, link2 = result.releaselinks
        assert link1.basename == "master"
        assert link1.eggfragment == "py-dev"
        assert link2.basename == "py.zip"
        assert link2.eggfragment == "py-dev"

    def test_parse_index_with_matchingprojectname_no_version(self):
        result = parse_index(self.simplepy,
            """<a href="http://bb.org/download/p.zip" />
            <a href="http://bb.org/download/py-1.0.zip" />""")
        assert len(result.releaselinks) == 1

    def test_parse_index_with_non_parseable_hrefs(self):
        result = parse_index(self.simplepy,
            """<a href="qlkwje 1lk23j123123" />
            <a href="http://bb.org/download/py-1.0.zip" />""")
        assert len(result.releaselinks) == 1

    def test_releasefile_and_scrape(self):
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>
               <a href="http://pylib.org" rel="homepage">whatever</a>
               <a href="http://pylib2.org" rel="download">whatever2</a>
        """)
        assert len(result.releaselinks) == 1
        assert len(result.crawllinks) == 2
        result.parse_index(URL("http://pylib.org"), """
               <a href="http://pylib.org/py-1.1-py27.egg" />
               <a href="http://pylib.org/other" rel="download" />
        """, scrape=False)
        assert len(result.crawllinks) == 2
        assert len(result.releaselinks) == 2
        links = list(result.releaselinks)
        assert links[0].url == \
                "http://pypi.python.org/pkg/py-1.4.12.zip#md5=12ab"
        assert links[1].url == "http://pylib.org/py-1.1-py27.egg"

    def test_releasefile_and_scrape_no_ftp(self):
        result = parse_index(self.simplepy,
            """<a href="ftp://pylib2.org/py-1.0.tar.gz"
                  rel="download">whatever2</a> """)
        assert len(result.releaselinks) == 0
        assert len(result.crawllinks) == 0


    def test_releasefile_md5_matching_and_ordering(self):
        """ check that md5-links win over non-md5 links anywhere.
        And otherwise the links from the index page win over scraped ones.
        """
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>
               <a href="../../pkg/py-1.4.11.zip">qwe</a>
               <a href="../../pkg/py-1.4.10.zip#md5=2222">qwe</a>
               <a href="http://pylib.org" rel="homepage">whatever</a>
               <a href="http://pylib2.org" rel="download">whatever2</a>
        """)
        assert len(result.releaselinks) == 3
        assert len(result.crawllinks) == 2
        result.parse_index(URL("http://pylib.org"), """
               <a href="http://pylib.org/py-1.4.12.zip" />
               <a href="http://pylib.org/py-1.4.11.zip#md5=1111" />
               <a href="http://pylib.org/py-1.4.10.zip#md5=12ab" />
        """, scrape=False)
        assert len(result.crawllinks) == 2
        assert len(result.releaselinks) == 3
        link1, link2, link3 = result.releaselinks
        assert link1.url == \
                "http://pypi.python.org/pkg/py-1.4.12.zip#md5=12ab"
        assert link2.url == \
                "http://pylib.org/py-1.4.11.zip#md5=1111"
        assert link3.url == \
                "http://pypi.python.org/pkg/py-1.4.10.zip#md5=2222"


class TestExtPYPIDB:
    def test_parse_project_attributes(self, pypistage):
        from devpi_server.model import _ixconfigattr
        for name in _ixconfigattr:
            assert name in pypistage.ixconfig

    def test_parse_project_nomd5(self, pypistage):
        x = pypistage.mock_simple("pytest", pkgver="pytest-1.0.zip")
        links = pypistage.get_releaselinks("pytest")
        link, = links
        assert link.entry.url == "https://pypi.python.org/pkg/pytest-1.0.zip"
        assert link.md5 == x.md5
        assert link.entrypath.endswith("/pytest-1.0.zip")
        assert link.entrypath == link.entry.relpath

    def test_parse_project_replaced_eggfragment(self, pypistage):
        pypistage.mock_simple("pytest", pypiserial=10,
            pkgver="pytest-1.0.zip#egg=pytest-dev1")
        links = pypistage.get_releaselinks("pytest")
        assert links[0].eggfragment == "pytest-dev1"
        pypistage.mock_simple("pytest", pypiserial=11,
            pkgver="pytest-1.0.zip#egg=pytest-dev2")
        links = pypistage.get_releaselinks("pytest")
        assert links[0].eggfragment == "pytest-dev2"

    def test_parse_project_replaced_md5(self, pypistage):
        x = pypistage.mock_simple("pytest", pypiserial=10,
                                   pkgver="pytest-1.0.zip")
        links = pypistage.get_releaselinks("pytest")
        assert links[0].md5 == x.md5
        y = pypistage.mock_simple("pytest", pypiserial=11,
                                   pkgver="pytest-1.0.zip")
        links = pypistage.get_releaselinks("pytest")
        assert links[0].md5 == y.md5
        assert x.md5 != y.md5

    def test_get_versiondata(self, pypistage):
        pypistage.mock_simple("Pytest", pkgver="pytest-1.0.zip")
        data = pypistage.get_versiondata("Pytest", "1.0")
        assert data["+elinks"]
        assert data["name"] == "Pytest"
        assert data["version"] == "1.0"
        assert pypistage.get_projectname("pytest") == "Pytest"

    def test_get_versiondata_with_egg(self, pypistage):
        pypistage.mock_simple("pytest", text='''
            <a href="../../pkg/tip.zip#egg=pytest-dev" />''')
        data = pypistage.get_versiondata("Pytest", "egg=pytest-dev")
        assert data["+elinks"]

    def test_parse_and_scrape(self, pypistage):
        md5 = getmd5("123")
        pypistage.mock_simple("pytest", text='''
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="https://download.com/index.html" />
            '''.format(md5=md5), pypiserial=20)
        pypistage.url2response["https://download.com/index.html"] = dict(
            status_code=200, text = '''
                <a href="pytest-1.1.tar.gz" /> ''',
            headers = {"content-type": "text/html"})
        links = pypistage.get_releaselinks("pytest")
        assert len(links) == 2
        assert links[0].entry.url == "https://download.com/pytest-1.1.tar.gz"
        assert links[0].entrypath.endswith("/pytest-1.1.tar.gz")

        links = pypistage.get_linkstore_perstage("pytest", "1.0").get_links()
        assert len(links) == 1
        assert links[0].basename == "pytest-1.0.zip"
        assert links[0].entry.md5 == md5

        # check refresh
        md5b = getmd5("456")
        pypistage.mock_simple("pytest", text='''
                <a href="../../pkg/pytest-1.0.1.zip#md5={md5b}" />
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="https://download.com/index.html" />
            '''.format(md5=md5, md5b=md5b), pypiserial=25)
        links = pypistage.get_releaselinks("pytest")
        assert len(links) == 3
        assert links[1].entry.url == "https://pypi.python.org/pkg/pytest-1.0.1.zip"
        assert links[1].entrypath.endswith("/pytest-1.0.1.zip")

    def test_parse_and_scrape_non_html_ignored(self, pypistage):
        pypistage.mock_simple("pytest", text='''
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="https://download.com/index.html" />
            ''', pypiserial=20)
        pypistage.url2response["https://download.com/index.html"] = dict(
            status_code=200, text = '''
                <a href="pytest-1.1.tar.gz" /> ''',
            headers = {"content-type": "text/plain"})
        links = pypistage.get_releaselinks("pytest")
        assert len(links) == 1

    def test_get_releaselinks_cache_refresh_semantics(self, pypistage):
        pypistage.mock_simple("pytest", text='''
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="https://download.com/index.html" />
            ''', pypiserial=10)

        # check get_releaselinks properly returns -2 on stale cache returns
        ret = pypistage.get_releaselinks("pytest")
        assert len(ret) == 1
        pypistage.pypimirror.process_changelog([("pytest", 0,0,0, 11)])
        with pytest.raises(pypistage.UpstreamError) as excinfo:
            pypistage.get_releaselinks("pytest")
        assert "expected 11" in excinfo.value.msg

    @pytest.mark.parametrize("errorcode", [404, -1, -2])
    def test_parse_and_scrape_error(self, pypistage, errorcode):
        pypistage.mock_simple("pytest", text='''
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="https://download.com/index.html" />
            ''')
        pypistage.url2response["https://download.com/index.html"] = dict(
            status_code=errorcode, text = 'not found')
        links = pypistage.get_releaselinks("pytest")
        assert len(links) == 1
        assert links[0].entry.url == \
                "https://pypi.python.org/pkg/pytest-1.0.zip"

    def test_scrape_not_recursive(self, pypistage):
        pypistage.mock_simple("pytest", text='''
                <a rel="download" href="https://download.com/index.html" />
            ''')
        md5=getmd5("hello")
        pypistage.url2response["https://download.com/index.html"] = dict(
            status_code=200, text = '''
                <a href="../../pkg/pytest-1.0.zip#md5={md5}" />
                <a rel="download" href="http://whatever.com" />'''.format(
                md5=md5),
            headers = {"content-type": "text/html"},
        )
        pypistage.url2response["https://whatever.com"] = dict(
            status_code=200, text = '<a href="pytest-1.1.zip#md5={md5}" />'
                             .format(md5=md5))
        links = pypistage.get_releaselinks("pytest")
        assert len(links) == 1

    def test_list_projectnames_perstage(self, pypistage):
        pypistage.mock_simple("proj1", pkgver="proj1-1.0.zip")
        pypistage.mock_simple("proj2", pkgver="proj2-1.0.zip")
        pypistage.url2response["https://pypi.python.org/simple/proj3/"] = dict(
            status_code=404)
        assert len(pypistage.get_releaselinks("proj1")) == 1
        assert len(pypistage.get_releaselinks("proj2")) == 1
        assert pypistage.get_releaselinks("proj3") == []
        assert pypistage.list_projectnames_perstage() == set(["proj1", "proj2"])

    def test_get_existing_with_302(self, pypistage):
        pypistage.mock_simple("Hello_this")
        pypistage.mock_simple("hello-World")
        pypistage.mock_simple("s-p")
        assert pypistage.get_projectname("hello-this") == "Hello_this"
        assert pypistage.get_projectname("hello_world") == "hello-World"
        assert pypistage.get_projectname("hello-world") == "hello-World"
        assert pypistage.get_projectname("s-p") == "s-p"
        assert pypistage.get_projectname("s_p") == "s-p"
        assert pypistage.get_projectname("sqwe_p") is None


def raise_ValueError():
    raise ValueError(42)

class TestRefreshManager:

    @pytest.mark.notransaction
    def test_init_pypi_mirror(self, xom, keyfs, mock):
        proxy = mock.create_autospec(XMLProxy)
        d = {"hello": 10, "abc": 42}
        proxy.list_packages_with_serial.return_value = d
        mirror = PyPIMirror(xom)
        mirror.init_pypi_mirror(proxy)
        assert mirror.name2serials == d

    @pytest.mark.notransaction
    def test_pypi_initial(self, makexom, queue, mock):
        proxy = mock.create_autospec(XMLProxy)
        d = {"hello": 10, "abc": 42}
        proxy.list_packages_with_serial.return_value = d
        class Plugin:
            def devpiserver_pypi_initial(self, stage, name2serials):
                queue.put((stage, name2serials))
        xom = makexom(plugins=[(Plugin(),None)])
        xom.pypimirror.init_pypi_mirror(proxy)
        xom.thread_pool.start()
        stage, name2serials = queue.get()
        assert name2serials == d
        for name in name2serials:
            assert py.builtin._istext(name)

    @pytest.mark.notransaction
    def test_pypichanges_loop(self, pypistage, monkeypatch, pool, mock):
        pypistage.pypimirror.process_changelog = mock.Mock()
        proxy = mock.create_autospec(XMLProxy)
        changelog = [
            ["pylib", "1.4", 12123, 'new release', 11],
            ["pytest", "2.4", 121231, 'new release', 27]
        ]
        proxy.changelog_since_serial.return_value = changelog

        # we need to have one entry in serials
        pypistage.httpget.mock_simple("pytest", pypiserial=27)
        pypistage.pypimirror.name2serials["pytest"] = 27
        mirror = pypistage.pypimirror
        pool.register(mirror)
        pool.shutdown()
        with pytest.raises(pool.Shutdown):
            mirror.thread_run(proxy)
        mirror.process_changelog.assert_called_once_with(changelog)

    def test_pypichanges_changes(self, xom, pypistage, keyfs, monkeypatch):
        assert not pypistage.pypimirror.name2serials
        pypistage.mock_simple("pytest", '<a href="pytest-2.3.tgz"/a>',
                          pypiserial=20)
        pypistage.mock_simple("Django", '<a href="Django-1.6.tgz"/a>',
                          pypiserial=11)
        assert len(pypistage.pypimirror.name2serials) == 2
        assert len(pypistage.get_releaselinks("pytest")) == 1
        assert len(pypistage.get_releaselinks("Django")) == 1
        pypistage.mock_simple("pytest", '<a href="pytest-2.4.tgz"/a>',
                          pypiserial=27)
        pypistage.mock_simple("Django", '<a href="Django-1.7.tgz"/a>',
                          pypiserial=25)
        assert len(pypistage.pypimirror.name2serials) == 2
        name2serials = pypistage.pypimirror.load_name2serials(None)
        for name in name2serials:
            assert py.builtin._istext(name)
        assert name2serials["pytest"] == 27
        assert name2serials["Django"] == 25
        b = pypistage.get_releaselinks("pytest")[0].basename
        assert b == "pytest-2.4.tgz"
        b = pypistage.get_releaselinks("Django")[0].basename
        assert b == "Django-1.7.tgz"

    def test_changelog_since_serial_nonetwork(self, pypistage, caplog,
            reqmock, pool):
        pypistage.mock_simple("pytest", pypiserial=10)
        reqreply = reqmock.mockresponse(PYPIURL_XMLRPC, code=400)
        xmlproxy = XMLProxy(PYPIURL_XMLRPC)
        mirror = pypistage.pypimirror
        pool.register(mirror)
        pool.shutdown()
        with pytest.raises(pool.Shutdown):
            mirror.thread_run(xmlproxy)
        with pytest.raises(pool.Shutdown):
            mirror.thread_run(xmlproxy)
        calls = reqreply.requests
        assert len(calls) == 2
        assert xmlrpc.loads(calls[0].body) == ((10,), "changelog_since_serial")
        assert caplog.getrecords(".*changelog_since_serial.*")

    def test_changelog_list_packages_no_network(self, makexom, mock):
        xmlproxy = mock.create_autospec(XMLProxy)
        xmlproxy.list_packages_with_serial.return_value = None
        with pytest.raises(Fatal):
            makexom(proxy=xmlproxy)
        #assert not xom.keyfs.PYPISERIALS.exists()


def test_requests_httpget_negative_status_code(xom_notmocked, monkeypatch):
    import requests.exceptions
    l = []
    def r(*a, **k):
        l.append(1)
        raise requests.exceptions.RequestException()

    monkeypatch.setattr(xom_notmocked._httpsession, "get", r)

def test_requests_httpget_timeout(xom_notmocked, monkeypatch):
    import requests.exceptions
    def httpget(url, **kw):
        assert kw["timeout"] == 1.2
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(xom_notmocked._httpsession, "get", httpget)
    r = xom_notmocked.httpget("http://notexists.qwe", allow_redirects=False,
                              timeout=1.2)
    assert r.status_code == -1

