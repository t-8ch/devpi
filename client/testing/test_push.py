import sys
import py
import json
import pytest
import types
from devpi.main import Hub, check_output

def runproc(cmd):
    args = cmd.split()
    return check_output(args)


def test_main(monkeypatch, tmpdir):
    from devpi.push import main
    l = []
    def mypost(method, url, data, headers):
        l.append((method, url, data))
        class r:
            status_code = 201
            reason = "created"
            content = json.dumps(dict(type="actionlog", status=201,
                result=[("register", "pkg", "1.0"),
                        ("upload", "pkg-1.3.tar.gz")]
            ))
            headers = {"content-type": "application/json"}
        return r

    class args:
        clientdir = tmpdir.join("client")
        debug = False
    import devpi.server
    monkeypatch.setattr(devpi.server, "handle_autoserver", lambda x,y: None)
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
        posturl = "whatever"
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
            *release*
            *url*
        """)
