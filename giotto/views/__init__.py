import os
import json
import mimeparse
import inspect

from jinja2 import Template, DebugUndefined, Environment, PackageLoader, FileSystemLoader
from jinja2.exceptions import TemplateNotFound

from giotto import get_config
from giotto.exceptions import NoViewMethod
from giotto.utils import Mock, htmlize, htmlize_list, pre_process_json, super_accept_to_mimetype, jsonify
from giotto.control import GiottoControl, Redirection

def renders(*mimetypes):
    def decorator(func):
        func.mimetypes = []
        for mimetype in mimetypes:
            func.mimetypes.append(mimetype)
        return func
    return decorator

class GiottoView(object):
    """
    Base class for all Giotto view objects. All Giotto Views must at least descend
    from this class, as ths class contains piping that the controller calls.
    """

    def __init__(self, persist=None, **kwargs):
        self.persist = persist
        self.render_map = {} # renderers by mimetype
        self.reject_map = {} # renderers by name (no corresponding mimetype)
        class_defined_renderers = [x for x in dir(self) if not x.startswith('__')]
        self._register_renderers(class_defined_renderers)

        for format, function in kwargs.items():
            ## key word arguments can be passed into the constructor to
            ## override render methods from within the manifest.
            ## set 'mimetypes' as if it were using the @renders decorator
            mime = super_accept_to_mimetype(format)
            setattr(function, 'mimetypes', [mime or format])
            setattr(self, format, function)

        # kwarg renderers kill any render methods that are defined by the class
        self._register_renderers(kwargs.keys())

    def _register_renderers(self, attrs):
        """
        Go through the passed in list of attributes and register those renderers
        in the render map.
        """
        for method in attrs:
            func = getattr(self, method)
            mimetypes = getattr(func, 'mimetypes', [])
            for mimetype in mimetypes:
                if not '/' in mimetype:
                    self.reject_map[mimetype] = func
                if mimetype not in self.render_map:
                    self.render_map[mimetype] = func
                else:
                    # about to redefine an already defined renderer.
                    # make sure this new render method is not on a base class.
                    base_classes = self.__class__.mro()[1:]
                    from_baseclass = any([x for x in base_classes if func.__name__ in dir(x)])
                    if not from_baseclass:
                        self.render_map[mimetype] = func


    def can_render(self, partial_mimetype):
        """
        Given a partial mimetype (such as 'json' or 'html'), return if the 
        view can render that type.
        """
        for mime in self.render_map.keys():
            if mime == '*/*':
                return True
            if partial_mimetype in mime:
                return True
        return False

    def render(self, result, mimetype, errors=None):
        """
        Render a model result into `mimetype` format.
        """
        available_mimetypes = [x for x in self.render_map.keys() if '/' in x]
        render_func = None

        if '/' not in mimetype:
            # naked superformat (does not correspond to a mimetype)
            render_func = self.reject_map.get(mimetype, None)
            if not render_func:
                raise NoViewMethod("Unknown Superformat: %s" % mimetype)

        if not render_func and available_mimetypes:
            target_mimetype = mimeparse.best_match(available_mimetypes, mimetype)
            render_func = self.render_map.get(target_mimetype, None)

        if not render_func:
            raise NoViewMethod("%s not supported for this program" % mimetype)

        principle_mimetype = render_func.mimetypes[0]

        if GiottoControl in render_func.__class__.mro():
            # redirection defined as view (not wrapped in lambda)
            return {'body': render_func, 'persist': render_func.persist}

        if callable(self.persist):
            # persist (cookie data) can be either an object, or a callable)
            persist = self.persist(result)
        else:
            persist = self.persist

        # render functins can take either one or two arguments, both are
        # supported by the API
        arg_names = inspect.getargspec(render_func).args
        num_args = len(set(arg_names) - set(['self', 'cls']))
        if num_args == 2:
            data = render_func(result, errors or Mock())
        else:
            # if the renderer only has one argument, don't pass in the 2nd arg.
            data = render_func(result)

        if GiottoControl in data.__class__.mro():
            # render function returned a control object
            return {'body': data, 'persist': persist}

        if not hasattr(data, 'items'):
            # view returned string
            data = {'body': data, 'mimetype': principle_mimetype}
        else:
            # result is a dict in for form {body: XX, mimetype: xx}
            if not 'mimetype' in data and target_mimetype == '*/*':
                data['mimetype'] = ''

            if not 'mimetype' in data:
                data['mimetype'] = target_mimetype

        data['persist'] = persist
        return data

