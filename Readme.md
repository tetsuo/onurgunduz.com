# onurgunduz.com

my personal site.

This runs on [Google App Engine](https://appengine.google.com) and built on top of [pv](https://github.com/tetsuo/pv), a minimal wsgi framework.

[http://onurgunduz.com](http://www.onurgunduz.com)

# running

You will need [App Engine Python SDK](https://developers.google.com/appengine/downloads) and [pip](http://www.pip-installer.org/en/latest/installing.html) installed on your system.

To run locally, install dependencies into lib directory first:

```
pip install -r requirements.txt -t lib
```

Then type `dev_appserver.py .` to start a development server.

# deploy

Use the [admin console](https://appengine.google.com) to create a project, then you can deploy the application with:

```
appcfg.py -A <your-project-id> --oauth2 update .
```

# license

mit