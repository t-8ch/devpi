# coding: utf-8
from __future__ import unicode_literals
from devpi_common.metadata import get_pyversion_filetype, splitbasename
from devpi_common.url import URL
from devpi_server.log import threadlog as log
from devpi_web.description import get_description
from devpi_web.doczip import Docs, get_unpack_path
from devpi_web.indexing import is_project_cached
from operator import attrgetter, itemgetter
from py.xml import html
from pyramid.compat import decode_path_info
from pyramid.decorator import reify
from pyramid.httpexceptions import HTTPFound, HTTPNotFound
from pyramid.interfaces import IRoutesMapper
from pyramid.response import FileResponse
from pyramid.view import notfound_view_config, view_config
import functools
import json
import py


class ContextWrapper(object):
    def __init__(self, context):
        self.context = context

    def __getattr__(self, name):
        return getattr(self.context, name)

    @reify
    def stage(self):
        stage = self.model.getstage(self.username, self.index)
        if not stage:
            raise HTTPNotFound(
                "The stage %s/%s could not be found." % (self.username, self.index))
        return stage

    @reify
    def versions(self):
        versions = self.stage.get_project_versions(self.name, sort=False)
        if not versions:
            raise HTTPNotFound("The project %s does not exist." % self.name)
        return versions

    @reify
    def verdata(self):
        verdata = self.stage.get_project_versiondata(self.name, self.version)
        if not verdata and self.versions:
            raise HTTPNotFound(
                "The version %s of project %s does not exist." % (
                    self.version, self.name))
        return verdata

    @reify
    def project_version(self):
        return self.stage.get_project_version(self.name, self.version)


def get_doc_path_info(context, request):
    relpath = request.matchdict['relpath']
    if not relpath:
        raise HTTPFound(location="index.html")
    doc_path = get_unpack_path(context.stage, context.name, context.version)
    if not doc_path.check():
        raise HTTPNotFound("No documentation available.")
    doc_path = doc_path.join(relpath)
    if not doc_path.check():
        raise HTTPNotFound("File %s not found in documentation." % relpath)
    return doc_path, relpath


@view_config(route_name="docroot", request_method="GET")
def doc_serve(context, request):
    """ Serves the raw documentation files. """
    context = ContextWrapper(context)
    doc_path, relpath = get_doc_path_info(context, request)
    return FileResponse(str(doc_path))


@view_config(
    route_name="docviewroot",
    request_method="GET",
    renderer="templates/doc.pt")
def doc_show(context, request):
    """ Shows the documentation wrapped in an iframe """
    context = ContextWrapper(context)
    stage = context.stage
    name, version = context.name, context.version
    doc_path, relpath = get_doc_path_info(context, request)
    return dict(
        title="%s-%s Documentation" % (name, version),
        base_url=request.route_url(
            "docroot", user=stage.user.name, index=stage.index,
            name=name, version=version, relpath=''),
        baseview_url=request.route_url(
            "docviewroot", user=stage.user.name, index=stage.index,
            name=name, version=version, relpath=''),
        url=request.route_url(
            "docroot", user=stage.user.name, index=stage.index,
            name=name, version=version, relpath=relpath))


@notfound_view_config(renderer="templates/notfound.pt")
def notfound(request):
    if request.method == 'POST':
        request.response.status = 404
        return dict(msg=request.exception)
    path = decode_path_info(request.environ['PATH_INFO'] or '/')
    registry = request.registry
    mapper = registry.queryUtility(IRoutesMapper)
    if mapper is not None and path.endswith('/'):
        # redirect URLs with a trailing slash to URLs without one, if there
        # is a matching route
        nonslashpath = path.rstrip('/')
        for route in mapper.get_routes():
            if route.match(nonslashpath) is not None:
                qs = request.query_string
                if qs:
                    qs = '?' + qs
                return HTTPFound(location=nonslashpath + qs)
    request.response.status = 404
    return dict(msg=request.exception)


