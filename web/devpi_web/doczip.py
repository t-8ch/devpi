try:
    from UserDict import DictMixin
except ImportError:
    from collections import MutableMapping as DictMixin
from bs4 import BeautifulSoup
from devpi_common.archive import Archive
from devpi_common.types import cached_property
from devpi_server.log import threadlog
import json


def get_unpack_path(stage, name, version):
    # XXX this should rather be in some devpi-web managed directory area
    return stage.keyfs.basedir.join(stage.user.name, stage.index,
                                    name, version, "+doc")


def unpack_docs(stage, name, version, entry):
    # unpack, maybe a bit uncarefully but in principle
    # we are not loosing the original zip file anyway
    unpack_path = get_unpack_path(stage, name, version)
    with entry.file_open_read() as f:
        with Archive(f) as archive:
            archive.extract(unpack_path)
    threadlog.debug("%s: unpacked %s-%s docs to %s",
                    stage.name, name, version, unpack_path)
    return unpack_path


class Docs(DictMixin):
    def __init__(self, stage, name, version):
        self.stage = stage
        self.name = name
        self.version = version
        self.unpack_path = get_unpack_path(stage, name, version)

    @cached_property
    def _entries(self):
        if not self.unpack_path.exists():
            # this happens on import, when the metadata is registered, but the docs
            # aren't uploaded yet
            return {}
        html = []
        fjson = []
        for entry in self.unpack_path.visit():
            if entry.basename.endswith('.fjson'):
                fjson.append(entry)
            elif entry.basename.endswith('.html'):
                html.append(entry)
        if fjson:
            entries = dict(
                (x.relto(self.unpack_path)[:-6], x)
                for x in fjson)
        else:
            entries = dict(
                (x.relto(self.unpack_path)[:-5], x)
                for x in html)
        return entries

    def keys(self):
        return self._entries.keys()

    def __len__(self):
        return len(self.keys())

    def __iter__(self):
        return iter(self.keys())

    def __delitem__(self, name):
        raise NotImplementedError

    def __setitem__(self, name, value):
        raise NotImplementedError

    def __getitem__(self, name):
        entry = self._entries[name]
        if entry.basename.endswith('.fjson'):
            info = json.loads(entry.read())
            return dict(
                title=BeautifulSoup(info.get('title', '')).text,
                text=BeautifulSoup(info.get('body', '')).text,
                path=info.get('current_page_name', name))
        else:
            soup = BeautifulSoup(entry.read())
            body = soup.find('body')
            if body is None:
                return
            title = soup.find('title')
            if title is None:
                title = ''
            else:
                title = title.text
            return dict(
                title=title,
                text=body.text,
                path=name)


def iter_doc_contents(stage, name, version):
    docs = Docs(stage, name, version)
    for entry in docs:
        result = docs[entry]
        if result is None:
            continue
        yield result
