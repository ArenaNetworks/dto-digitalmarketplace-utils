import json
import hashlib
import requests
from flask import current_app
from flask.json import JSONEncoder
from flask import request

from .exceptions import ReactRenderingError, RenderServerError
from dmutils.csrf import get_csrf_token

from six import python_2_unicode_compatible


@python_2_unicode_compatible
class RenderedComponent(object):
    def __init__(self, markup, props, slug=None, files=None):
        self.markup = markup
        self.props = props
        self.slug = slug
        self.files = files or {}

    def __str__(self):
        return self.markup

    def get_bundle(self):
        bundle_url = current_app.config.get('REACT_BUNDLE_URL', '/')
        return bundle_url + self.files.get(self.slug)

    def get_vendor_bundle(self):
        bundle_url = current_app.config.get('REACT_BUNDLE_URL', '/')
        return bundle_url + self.files.get('vendor', 'vendor.js')

    def get_file(self, key=''):
        # If bundle doesn't contain requested file, don't return half a url.
        if key not in self.files:
            return None

        bundle_url = current_app.config.get('REACT_BUNDLE_URL', '/')
        return bundle_url + self.files.get(key)

    def get_slug(self):
        return self.slug

    def get_props(self):
        return self.props

    def render(self):
        return str(self.markup)


class RenderServer(object):
    @property
    def url(self):
        return current_app.config.get('REACT_RENDER_URL', '')

    def render(self, path, props=None, to_static_markup=False, request_headers=None):
        url = self.url

        if props is None:
            props = {}

        if 'form_options' not in props:
            props['form_options'] = {}

        props['form_options']['csrf_token'] = get_csrf_token()

        # Add default options.
        opts = props.get('options', {})
        opts.update({
            'serverRender': True,
            'apiUrl': current_app.config.get('SERVER_NAME', None)
        })

        # Pass current route path for React router to use
        props.update({
            '_serverContext': {
                'location': request.path
            },
            'options': opts
        })

        serialized_props = json.dumps(dict(props), cls=JSONEncoder, sort_keys=True)

        if not current_app.config.get('REACT_RENDER', ''):
            return RenderedComponent('', serialized_props)

        options = {
            'path': path,
            'serializedProps': serialized_props,
            'toStaticMarkup': to_static_markup
        }
        serialized_options = json.dumps(options, sort_keys=True)
        options_hash = hashlib.sha1(serialized_options.encode('utf-8')).hexdigest()

        all_request_headers = {'content-type': 'application/json'}

        # Add additional requests headers if the requet_headers dictionary is specified
        if request_headers is not None:
            all_request_headers.update(request_headers)

        try:
            res = requests.post(
                url,
                data=serialized_options,
                headers=all_request_headers,
                params={'hash': options_hash}
            )
        except requests.exceptions.ConnectionError:
            raise RenderServerError('Could not connect to render server at {}'.format(url))

        if res.status_code != 200:
            raise RenderServerError(
                'Unexpected response from render server at {} - {}: {}'.format(url, res.status_code, res.text)
            )

        obj = res.json()

        markup = obj.get('markup', None)
        err = obj.get('error', None)
        slug = obj.get('slug', 'main')
        files = obj.get('files', dict())

        if err:
            if 'message' in err and 'stack' in err:
                raise ReactRenderingError(
                    'Message: {}\n\nStack trace: {}'.format(err['message'], err['stack'])
                )
            raise ReactRenderingError(err)

        if markup is None:
            raise ReactRenderingError('Render server failed to return markup. Returned: {}'.format(obj))

        return RenderedComponent(markup, serialized_props, slug, files)


render_server = RenderServer()
