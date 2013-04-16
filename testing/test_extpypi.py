
import pytest
from devpi_server.extpypi import (DistURL, parse_index, HTTPCacheAdapter,
     FSCache)

class TestDistURL:
    def test_basename(self):
        d = DistURL("http://codespeak.net/basename")
        assert d.basename == "basename"
        d = DistURL("http://codespeak.net")
        assert not d.basename

    def test_parentbasename(self):
        d = DistURL("http://codespeak.net/simple/basename/")
        assert d.parentbasename == "basename"
        assert d.basename == ""

    def test_hashing(self):
        assert hash(DistURL("http://a")) == hash(DistURL("http://a"))
        assert DistURL("http://a") == DistURL("http://a")

    def test_eggfragment(self):
        url = DistURL("http://a/py.tar.gz#egg=py-dev")
        assert url.eggfragment == "py-dev"

class TestIndexParsing:
    simplepy = DistURL("http://pypi.python.org/simple/py/")

    def test_parse_index_simple(self):
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>""")
        link, = result.releaselinks
        assert link.basename == "py-1.4.12.zip"
        assert link.md5 == "12ab"

    @pytest.mark.parametrize("rel", ["homepage", "download"])
    def test_parse_index_with_rel(self, rel):
        result = parse_index(self.simplepy, """
               <a href="http://pylib.org" rel="%s">whatever</a>
               <a href="http://pylib2.org" rel="%s">whatever2</a>
               <a href="http://pylib3.org">py-1.0.zip</a>
               <a href="http://pylib2.org/py-1.0.zip" rel="%s">whatever2</a>
        """ % (rel,rel, rel))
        assert len(result.releaselinks) == 1
        assert result.releaselinks[0] == "http://pylib2.org/py-1.0.zip"
        assert len(result.scrapelinks) == 2
        assert result.scrapelinks[0] == "http://pylib.org"
        assert result.scrapelinks[1] == "http://pylib2.org"

    def test_parse_index_with_egg(self):
        # XXX re-check with exact setuptools egg parsing logic
        result = parse_index(self.simplepy,
            """<a href="http://bitbucket.org/download/py-dev#egg=dev" /a>""")
        assert len(result.releaselinks) == 1
        link, = result.releaselinks
        assert link.basename == "py-dev"
        assert link.eggfragment == "dev"

    def test_releasefile_and_scrape(self):
        result = parse_index(self.simplepy,
            """<a href="../../pkg/py-1.4.12.zip#md5=12ab">qwe</a>
               <a href="http://pylib.org" rel="homepage">whatever</a>
               <a href="http://pylib2.org" rel="download">whatever2</a>
        """)
        assert len(result.releaselinks) == 1
        assert len(result.scrapelinks) == 2
        result.parse_index(result.scrapelinks[0], """
               <a href="http://pylib.org/py-1.1.zip" /a>
               <a href="http://pylib.org/other" rel="download" /a>
        """, scrape=False)
        assert len(result.scrapelinks) == 2
        assert len(result.releaselinks) == 2
        assert result.releaselinks[1] == "http://pylib.org/py-1.1.zip"


class TestFSCache:
    #@pytest.mark.parametrize("item", [
    #    "something",
    #    [301, "redirect"],
    #    {"code": 301, "content": "hello"},
    #    404,
    #])
    def test_setbody(self, tmpdir, redis):
        cache = FSCache(tmpdir, redis)
        assert cache.get("http://whatever/this") is None
        r = cache.setbody("http://whatever/this", "hello")
        assert r.status_code == 200
        assert r.text == "hello"
        assert r.url == "http://whatever/this"

    def test_setmeta(self, tmpdir, redis):
        cache = FSCache(tmpdir, redis)
        r = cache.setmeta("http://whatever/that", status_code=404)
        assert r.status_code == 404
        assert r.text is None
        assert r.url == "http://whatever/that"
        r = cache.setmeta("http://whatever/that", status_code=301,
                          nextlocation="http://whatever/that/this")
        assert r.status_code == 301
        assert r.text is None
        assert r.url == "http://whatever/that"
        assert r.nextlocation == "http://whatever/that/this"



class TestHTTPCacheAdapter:
    @pytest.fixture
    def cache(self, tmpdir, redis):
        return FSCache(tmpdir, redis)

    @pytest.mark.parametrize("target", ["http://hello", "http://hello/"])
    def test_httpcacheget_ok(self, cache, target):
        class httpget:
            def __init__(self, url):
                self.url = url
                self.status_code = 200
                self.text = "hello"
        httpcache = HTTPCacheAdapter(cache, httpget)
        response = httpcache.get(target)
        assert response.status_code == 200
        assert response.text == "hello"
        del httpcache.httpget
        assert httpcache.get(target).text == "hello"

    def test_httpcacheget_redirect_ok(self, cache):
        class httpget:
            def __init__(self, url):
                self.url = url
                if url == "http://hello/world":
                    self.status_code = 301
                    self.headers = {"location": "/redirect"}
                elif url == "http://hello/redirect":
                    self.status_code = 200
                    self.text = "redirected"
                else:
                    assert 0
        httpcache = HTTPCacheAdapter(cache, httpget)
        text = httpcache.get("http://hello/world").text
        assert text == "redirected"
        del httpcache.httpget  # make sure we don't trigger network anymore
        assert httpcache.get("http://hello/world").text == "redirected"

    def test_httpcacheget_redirect_max(self, cache):
        class httpget:
            def __init__(self, url):
                self.url = url
                self.headers = {"location": "/redirect"}
                self.status_code = 301
        httpcache = HTTPCacheAdapter(cache, httpget)
        assert httpcache.get("http://whatever") == 301

