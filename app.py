import pv
import os

settings = {
    "title": "@xxy998",
    "description": "updates & geschriften",
    "author": "@xxy998",
    "static_path": os.path.join(os.path.dirname(__file__), "public"),
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    "cookie_secret": "secret",
    "xsrf_cookies": True,
    "debug": os.environ["SERVER_SOFTWARE"].startswith("Dev"),
}

url_mappings = [
    ("/blog/?", "handlers.BlogMainPageHandler"),
    ("/blog/{page:[0-9]+}/?", "handlers.BlogMainPageHandler"),
    ("/blog/{key:[a-z-0-9-]+}/?", "handlers.EntryPageHandler"),
    ("/tag/{tag:[a-z-0-9-]+}/?", "handlers.TagPageHandler"),
    ("/edit/{key:[a-z-0-9-]+}/?", "handlers.NewEntryHandler"),
    ("/delete/{key:[a-z-0-9-]+}/?", "handlers.DeleteEntryHandler"),
    ("/new/?", "handlers.NewEntryHandler"),
    ("/media/?", "handlers.MediaHandler"),
    ("/media/upload/?", "handlers.MediaUploadHandler"),
    ("/media/delete/?", "handlers.MediaDeleteHandler"),
    ("/file/{id:[0-9]+}/?", "handlers.MediaDownloadHandler"),
    ("/login/?", "handlers.LoginHandler"),
    ("/logout/?", "handlers.LogoutHandler"),
    ("/opensearch.xml", "handlers.OpenSearchHandler"),
    ("/sitemap.xml", "handlers.SitemapHandler"),
    ("/feed/?", "pv.web.RedirectHandler", {"url": "/blog/?format=atom"}),
    ("/", "pv.web.RedirectHandler", {"url": "/blog"})
]

app = pv.WSGIApplication(url_mappings, **settings)
