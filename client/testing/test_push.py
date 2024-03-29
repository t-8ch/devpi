import py
import json
from devpi.main import Hub, check_output
from devpi.push import parse_target, PyPIPush, DevpiPush

def runproc(cmd):
    args = cmd.split()
    return check_output(args)

def test_parse_target_devpi(loghub):
    class args:
        target = "user/name"
    res = parse_target(loghub, args)
    assert isinstance(res, DevpiPush)

def test_parse_target_pypi(tmpdir, loghub):
    p = tmpdir.join("pypirc")
    p.write(py.std.textwrap.dedent("""
        [distutils]
        index-servers = whatever

        [whatever]
        repository: http://anotherserver
        username: test
        password: testp
    """))
    class args:
        target = "pypi:whatever"
        pypirc = str(p)
    res = parse_target(loghub, args)
    assert isinstance(res, PyPIPush)
    assert res.user == "test"
    assert res.password == "testp"
    assert res.posturl == "http://anotherserver"

def test_push_devpi(loghub, monkeypatch, mock_http_api):
    class args:
        target = "user/name"
    pusher = parse_target(loghub, args)
    mock_http_api.set(loghub.current.index, 200, result={})
    pusher.execute(loghub, "pytest", "2.3.5")
    dict(name="pytest", version="2.3.5", targetindex="user/name")
    assert len(mock_http_api.called) == 1
    # loghub.http_api.assert_called_once_with(
    #            "push", loghub.current.index, kvdict=req)

def test_main_push_pypi(monkeypatch, tmpdir):
    from devpi.push import main
    l = []
    def mypost(method, url, data, headers, auth=None, cert=None):
        l.append((method, url, data))
        class r:
            status_code = 201
            reason = "created"
            content = json.dumps(dict(type="actionlog", status=201,
                result=[("200", "register", "pkg", "1.0"),
                        ("200", "upload", "pkg-1.3.tar.gz")]
            ))
            headers = {"content-type": "application/json"}
            _json = json.loads(content)
        r.url = url
        return r

    class args:
        clientdir = tmpdir.join("client")
        debug = False
    hub = Hub(args)
    monkeypatch.setattr(hub.http, "request", mypost)
    hub.current.reconfigure(dict(index="/some/index"))
    p = tmpdir.join("pypirc")
    p.write(py.std.textwrap.dedent("""
        [distutils]
        index-servers = whatever

        [whatever]
        repository: http://anotherserver
        username: test
        password: testp
    """))
    class args:
        pypirc = str(p)
        target = "pypi:whatever"
        nameversion = "pkg-1.0"

    main(hub, args)
    assert len(l) == 1
    method, url, data = l[0]
    assert url == hub.current.index
    req = py.std.json.loads(data)
    assert req["name"] == "pkg"
    assert req["version"] == "1.0"
    assert req["posturl"] == "http://anotherserver"
    assert req["username"] == "test"
    assert req["password"] == "testp"

class TestPush:
    def test_help(self, ext_devpi):
        result = ext_devpi("push", "-h")
        assert result.ret == 0
        result.stdout.fnmatch_lines("""
            *TARGET*
        """)
