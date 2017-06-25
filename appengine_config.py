import os
import re
from google.appengine.ext import vendor

vendor.add('lib')

_DISALLOWED_PATHS = [r'/static.*']

def appstats_should_record(env):
    path_info = env.get('PATH_INFO', None)
    if not path_info:
        return
    for regex in _DISALLOWED_PATHS:
        if bool(re.match(regex, path_info)):
            return
    return True

def webapp_add_wsgi_middleware(app):
    if os.environ['SERVER_SOFTWARE'].startswith('Dev'):
        from google.appengine.ext.appstats import recording
        app = recording.appstats_wsgi_middleware(app)
        return app
    else:
        return app
