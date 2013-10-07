import pytest
from devpi_common.metadata import *

@pytest.mark.parametrize(("releasename", "expected"), [
    ("pytest-2.3.4.zip", ("pytest", "2.3.4", ".zip")),
    ("pytest-2.3.4-py27.egg", ("pytest", "2.3.4", "-py27.egg")),
    ("dddttt-0.1.dev38-py2.7.egg", ("dddttt", "0.1.dev38", "-py2.7.egg")),
    ("devpi-0.9.5.dev1-cp26-none-linux_x86_64.whl",
        ("devpi", "0.9.5.dev1", "-cp26-none-linux_x86_64.whl")),
    ("wheel-0.21.0-py2.py3-none-any.whl", ("wheel", "0.21.0", "-py2.py3-none-any.whl")),
    ("green-0.4.0-py2.5-win32.egg", ("green", "0.4.0", "-py2.5-win32.egg")),
    ("Candela-0.2.1.macosx-10.4-x86_64.exe", ("Candela", "0.2.1",
                                             ".macosx-10.4-x86_64.exe")),
    ("Cambiatuscromos-0.1.1alpha.linux-x86_64.exe",
        ("Cambiatuscromos", "0.1.1alpha", ".linux-x86_64.exe")),
    ("Aesthete-0.4.2.win32.exe", ("Aesthete", "0.4.2", ".win32.exe")),
    ("DTL-1.0.5.win-amd64.exe", ("DTL", "1.0.5", ".win-amd64.exe")),
    ("Cheetah-2.2.2-1.x86_64.rpm", ("Cheetah", "2.2.2-1", ".x86_64.rpm")),
    ("Cheetah-2.2.2-1.src.rpm", ("Cheetah", "2.2.2-1", ".src.rpm")),
    ("Cheetah-2.2.2-1.x85.rpm", ("Cheetah", "2.2.2-1", ".x85.rpm")),
    ("Cheetah-2.2.2.dev1.x85.rpm", ("Cheetah", "2.2.2.dev1", ".x85.rpm")),
    ("Cheetah-2.2.2.dev1.noarch.rpm", ("Cheetah", "2.2.2.dev1", ".noarch.rpm")),
    ("deferargs.tar.gz", ("deferargs", "", ".tar.gz")),
    ("Twisted-12.0.0.win32-py2.7.msi",
        ("Twisted", "12.0.0", ".win32-py2.7.msi")),
])
def test_splitbasename(releasename, expected):
    result = splitbasename(releasename)
    assert result == expected

@pytest.mark.parametrize(("releasename", "expected"), [
    ("x-2.3.zip", ("source", "sdist")),
    ("x-2.3-0.4.0.win32-py3.1.exe", ("3.1", "bdist_wininst")),
    ("x-2.3-py27.egg", ("2.7", "bdist_egg")),
    ("wheel-0.21.0-py2.py3-none-any.whl", ("2.7", "bdist_wheel")),
    ("devpi-0.9.5.dev1-cp26-none-linux_x86_64.whl", ("2.6", "bdist_wheel")),
    ("greenlet-0.4.0-py3.3-win-amd64.egg", ("3.3", "bdist_egg")),
])
def test_get_pyversion_filetype(releasename, expected):
    result = get_pyversion_filetype(releasename)
    assert result == expected

@pytest.mark.parametrize(("releasename", "expected"), [
    ("pytest-2.3.4.zip", ("pytest-2.3.4", ".zip")),
    ("green-0.4.0-py2.5-win32.egg", ("green-0.4.0-py2.5-win32", ".egg")),
    ("green-1.0.tar.gz", ("green-1.0", ".tar.gz")),
])
def test_splitext_archive(releasename, expected):
    assert splitext_archive(releasename) == expected

def test_sorted_by_version():
    l = ["hello-1.3.0.tgz", "hello-1.3.1.tgz", "hello-1.2.9.zip"]
    assert sorted_by_version(l) == \
        ["hello-1.2.9.zip", "hello-1.3.0.tgz", "hello-1.3.1.tgz"]

def test_sorted_by_version_with_attr():
    class A:
        def __init__(self, ver):
            self.ver = ver
        def __eq__(self, other):
            assert self.ver == other.ver
    l = [A("hello-1.2.0.tgz") , A("hello-1.1.0.zip")]
    x = sorted_by_version(l, attr="ver")
    l.reverse()
    assert x == l

def test_version():
    ver1 = Version("1.0")
    ver2 = Version("1.1")
    assert max([ver1, ver2]) == ver2

class TestBasenameMeta:
    def test_two_comparison(self):
        meta1 = BasenameMeta("x-1.0.tar.gz")
        meta2 = BasenameMeta("x-1.1.tar.gz")
        assert meta1 != meta2
        assert meta1 < meta2
        assert meta1.name == "x"
        assert meta1.version == "1.0"
        assert meta1.ext == ".tar.gz"
        assert meta1.obj == "x-1.0.tar.gz"

    def test_normalize_equal(self):
        meta1 = BasenameMeta("x-1.0.tar.gz")
        meta2 = BasenameMeta("X-1.0.tar.gz")
        assert meta1 == meta2
        meta3 = BasenameMeta("X-1.0.zip")
        assert meta3 != meta1
        assert meta3 > meta1

    def test_basename_attribute(self):
        class B:
            basename = "x-1.0.tar.gz"
        meta1 = BasenameMeta(B)
        meta2 = BasenameMeta("x-1.0.tar.gz")
        assert meta1 == meta2
