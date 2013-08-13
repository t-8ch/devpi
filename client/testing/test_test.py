
import py
import pytest
from devpi.util import url as urlutil
from devpi.test import *
from devpi.main import check_output
from mock import Mock

pytest_plugins = "pytester"

def test_post_tox_json_report(loghub, mock_http_api):
    mock_http_api.set("http://devpi.net", 200, result={})
    post_tox_json_report(loghub, "http://devpi.net", {"hello": "123"})
    assert len(mock_http_api.called) == 1
    loghub._getmatcher().fnmatch_lines("""
        *posting*
        *success*
    """)

def test_post_tox_json_report_error(loghub, mock_http_api):
    mock_http_api.set("http://devpi.net/+tests", 404)
    post_tox_json_report(loghub, "http://devpi.net/+tests", {"hello": "123"})
    assert len(mock_http_api.called) == 1
    loghub._getmatcher().fnmatch_lines("""
        *could not post*http://devpi.net/+tests*
    """)

class TestFunctional:
    @pytest.mark.xfail(reason="output capturing for devpi calls")
    def test_main_nopackage(self, out_devpi):
        result = out_devpi("test", "--debug", "notexists73", ret=1)
        result.fnmatch_lines([
            "*could not find/receive*",
        ])

    def test_main_example(self, out_devpi, create_and_upload):
        create_and_upload("exa-1.0", filedefs={
           "tox.ini": """
              [testenv]
              commands = python -c "print('ok')"
            """,
        })
        result = out_devpi("test", "--debug", "exa")
        assert result.ret == 0
        result = out_devpi("list", "-f", "exa")
        assert result.ret == 0
        result.stdout.fnmatch_lines("""*tests passed*""")