dist_file_types = {
    'sdist': 'Source',
    'bdist_dumb': '"dumb" binary',
    'bdist_rpm': 'RPM',
    'bdist_wininst': 'MS Windows installer',
    'bdist_msi': 'MS Windows MSI installer',
    'bdist_egg': 'Python Egg',
    'bdist_dmg': 'OS X Disk Image',
    'bdist_wheel': 'Python Wheel'}


def sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0:
            return (num, x)
        num /= 1024.0
    return (num, 'TB')


def get_files_info(request, pv, show_toxresults=False):
    xom = request.registry['xom']
    files = []
    filedata = pv.get_links(rel='releasefile')
    if not filedata:
        log.warn(
            "project %r version %r has no files", pv.projectname, pv.version)
    for link in sorted(filedata, key=attrgetter('basename')):
        entry = xom.filestore.get_file_entry(link.entrypath)
        relurl = URL(request.path).relpath("/" + entry.relpath)
        if entry.eggfragment:
            relurl += "#egg=%s" % entry.eggfragment
        elif entry.md5:
            relurl += "#md5=%s" % entry.md5
        py_version, file_type = get_pyversion_filetype(entry.basename)
        if py_version == 'source':
            py_version = ''
        size = ''
        if entry.file_exists():
            size = "%.0f %s" % sizeof_fmt(entry.file_size())
        fileinfo = dict(
            title=link.basename,
            url=request.relative_url(relurl),
            basename=entry.basename,
            md5=entry.md5,
            dist_type=dist_file_types.get(file_type, ''),
            py_version=py_version,
            size=size)
        if show_toxresults:
            toxresults = get_toxresults_info(link)
            if toxresults:
                fileinfo['toxresults'] = toxresults
        files.append(fileinfo)
    return files


def _get_commands_info(commands):
    result = dict(
        failed=any(x["retcode"] != "0" for x in commands),
        commands=[])
    for command in commands:
        result["commands"].append(dict(
            failed=command["retcode"] != "0",
            command=" ".join(command["command"]),
            output=command["output"]))
    return result


def load_toxresult(link):
    data = link.entry.file_get_content().decode("utf-8")
    return json.loads(data)


def get_toxresults_info(link, newest=False):
    result = []
    seen = set()
    for reflink in reversed(link.pv.get_links(rel="toxresult", for_entrypath=link)):
        try:
            toxresult = load_toxresult(reflink)
            for envname in toxresult["testenvs"]:
                seen_key = (toxresult["host"], toxresult["platform"], envname)
                if seen_key in seen:
                    continue
                if newest:
                    seen.add(seen_key)
                env = toxresult["testenvs"][envname]
                info = dict(
                    basename=reflink.basename,
                    _key="-".join(seen_key),
                    host=toxresult["host"],
                    platform=toxresult["platform"],
                    envname=envname)
                info["setup"] = _get_commands_info(env.get("setup", []))
                try:
                    info["pyversion"] = env["python"]["version"].split(None, 1)[0]
                except KeyError:
                    pass
                info["test"] = _get_commands_info(env.get("test", []))
                info['failed'] = info["setup"]["failed"] or info["test"]["failed"]
                result.append(info)
        except Exception:
            log.exception("Couldn't parse test results %s." % reflink.basename)
    return result


def get_docs_info(request, stage, metadata):
    if stage.name == 'root/pypi':
        return
    name, ver = metadata["name"], metadata["version"]
    doc_path = get_unpack_path(stage, name, ver)
    if doc_path.exists():
        return dict(
            title="%s-%s" % (name, ver),
            url=request.route_url(
                "docviewroot", user=stage.user.name, index=stage.index,
                name=name, version=ver, relpath="index.html"))


@view_config(
    route_name='root',
    renderer='templates/root.pt')
def root(context, request):
    rawusers = sorted(
        (x.get() for x in context.model.get_userlist()),
        key=itemgetter('username'))
    users = []
    for user in rawusers:
        username = user['username']
        indexes = []
        for index in sorted(user.get('indexes', [])):
            indexes.append(dict(
                title="%s/%s" % (username, index),
                url=request.route_url(
                    "/{user}/{index}", user=username, index=index)))
        users.append(dict(
            title=username,
            indexes=indexes))
    return dict(users=users)


