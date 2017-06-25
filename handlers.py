import pv
import utils
import models
import uuid
import functools
import logging
import email.utils
import datetime
import time
from webob import exc
from google.appengine.api import users, memcache
from google.appengine.ext import db, deferred, blobstore
from google.appengine.api.labs import taskqueue
from google.appengine.ext.webapp import blobstore_handlers


def admin(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        user = users.get_current_user()
        if not user:
            if self.request.method == "GET":
                self.redirect(users.create_login_url(self.request.uri))
                return
            raise exc.HTTPError
        elif not users.is_current_user_admin():
            raise exc.HTTPForbidden
        else:
            return method(self, *args, **kwargs)
    return wrapper


class BaseRequestHandler(pv.web.RequestHandler):
    @property
    def current_user(self):
        self._current_user = self.get_current_user()
        return self._current_user

    def get_current_user(self):
        user = users.get_current_user()
        if user:
            user.admin = users.is_current_user_admin()
        return user

    def render(self, template_name, **kwargs):
        format = self.get_argument("format", None)
        if "entries" in kwargs and isinstance(kwargs["entries"], list):
            kwargs["entries"] = list(kwargs["entries"])
        if kwargs.get("entries") and format == "atom":
            self.set_header("Content-Type", "application/atom+xml")
            template_name = "atom.xml"
        if "entries" in kwargs and format == "json":
            json_entries = [{
                "title": entry.title,
                "body": entry.body_html,
                "published": entry.published.isoformat(),
                "updated": entry.updated.isoformat(),
                "tags": entry.tags,
                "link": "http://" + self.request.host + "/blog/" + entry.key().name(),
            } for entry in kwargs["entries"]]
            self.set_header("Content-Type", "text/javascript")
            self.write({"entries": json_entries})
            return

        return pv.web.RequestHandler.render(self, template_name, **kwargs)


class BlogMainPageHandler(BaseRequestHandler):
    @pv.web.removeslash
    def get(self, page=1):
        try:
            entries, more = models.Entry.get_by_page(int(page), cached=True)
        except ValueError:
            raise exc.HTTPNotFound
        except models.PageNotFound:
            logging.warning('Page not found (%s).' % str(page))
            raise exc.HTTPNotFound
        self.render('entries.html', entries=entries,
                    more=more, page=page, show_comments=False)


class TagPageHandler(BaseRequestHandler):
    def get(self, tag=None):
        try:
            entries = models.Entry.get_tagged_entries(tag=tag)
        except models.Error:
            raise exc.HTTPNotFound
        if not entries:
            raise exc.HTTPNotFound
        self.render('tag.html', entries=entries, _tag=tag)


class EntryPageHandler(BaseRequestHandler):
    @pv.web.removeslash
    def get(self, key=None):
        try:
            entry = models.Entry.get_by_key_name(key, cached=True)
        except db.BadValueError:
            raise exc.HTTPNotFound
        if not entry:
            raise exc.HTTPNotFound
        self.render('entry.html',
                    entries=[entry], show_comments=True)


class MediaHandler(BaseRequestHandler):
    @admin
    def get(self):
        upload = self.request.get('upload', None)
        if upload:
            self.render('upload.html',
                        form_url=blobstore.create_upload_url('/media/upload?_xsrf='+self.xsrf_token))
            return
        _limit = 30
        def get_query(keys_only=False, cursor=None):
            query = db.Query(models.FileInfo, keys_only=keys_only).order('-timestamp')
            if cursor is not None:
                query.with_cursor(cursor)
            return query
        cursor = self.get_argument('cursor', None)
        try:
            query = get_query(cursor=cursor)
            entities = query.fetch(_limit)
        except db.BadValueError:
            entities = []
        if len(entities) == _limit:
            cursor = query.cursor()
        else:
            cursor = None
        self.render('media.html',
                    cursor=cursor,
                    files=entities)


class MediaUploadHandler(BaseRequestHandler):
    @admin
    def post(self):
        blob_info = blobstore.parse_blob_info(self.request.params['file'])
        file_info = models.FileInfo(blob=blob_info.key(),
                                    filename=blob_info.filename,
                                    size=str(blob_info.size),
                                    content_type=blob_info.content_type)
        db.put(file_info)
        self.redirect('/media')


class MediaDownloadHandler(pv.web.RequestHandler,
                           blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, id=None):
        file_info = models.FileInfo.get_by_id(int(id))
        if not file_info or not file_info.blob:
            raise exc.HTTPNotFound

        if file_info.content_type.split('/')[0] == 'application':
            content_disposition = 'attachment; filename="%s"' % str(file_info.filename)
            self.set_header('Content-Disposition', content_disposition)

        self.set_header("Cache-Control", "public")
        ims_value = self.request.headers.get("If-Modified-Since")
        if ims_value is not None:
            date_tuple = email.utils.parsedate(ims_value)
            if_since = datetime.datetime.fromtimestamp(time.mktime(date_tuple))
            if if_since.date() >= file_info.modified.date():
                self.response.status_int = 304
                return
        self.set_header("Last-Modified", file_info.modified)
        try:
            self.send_blob(file_info.blob)
        except AttributeError:
            # @todo: BlobStore webapp'deki response class'indan clean methodunu cagiriyor
            pass


class MediaDeleteHandler(BaseRequestHandler):
    @admin
    def get(self):
        id = self.get_argument('id', None)
        try:
            file_info = models.FileInfo.get_by_id(int(id))
        except (db.BadValueError, ValueError):
            raise exc.HTTPNotFound
        if not file_info:
            raise exc.HTTPNotFound
        file_info.blob.delete()
        db.delete(file_info)
        self.redirect('/media')


class NewEntryHandler(BaseRequestHandler):
    @admin
    def get(self, key=None):
        entry = None
        tags = None
        if key:
            try:
                entry = db.get(db.Key.from_path('Entry', key))
            except db.BadValueError:
                raise exc.HTTPNotFound
            if entry:
                tags = ", ".join(entry.tags)
            else:
                raise exc.HTTPNotFound
        self.render('new.html', entry=entry, tags=tags,
                    key_name=key)

    @admin
    def post(self, key=None):
        title, body, tags = (self.get_argument(v, u"").strip()
                             for v in ('title', 'body', 'tags'))
        if title and body:
            if key:
                try:
                    entry = db.get(db.Key.from_path('Entry', key))
                except db.BadKeyError:
                    raise exc.HTTPNotFound
                except db.BadValueError:
                    raise exc.HTTPUnprocessableEntity
                entry.title = title
                entry.body = body
            else:
                slug = utils.slughifi(title)
                try:
                    if db.GqlQuery('SELECT __key__ WHERE __key__ = :1',
                                   db.Key.from_path('Entry', slug)).fetch(1):
                        slug += "-" + uuid.uuid4().hex[:4]
                except db.BadValueError:
                    raise exc.HTTPUnprocessableEntity
                entry = models.Entry(key_name=slug,
                                     title=title,
                                     body=body)
            tags = [utils.slughifi(tag) for tag in tags.split(",")]
            tags = set([tag for tag in tags if tag])
            entry.tags = [db.Category(tag) for tag in tags]
            entry.put()
            if entry.is_saved():
                if not key and not self.application.settings['debug']:
                    try:
                        deferred.defer(utils.ping, self.request.host,
                                      self.application.settings['title'],
                                      _name='ping-%s' % entry.key().name())
                    except taskqueue.TaskAlreadyExistsError:
                        logging.warning('ping-%s task already exists.' % entry.key().name())
                    except taskqueue.TombstonedTaskError:
                        logging.warning('ping-%s is tombstoned.' % entry.key().name())
                return self.redirect(entry.url())
        self.render('new.html',
                    entry=utils._O(dict(title=title, body=body)),
                    tags=tags,
                    key_name=key)


class DeleteEntryHandler(BaseRequestHandler):
    @admin
    def get(self, key=None):
        try:
            entry = db.get(db.Key.from_path('Entry', key))
            if not entry:
                raise exc.HTTPNotFound
        except db.BadValueError:
            raise exc.HTTPUnprocessableEntity
        if entry:
            entry.delete()
        self.redirect('/')


class OpenSearchHandler(BaseRequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/xml")
        self.render("opensearch.xml")


class SitemapHandler(BaseRequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/xml")
        key = 'sitemap.xml'
        sitemap = memcache.get(key)
        if not sitemap:
            sitemap = '<?xml version="1.0" encoding="UTF-8"?> \
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            urls = utils.generate_sitemap(host=self.request.host)
            for url in urls:
                sitemap += url
            sitemap += '</urlset>'
            memcache.set(key, sitemap)
        self.write(sitemap)


class LoginHandler(BaseRequestHandler):
    def get(self):
        self.redirect(users.create_login_url('/'))


class LogoutHandler(BaseRequestHandler):
    def get(self):
        self.redirect(users.create_logout_url('/'))
