from __future__ import absolute_import

import os
import jinja2
import rollbar
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

import flask_featureflags
from . import config, logging, force_https, request_id, formats, filters, rollbar_agent
from flask import Markup, redirect, request, session, current_app, abort
from flask_script import Manager, Server
from flask_login import current_user
from werkzeug.contrib.fixers import ProxyFix

from .asset_fingerprint import AssetFingerprinter
from .user import User, user_logging_string

from dmutils import terms_of_use
from dmutils.forms import is_csrf_token_valid

from .csrf import check_valid_csrf


def init_app(
        application,
        config_object,
        bootstrap=None,
        data_api_client=None,
        db=None,
        login_manager=None,
        search_api_client=None,
        cache=None,
):

    application.config.from_object(config_object)
    if hasattr(config_object, 'init_app'):
        config_object.init_app(application)

    # all belong to dmutils
    config.init_app(application)
    logging.init_app(application)
    ProxyFix(application)
    request_id.init_app(application)
    force_https.init_app(application)
    rollbar_agent.init_app(application)

    flask_featureflags.FeatureFlag(application)

    if bootstrap:
        bootstrap.init_app(application)
    if data_api_client:
        data_api_client.init_app(application)
    if db:
        db.init_app(application)
    if login_manager:
        login_manager.init_app(application)
    if search_api_client:
        search_api_client.init_app(application)
    if cache:
        cache_type = application.config.get('DM_CACHE_TYPE', 'prod')
        if cache_type == 'dev':
            # This is "not really thread safe" - a.k.a not thread safe
            # Only for dev mode
            cache_config = {'CACHE_TYPE': 'simple'}
        else:
            # NICETODO: the memecached backend is supposed to be a drop-in replacement
            tmp_dir = os.environ.get('TMPDIR', '/tmp')
            cache_dir = os.path.join(tmp_dir, 'dm-cache')
            cache_config = {'CACHE_TYPE': 'filesystem', 'CACHE_DIR': cache_dir}
        cache.config = cache_config
        cache.init_app(application, config=cache_config)

    @application.before_request
    def set_scheme():
        request.environ['wsgi.url_scheme'] = application.config['DM_HTTP_PROTO']

    @application.after_request
    def add_header(response):
        if not response.headers.get('X-Frame-Options'):
            response.headers['X-Frame-Options'] = 'DENY'
        return response


def init_frontend_app(application, data_api_client, login_manager, template_dirs=['app/templates']):
    application.jinja_loader = jinja2.FileSystemLoader(template_dirs)

    def request_log_handler(response):
        params = {
            'method': request.method,
            'url': request.url,
            'status': response.status_code,
            'user': user_logging_string(current_user),
        }
        application.logger.info('{method} {url} {status} {user}', extra=params)
    application.extensions['request_log_handler'] = request_log_handler

    terms_of_use.init_app(application)

    @login_manager.user_loader
    def load_user(user_id):
        return User.load_user(data_api_client, user_id)

    @application.before_request
    def check_csrf_token():
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            old_csrf_valid = is_csrf_token_valid()
            new_csrf_valid = check_valid_csrf()

            if not (old_csrf_valid or new_csrf_valid):
                current_app.logger.info(
                    u'csrf.invalid_token: Aborting request, user_id: {user_id}',
                    extra={'user_id': session.get('user_id', '<unknown')})
                rollbar.report_message('csrf.invalid_token: Aborting request check_csrf_token()', 'error', request)
                abort(400, 'Invalid CSRF token. Please try again.')

    @application.before_request
    def refresh_session():
        session.permanent = True
        session.modified = True

    @application.before_request
    def remove_trailing_slash():
        if request.path != application.config['URL_PREFIX'] + '/' and request.path.endswith('/'):
            if request.query_string:
                return redirect(
                    '{}?{}'.format(
                        request.path[:-1],
                        request.query_string.decode('utf-8')
                    ),
                    code=301
                )
            else:
                return redirect(request.path[:-1], code=301)

    @application.after_request
    def add_cache_control(response):
        if request.method != 'GET' or response.status_code in (301, 302):
            return response

        vary = response.headers.get('Vary', None)
        if vary:
            response.headers['Vary'] = vary + ', Cookie'
        else:
            response.headers['Vary'] = 'Cookie'

        if current_user.is_authenticated:
            response.cache_control.private = True
        if response.cache_control.max_age is None:
            response.cache_control.max_age = application.config['DM_DEFAULT_CACHE_MAX_AGE']

        return response

    @application.context_processor
    def inject_global_template_variables():
        template_data = {
            'pluralize': pluralize,
            'header_class': 'with-proposition',
            'asset_path': application.config['ASSET_PATH'] + '/',
            'asset_fingerprinter': AssetFingerprinter(asset_root=application.config['ASSET_PATH'] + '/')
        }
        return template_data

    @application.template_filter('markdown')
    def markdown_filter_flask(data):
        return Markup(filters.markdown_filter(data))
    application.add_template_filter(filters.format_links)
    application.add_template_filter(filters.smartjoin)
    application.add_template_filter(quote)

    date_formatter = formats.DateFormatter(application.config['DM_TIMEZONE'])
    application.add_template_filter(date_formatter.timeformat)
    application.add_template_filter(date_formatter.shortdateformat)
    application.add_template_filter(date_formatter.dateformat)
    application.add_template_filter(date_formatter.datetimeformat)


def pluralize(count, singular, plural):
    return singular if count == 1 else plural


def get_extra_files(paths):
    for path in paths:
        for dirname, dirs, files in os.walk(path):
            for filename in files:
                filename = os.path.join(dirname, filename)
                if os.path.isfile(filename):
                    yield filename


def init_manager(application, port, extra_directories=()):

    manager = Manager(application)

    extra_files = list(get_extra_files(extra_directories))

    application.logger.info("Watching {} extra files".format(len(extra_files)))

    manager.add_command(
        "runserver",
        Server(port=port, extra_files=extra_files)
    )

    @manager.command
    def runprodserver():
        from waitress import serve
        serve(application, port=port)

    @manager.command
    def list_routes():
        """List URLs of all application routes."""
        for rule in sorted(manager.app.url_map.iter_rules(), key=lambda r: r.rule):
            print("{:10} {}".format(", ".join(rule.methods - set(['OPTIONS', 'HEAD'])), rule.rule))

    return manager
