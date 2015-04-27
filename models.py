import utils
import urllib
import markdown2, BeautifulSoup
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.ext.blobstore import blobstore

DATASTORE_FETCH_LIMIT = 900

class Error(Exception):
    """"""

class PageNotFound(Error):
    """"""


class BaseModel(db.Model):
    @classmethod
    def flush(cls, num_fetch=499):
        """Deletes all records of this kind."""
        keys = []
        while True:
            entities = cls.all(keys_only=True).fetch(num_fetch)
            if not entities:
                break
            else:
                keys.extend(entities)
                db.delete(entities)
        return keys

    def after_put(self):
        raise NotImplementedError
    
    def before_put(self):
        raise NotImplementedError

    def put(self, **kwargs):
        try:
            self.before_put()
        except NotImplementedError:
            pass
        super(BaseModel, self).put(**kwargs)
        try:
            self.after_put()
        except NotImplementedError:
            pass
        
    def delete(self, **kwargs):
        super(BaseModel, self).delete(**kwargs)
        try:
            self.after_put()
        except NotImplementedError:
            pass
        
    @classmethod
    def get_by_key_name(cls, key_names, cached=False, parent=None, **kwargs):
        if isinstance(key_names, list) or not cached:
            # @todo: Multi gets are not cached.
            result = super(BaseModel, cls).get_by_key_name(key_names=key_names,
                                                           parent=parent, **kwargs)
        else:
            cache_key = '/'.join([cls.kind().lower(), key_names])
            result = memcache.get(cache_key)
            if not result:
                result = super(BaseModel, cls).get_by_key_name(key_names=key_names,
                                                               parent=parent, **kwargs)
                if result:
                    memcache.set(cache_key, utils.pb_serialize(result))
            else:
                result = utils.pb_deserialize(result)
        return result
    
    @classmethod
    def _get_by_page(cls, page=1, limit=10):
        if not cls.properties().has_key('published'):
            raise Error, '_get_by_page method needs a \'published\' property.'
        if not isinstance(cls.properties()['published'], db.DateTimeProperty):
            raise Error, '\'published\' property must be a DateTimeProperty instance.'
        
        def get_query(keys_only=False, cursor=None):
            query = db.Query(cls, keys_only=keys_only).order('-published')
            if cursor is not None:
                query.with_cursor(cursor)
            return query
        
        if page <= 1:
            q = get_query()
        else:
            cursor = Cursor.get_by_key_name('_'.join([cls.kind().lower(), str(page)]))
            if not cursor:
                n = (int(page)-1)*limit
                q = get_query(keys_only=True)
                if n <= DATASTORE_FETCH_LIMIT:
                    _to_fetch = n
                    _remaining = 0
                else:
                    _to_fetch = DATASTORE_FETCH_LIMIT
                    _remaining = n - DATASTORE_FETCH_LIMIT
                e = q.fetch(_to_fetch)
                entities_len = len(e)
                while _remaining > 0:
                    if _remaining <= DATASTORE_FETCH_LIMIT:
                        cursor = q.cursor()
                        q = get_query(keys_only=True, cursor=cursor)
                        e = q.fetch(_remaining)
                        _remaining = 0
                        entities_len += len(e)
                    else:
                        cursor = q.cursor()
                        q = get_query(keys_only=True, cursor=cursor)
                        _remaining = _remaining - DATASTORE_FETCH_LIMIT
                        e = q.fetch(DATASTORE_FETCH_LIMIT)
                        entities_len += len(e)
                if entities_len == n:
                    cursor = Cursor(key_name='_'.join([cls.kind().lower(), str(page)]),
                                    value=q.cursor())
                    cursor.put()
                else:
                    raise PageNotFound
            q = get_query(cursor=cursor.value)
        more = False
        entities = q.fetch(limit)
        if entities:
            if len(entities) == limit:
                q = get_query(cursor=q.cursor(), keys_only=True)
                e = q.fetch(1)
                if e:
                    more = True
                else:
                    more= False    
        return entities, more

    @classmethod
    def get_by_page(cls, page=1, cached=False):
        if not cached:
            return cls._get_by_page(page=page)
        else:
            key = '/'.join(['pg', cls.kind().lower(), str(page)])
            data = memcache.get(key)
            if data:
                return utils.pb_deserialize(data['entities']), data['more']
            entities, more = cls._get_by_page(page=page)
            memcache.set(key, dict(entities=utils.pb_serialize(entities),
                                   more=more))
            return entities, more
            

class Cursor(BaseModel):
    value = db.TextProperty(required=True)


class Entry(BaseModel):
    title = db.StringProperty(required=True)
    body = db.TextProperty(required=True)
    body_html = db.TextProperty()
    tags = db.ListProperty(db.Category)
    published = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    
    def url(self, query_args={}, absolute=False, path_prefix="/blog/"):
        url = path_prefix + self.key().name()
        if absolute:
            url = "http://" + self.request.host + url
        if query_args:
            url += "?" + urllib.urlencode(query_args)
        return url
    
    def before_put(self):
        self.body_html = markdown2.markdown(self.body, safe_mode='escape')
    
    def after_put(self):
        keys = ['entry/%s' % self.key().name(), 'sitemap.xml']
        cursor_keys = Cursor.flush()
        # @todo: Flushes all cursors omitting kind and filters.
        keys.extend(['pg/entry/1'])
        keys.extend([('pg/entry/%s' % key.name().split('_')[1])
                               for key in cursor_keys])
        memcache.delete_multi(keys)

    def parse_thumbnails(self):
        soup = BeautifulSoup.BeautifulSoup(self.body,
            parseOnlyThese=BeautifulSoup.SoupStrainer("img"))
        imgs = soup.findAll("img")
        thumbnails = []
        for img in imgs:
            if "nomediarss" in img.get("class", "").split():
                continue
            thumbnails.append({
                "url": img["src"],
                "title": img.get("title", img.get("alt", "")),
                "width": img.get("width", ""),
                "height": img.get("height", ""),
            })
        return thumbnails

    @classmethod
    def get_tagged_entries(cls, tag=None, keys_only=False, limit=100):
        # @todo: Fetches are limited to 100 entries.
        if not tag.strip():
            raise Error, 'tag is missing.'
        return db.Query(Entry, keys_only=keys_only).filter("tags =",
                                        tag).order("-published").fetch(limit)


class FileInfo(db.Model):
    blob = blobstore.BlobReferenceProperty(required=True)
    filename = db.StringProperty(indexed=False)
    size = db.StringProperty(indexed=False)
    content_type = db.StringProperty(indexed=False)
    timestamp = db.DateTimeProperty(auto_now_add=True)
    modified = db.DateTimeProperty(auto_now=True)


def dummy_entries(limit=10):
    entities = []
    for k in range(limit):
        e = Entry(title='Dummy Title %s' % k,
                  body='Body %s' % k,
                  key_name='dummy-%s' % str(k))
        entities.append(e)
    return db.put(entities)
