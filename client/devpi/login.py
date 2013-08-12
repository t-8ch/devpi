
import os
import sys
import py
import json

from devpi import log
from devpi.use import parse_keyvalue_spec


def main(hub, args):
    user = args.username
    if user is None:
        user = hub.raw_input("user: ")
    password = args.password
    if password is None:
        password = py.std.getpass.getpass("password for user %s: " % user)
    data = dict(user=user, password=password)
    data = hub.http_api("post", hub.current.login, data, quiet=False)
    hub.current.set_auth(user, data["password"])
    hours = data["expiration"] / (60*60.0)
    hub.info("logged in %r, credentials valid for %.2f hours" %
             (user, hours))
    #else:
    #    hub.error("server refused %r login, code=%s" %(user, r.status_code))
    #    return 1


def logoff(hub, args):
    if hub.current.get_auth():
        hub.current.del_auth()
        hub.info("login information deleted")
    else:
        hub.error("not logged in")