@view_config(
    route_name="/{user}/{index}", accept="text/html", request_method="GET",
    renderer="templates/index.pt")
def index_get(context, request):
    context = ContextWrapper(context)
    user, index = context.username, context.index
    stage = context.stage
    bases = []
    packages = []
    result = dict(
        title="%s index" % stage.name,
        simple_index_url=request.route_url(
            "/{user}/{index}/+simple/", user=user, index=index),
        bases=bases,
        packages=packages)
    if stage.name == "root/pypi":
        return result

    if hasattr(stage, "ixconfig"):
        for base in stage.ixconfig["bases"]:
            base_user, base_index = base.split('/')
            bases.append(dict(
                title=base,
                url=request.route_url(
                    "/{user}/{index}",
                    user=base_user, index=base_index),
                simple_url=request.route_url(
                    "/{user}/{index}/+simple/",
                    user=base_user, index=base_index)))

    for projectname in stage.getprojectnames_perstage():
        metadata = stage.get_metadata_latest_perstage(projectname)
        try:
            name, ver = metadata["name"], metadata["version"]
        except KeyError:
            log.error("metadata for project %r empty: %s, skipping",
                      projectname, metadata)
            continue
        show_toxresults = not (stage.user.name == 'root' and stage.index == 'pypi')
        pv = stage.get_project_version(name, ver)
        packages.append(dict(
            info=dict(
                title="%s-%s" % (name, ver),
                url=request.route_url(
                    "/{user}/{index}/{name}/{version}",
                    user=stage.user.name, index=stage.index,
                    name=name, version=ver)),
            make_toxresults_url=functools.partial(
                request.route_url, "toxresults",
                user=stage.user.name, index=stage.index,
                name=name, version=ver),
            files=get_files_info(request, pv, show_toxresults),
            docs=get_docs_info(request, stage, metadata)))

    return result


@view_config(
    route_name="/{user}/{index}/{name}",
    accept="text/html", request_method="GET",
    renderer="templates/project.pt")
def project_get(context, request):
    context = ContextWrapper(context)
    releases = context.stage.getreleaselinks(context.name)
    if not releases:
        raise HTTPNotFound("The project %s does not exist." % context.name)
    versions = []
    seen = set()
    for release in releases:
        user, index = release.relpath.split("/", 2)[:2]
        name, version = splitbasename(release)[:2]
        seen_key = (user, index, name, version)
        if seen_key in seen:
            continue
        versions.append(dict(
            index_title="%s/%s" % (user, index),
            index_url=request.route_url(
                "/{user}/{index}", user=user, index=index),
            title=version,
            url=request.route_url(
                "/{user}/{index}/{name}/{version}",
                user=user, index=index, name=name, version=version)))
        seen.add(seen_key)
    return dict(
        title="%s/: %s versions" % (context.stage.name, name),
        versions=versions)


@view_config(
    route_name="/{user}/{index}/{name}/{version}",
    accept="text/html", request_method="GET",
    renderer="templates/version.pt")
def version_get(context, request):
    context = ContextWrapper(context)
    user, index = context.username, context.index
    name, version = context.name, context.version
    stage, verdata = context.stage, context.verdata
    infos = []
    skipped_keys = frozenset(
        ("description", "home_page", "name", "summary", "version"))
    for key, value in sorted(verdata.items()):
        if key in skipped_keys or key.startswith('+'):
            continue
        if isinstance(value, list):
            if not len(value):
                continue
            value = html.ul([html.li(x) for x in value]).unicode()
        else:
            if not value:
                continue
            value = py.xml.escape(value)
        infos.append((py.xml.escape(key), value))
    show_toxresults = not (user == 'root' and index == 'pypi')
    pv = stage.get_project_version(name, version)
    files = get_files_info(request, pv, show_toxresults)
    return dict(
        title="%s/: %s-%s metadata and description" % (stage.name, name, version),
        content=get_description(stage, name, version),
        home_page=verdata.get("home_page"),
        summary=verdata.get("summary"),
        infos=infos,
        files=files,
        show_toxresults=show_toxresults,
        make_toxresults_url=functools.partial(
            request.route_url, "toxresults",
            user=context.username, index=context.index,
            name=context.name, version=context.version),
        make_toxresult_url=functools.partial(
            request.route_url, "toxresult",
            user=context.username, index=context.index,
            name=context.name, version=context.version),
        docs=get_docs_info(request, stage, verdata))