class BasicView(GiottoView):
    """
    Basic viewer that contains generic functionality for showing any data.
    """
    @renders('application/json')
    def generic_json(self, result, errors):
        return {'body': jsonify(result), 'mimetype': 'application/json'}

    @renders('text/html')
    def generic_html(self, result, errors):
        """
        Try to display any object in sensible HTML.
        """
        h1 = htmlize(type(result))
        out = []
        result = pre_process_json(result)

        if not hasattr(result, 'items'):
            # result is a non-container
            header = "<tr><th>Value</th></tr>"
            if type(result) is list:
                result = htmlize_list(result)
            else:
                result = htmlize(result)
            out = ["<tr><td>" + result + "</td></tr>"]
        elif hasattr(result, 'lower'):
            out = ["<tr><td>" + result + "</td></tr>"]
        else:
            # object is a dict
            header = "<tr><th>Key</th><th>Value</th></tr>"
            for key, value in result.items():
                v = htmlize(value)
                row = "<tr><td>{0}</td><td>{1}</td></tr>".format(key, v)
                out.append(row)

        env = Environment(loader=PackageLoader('giotto'))
        template = env.get_template('generic.html')
        rendered = template.render({'header': h1, 'table_header': header, 'table_body': out})
        return {'body': rendered, 'mimetype': 'text/html'}

    @renders('text/plain', 'text/x-cmd', 'text/x-irc')
    def generic_text(self, result, errors):
        out = []
        kv_iterate = None
        single_iterate = []
        if hasattr(result, 'items'):
            #is a dict
            kv_iterate = result.items()
        elif hasattr(result, 'lower'):
            # is just a plain string
            return result
        elif not result:
            # is a Nonetype
            return ''
        elif hasattr(result, 'append'):
            # is a list
            single_iterate = result
        elif hasattr(result, 'todict'):
            # is a model object
            kv_iterate = result.todict().items()
        else:
            # generic object
            kv_iterate = result.__dict__.items()

        if kv_iterate:
            for key, value in kv_iterate:
                row = "{0} - {1}".format(key, value)
                out.append(row)
        else:
            for value in single_iterate:
                out.append(self.generic_text(value, None))

        return "\n".join(out)

def get_jinja_template(template_name):
    ppx = get_config('project_path')
    env = Environment(loader=FileSystemLoader(os.path.join(ppx, 'views'))) 
    return env.get_template(template_name)

def jinja_template(template_name, name='data', mimetype="text/html"):
    """
    Meta-renderer for rendering jinja templates
    """
    def jinja_renderer(result, errors):
        template = get_jinja_template(template_name)
        context = {name: result or Mock(), 'errors': errors, 'enumerate': enumerate}
        rendered = template.render(**context)
        return {'body': rendered, 'mimetype': mimetype}
    return jinja_renderer


def partial_jinja_template(template_name, name='data', mimetype="text/html"):
    """
    Partial render of jinja templates. This is useful if you want to re-render
    the template in the output middleware phase.
    These templates are rendered in a way that all undefined variables will be 
    kept in the emplate intact.
    """
    def partial_jinja_renderer(result, errors):
        template = get_jinja_template(template_name)
        old = template.environment.undefined
        template.environment.undefined = DebugUndefined
        context = {name: result or Mock(), 'errors': errors}
        rendered = template.render(**context)
        template.environment.undefined = old
        return {'body': rendered, 'mimetype': mimetype}
    return partial_jinja_renderer


def lazy_jinja_template(template_name, name='data', mimetype='text/html'):
    """
    Jinja template renderer that does not render the template at all.
    Instead of returns the context and template object blended together.
    Make sure to add ``giotto.middleware.RenderLazytemplate`` to the output
    middleware stread of any program that uses this renderer.
    """
    def lazy_jinja_renderer(result, errors):
        template = get_jinja_template(template_name)
        context = {name: result or Mock(), 'errors': errors}
        data = ('jinja2', template, context)
        return {'body': data, 'mimetype': mimetype}
    return lazy_jinja_renderer


class ImageViewer(GiottoView):
    """
    For viewing images. The 'result' must be a file object that contains image
    data (doesn't matter the format).
    """

    @renders('text/plain')
    def plaintext(self, result):
        """
        Converts the image object into an ascii representation. Code taken from
        http://a-eter.blogspot.com/2010/04/image-to-ascii-art-in-python.html
        """
        from PIL import Image

        ascii_chars = ['#', 'A', '@', '%', 'S', '+', '<', '*', ':', ',', '.']

        def image_to_ascii(image):
            image_as_ascii = []
            all_pixels = list(image.getdata())
            for pixel_value in all_pixels:
                index = pixel_value / 25 # 0 - 10
                image_as_ascii.append(ascii_chars[index])
            return image_as_ascii   

        img = Image.open(result)
        width, heigth = img.size
        new_width = 80 
        new_heigth = int((heigth * new_width) / width)
        new_image = img.resize((new_width, new_heigth))
        new_image = new_image.convert("L") # convert to grayscale

        # now that we have a grayscale image with some fixed width we have to convert every pixel
        # to the appropriate ascii character from "ascii_chars"
        img_as_ascii = image_to_ascii(new_image)
        img_as_ascii = ''.join(ch for ch in img_as_ascii)
        out = []
        for c in range(0, len(img_as_ascii), new_width):
            out.append(img_as_ascii[c:c+new_width])

        return "\n".join(out)

    def image(self, result):
        return result

    def image_jpeg(self, result):
        return self.image(result)

    def text_cmd(self, result):
        return result.read()

    def text_html(self, result):
        return """<!DOCTYPE html>
        <html>
            <body>
                <img src="/multiply?x=4&y=7">
            </body>
        </html>"""

class URLFollower(BasicView):
    """
    For visualizing programs that return a url
    """
    @renders("text/html")
    def text_html(self, data):
        return Redirection(data)

    def cmd(self, data):
        # execute browser and give it the url
        return ""

class ForceJSONView(GiottoView):
    """
    All objects going through this View will be displayed as JSON no matter what.
    """
    @renders("*/*")
    def renderer(self, data, errors):
        return jsonify(data)

class ForceTextView(GiottoView):
    @renders("*/*")
    def renderer(self, data, errors):
        return self.generic_text(data)