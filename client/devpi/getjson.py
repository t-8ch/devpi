import os
import sys
import py

import json

from devpi import log, cached_property
from devpi.util import url as urlutil
import posixpath

def main(hub, args=None):
    hub.set_quiet()
    current = hub.current
    args = hub.args

    path = args.path

    current = hub.current

    if path[0] != "/":
        if not current.index:
            hub.fatal("cannot use relative path without an active index")
        url = urlutil.joinpath(current.get_index_url(), path)
    else:
        url = urlutil.joinpath(current.rooturl, path)
    r = hub.http_api("get", url, quiet=True, check_version=False)
    if hub.args.verbose:
        hub.line("GET REQUEST sent to %s" % url)
        for name in sorted(r.headers):
            hub.line("%s: %s" %(name.upper(), r.headers[name]))
        hub.line()
    hub.out_json(r._json)
    return