@view_config(
    route_name="toxresults",
    accept="text/html", request_method="GET",
    renderer="templates/toxresults.pt")
def toxresults(context, request):
    context = ContextWrapper(context)
    pv = context.project_version
    basename = request.matchdict['basename']
    toxresults = get_toxresults_info(
        pv.get_links(basename=basename)[0], newest=False)
    return dict(
        title="%s/: %s-%s toxresults" % (
            context.stage.name, context.name, context.version),
        toxresults=toxresults,
        make_toxresult_url=functools.partial(
            request.route_url, "toxresult",
            user=context.username, index=context.index,
            name=context.name, version=context.version, basename=basename))


@view_config(
    route_name="toxresult",
    accept="text/html", request_method="GET",
    renderer="templates/toxresult.pt")
def toxresult(context, request):
    context = ContextWrapper(context)
    pv = context.project_version
    basename = request.matchdict['basename']
    toxresult = request.matchdict['toxresult']
    toxresults = [
        x for x in get_toxresults_info(
            pv.get_links(basename=basename)[0], newest=False)
        if x['basename'] == toxresult]
    return dict(
        title="%s/: %s-%s toxresult %s" % (
            context.stage.name, context.name, context.version, toxresult),
        toxresults=toxresults)


def batch_list(num, current, left=3, right=3):
    result = []
    if not num:
        return result
    if current >= num:
        raise ValueError("Current position (%s) can't be greater than total (%s)." % (current, num))
    result.append(0)
    first = current - left
    if first < 1:
        first = 1
    if first > 1:
        result.append(None)
    last = current + right + 1
    if last >= num:
        last = num - 1
    result.extend(range(first, last))
    if last < (num - 1):
        result.append(None)
    if num > 1:
        result.append(num - 1)
    return result


