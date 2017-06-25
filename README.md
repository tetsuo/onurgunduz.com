# blog

A simple blog on top of [pv](https://github.com/tetsuo/pv) and Google App Engine.

[See it in action here](http://www.onurgunduz.com).

# Features

* Markdown support.
* Serves html, json and xml as well.
* Pings Google Blog Search, Google PubSubHubbub Hub and FeedBurner.
* Generates sitemap.xml.

# Development

To run locally, you need to have [pip](http://www.pip-installer.org/en/latest/installing.html), [nodejs](https://nodejs.org/en/) and [Google App Engine SDK](https://developers.google.com/appengine/downloads) installed on your machine.

Install Python dependencies into `lib` folder:

```
pip install -r requirements.txt -t lib
```

Install node dependencies:

```
npm install
```

Compile Sass files and watch for changes:

```
npm run sass
```

Then type `dev_appserver.py .` to start the development server. Enjoy!

# Deploying

Use the [admin console](https://appengine.google.com) to create a project, then you can deploy the application with:

```
appcfg.py -A <your-project-id> --oauth2 update .
```

# License

<a href="https://creativecommons.org/licenses/by/3.0/">Creative Commons</a>