class SearchView:
    def __init__(self, request):
        self.request = request
        self._metadata = {}
        self._stage = {}
        self._docs = {}

    @reify
    def params(self):
        params = dict(self.request.params)
        params['query'] = params.get('query', '')
        try:
            params['page'] = int(params.get('page'))
        except TypeError:
            params['page'] = 1
        return params

    @reify
    def search_result(self):
        if not self.params['query']:
            return None
        search_index = self.request.registry['search_index']
        return search_index.query_projects(
            self.params['query'], page=self.params['page'])

    @reify
    def batch_links(self):
        batch_links = []
        if not self.search_result or not self.search_result['items']:
            return
        result_info = self.search_result['info']
        batch = batch_list(result_info['pagecount'], result_info['pagenum'] - 1)
        for index, item in enumerate(batch):
            if item is None:
                batch_links.append(dict(
                    title='…'))
            elif item == (self.params['page'] - 1):
                current = index
                batch_links.append({
                    'title': item + 1,
                    'class': 'current'})
            else:
                new_params = dict(self.params)
                new_params['page'] = item + 1
                batch_links.append(dict(
                    title=item + 1,
                    url=self.request.route_url(
                        'search',
                        _query=new_params)))
        if current < (len(batch_links) - 1):
            next = dict(batch_links[current + 1])
            next['title'] = 'Next'
            next['class'] = 'next'
            batch_links.append(next)
        else:
            batch_links.append({'class': 'next'})
        if current > 0:
            prev = dict(batch_links[current - 1])
            prev['title'] = 'Prev'
            prev['class'] = 'prev'
            batch_links.insert(0, prev)
        else:
            batch_links.insert(0, {'class': 'prev'})
        return batch_links

    def get_stage(self, path):
        if path not in self._stage:
            xom = self.request.registry['xom']
            user, index, name = path[1:].split('/')
            stage = xom.model.getstage(user, index)
            self._stage['path'] = stage
        return self._stage['path']

    def get_metadata(self, stage, data):
        path = data['path']
        version = data.get('version')
        key = (path, version)
        if key not in self._metadata:
            name = data['name']
            metadata = {}
            if version and is_project_cached(stage, name):
                metadata = stage.get_project_versiondata(name, version)
                if metadata is None:
                    metadata = {}
            self._metadata[key] = metadata
        return self._metadata[key]

    def get_docs(self, stage, data):
        path = data['path']
        if path not in self._docs:
            self._docs[path] = Docs(stage, data['name'], data['doc_version'])
        return self._docs[path]

    def process_sub_hits(self, stage, sub_hits, data):
        search_index = self.request.registry['search_index']
        result = []
        for sub_hit in sub_hits:
            sub_data = sub_hit['data']
            text_type = sub_data['type']
            metadata = self.get_metadata(stage, data)
            title = text_type.title()
            highlight = None
            if text_type == 'project':
                continue
            elif text_type in ('title', 'page'):
                docs = self.get_docs(stage, data)
                entry = docs[sub_data['text_path']]
                text = entry['text']
                highlight = search_index.highlight(text, sub_hit.get('words'))
                title = sub_data.get('text_title', title)
                text_path = sub_data.get('text_path')
                if text_path:
                    sub_hit['url'] = self.request.route_url(
                        "docviewroot", user=data['user'], index=data['index'],
                        name=data['name'], version=data['doc_version'],
                        relpath="%s.html" % text_path)
            elif text_type in ('keywords', 'description', 'summary'):
                text = metadata.get(text_type)
                highlight = search_index.highlight(text, sub_hit.get('words'))
                if 'version' in data:
                    sub_hit['url'] = self.request.route_url(
                        "/{user}/{index}/{name}/{version}",
                        user=data['user'], index=data['index'],
                        name=data['name'], version=data['version'],
                        _anchor=text_type)
            else:
                log.error("Unknown type %s" % text_type)
                continue
            sub_hit['title'] = title
            sub_hit['highlight'] = highlight
            result.append(sub_hit)
        return result

    @reify
    def result(self):
        result = self.search_result
        if not result or not result['items']:
            return
        items = []
        for item in result['items']:
            data = item['data']
            stage = self.get_stage(data['path'])
            if stage is None:
                continue
            if 'version' in data:
                item['url'] = self.request.route_url(
                    "/{user}/{index}/{name}/{version}",
                    user=data['user'], index=data['index'],
                    name=data['name'], version=data['version'])
                item['title'] = "%s-%s" % (data['name'], data['version'])
            else:
                item['url'] = self.request.route_url(
                    "/{user}/{index}/{name}",
                    user=data['user'], index=data['index'], name=data['name'])
                item['title'] = data['name']
            item['sub_hits'] = self.process_sub_hits(
                stage, item['sub_hits'], data)
            more_results = result['info']['collapsed_counts'][data['path']]
            if more_results:
                new_params = dict(self.params)
                new_params['query'] = "%s path:%s" % (self.params['query'], data['path'])
                item['more_url'] = self.request.route_url(
                    'search',
                    _query=new_params)
                item['more_count'] = more_results
            items.append(item)
        if not items:
            return
        result['items'] = items
        return result

    @view_config(
        route_name='search',
        renderer='templates/search.pt')
    def __call__(self):
        return dict(
            query=self.params['query'],
            page=self.params['page'],
            batch_links=self.batch_links,
            result=self.result)

    @view_config(
        route_name='search_help',
        renderer='templates/search_help.pt')
    def search_help(self):
        return dict()
