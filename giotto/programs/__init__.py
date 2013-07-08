import inspect
import re
import os

from giotto.exceptions import ProgramNotFound, MockNotFound, ControlMiddlewareInterrupt, NoViewMethod
from giotto.utils import super_accept_to_mimetype
from giotto.control import GiottoControl
from giotto.views import GiottoView

class GiottoProgram(object):
    name = None
    description = None
    tests = []
    pre_input_middleware = ()
    input_middleware = ()
    controllers = ()
    cache = 0
    model = ()
    view = None
    output_middleware = ()

    valid_args = [
        'name', 'description', 'tests', 'pre_input_middleware', 'controllers',
        'input_middleware', 'cache', 'model', 'view', 'output_middleware'
    ]

    def __repr__(self):
        return "<GiottoProgram: %s>" % (self.name or self.model.__doc__)

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k not in self.valid_args:
                raise ValueError(
                    "Invalid GiottoProgram argument: %s, choices are %s" %
                    (k, ", ".join(self.valid_args))
                )
            else:
                setattr(self, k, v)

        if hasattr(self.view, 'mro') and GiottoView in self.view.mro():
            # instantiate all views that are defined as a class.
            self.view = self.view()

    def get_model_args_kwargs(self):
        """
        Inspect the model (or view in the case of no model) and return the args
        and kwargs. This functin is necessary because argspec returns in a silly format
        by default.
        """
        source = self.get_model()
        if not source:
            return [], {}

        argspec = inspect.getargspec(source)
        kwargs = dict(zip(*[reversed(l) for l in (argspec.args, argspec.defaults or [])]))
        args = [x for x in argspec.args if x not in kwargs.keys()]
        if args and args[0] == 'cls':
            args = args[1:]
        return args, kwargs

    def get_model(self):
        if len(self.model) == 0:
            return None
        return self.model[0]

    def has_mock_defined(self):
        return len(self.model) > 1

    def get_model_mock(self):
        if not self.model or not self.model[0]:
            # no mock needed
            return {}
        try:
            return self.model[1]
        except IndexError:
            raise MockNotFound("no mock for %s" % self.name)

    def execute_input_middleware_stream(self, request, controller):
        """
        Request comes from the controller. Returned is a request.
        controller arg is the name of the controller.
        """
        start_request = request
        # either 'http' or 'cmd' or 'irc'
        controller_name = "".join(controller.get_controller_name().split('-')[:1])
        middlewares = list(self.pre_input_middleware) + list(self.input_middleware)
        for m in middlewares:
            to_execute = getattr(m(controller), controller_name)
            if to_execute:
                result = to_execute(request)
                if GiottoControl in type(result).mro():
                    # a middleware class returned a control object (redirection, et al.)
                    # ignore all other middleware classes
                    return request, result
                request = result
        return start_request, request

    def execute_output_middleware_stream(self, request, response, controller):
        controller_name = "".join(controller.get_controller_name().split('-')[:1]) # 'http-get' -> 'http'
        for m in self.output_middleware:
            to_execute = getattr(m(controller), controller_name, None)
            if to_execute:
                response = to_execute(request, response)
        return response

    def execute_model(self, data):
        """
        Returns data from the model, if mock is defined, it returns that instead.
        """
        model = self.get_model()
        if model is None:
            return None
        return model(**data)

    def execute_view(self, data, mimetype, errors):
        if not self.view:
            return {'body': '', 'mimetype': ''}
        return self.view.render(data, mimetype, errors)

key_regex = re.compile(r'^\w*$')

class ProgramManifest(object):
    """
    Represents a node in a larger manifest tree. Manifests are like URLS for
    giotto applications. All keys must be strings, and all values must be
    either GiottoPrograms or another ProgramManifest instance.
    """
    
    def __repr__(self):
        return "<Manifest %s (%s nodes)>" % (self.backname, len(self.manifest))

    def __getitem__(self, key):
        return self.manifest[key]

    def __init__(self, manifest, backname='root'):
        self.backname = backname
        self.manifest = manifest
        # any sub manifests, convert to manifests objects
        for key, item in self.manifest.items():
            type_ = type(item)

            is_program = isinstance(item, GiottoProgram)
            is_manifest = type_ == ProgramManifest
            is_list = type_ == list
            is_str = type_ == str

            if not key_regex.match(key):
                raise ValueError("Invalid manifest key: %s" % key)

            if type_ is dict:
                self.manifest[key] = ProgramManifest(item, backname=key)
            elif not any([is_manifest, is_program, is_list, is_str]):
                msg = "Manifest value must be either: a program, a list of programs, or another manifest"
                raise TypeError(msg)

    def get_urls(self, controllers=None, prefix_path=''):
        """
        Return a list of all valid urls (minus args and kwargs, just the program paths)
        for this manifest. If a single program has two urls, both will be returned.
        """
        tag_match = lambda program: set(program.controllers) & set(controllers or [])
        urls = set()
        for key, value in self.manifest.items():

            path = "%s/%s" % (prefix_path, key)

            if path.endswith('/') and prefix_path:
                path = path[:-1]

            if hasattr(value, 'lower'):
                # is a string redirect
                urls.add(path)

            elif hasattr(value, 'append'):
                # is a list, only append this url is the list contains a
                # program that implements this controller.
                for program in value:
                    if tag_match(program):
                        urls.add(path)

            elif isinstance(value, ProgramManifest):
                # is manifest
                pp = '' if path == '/' else path # for 'stacked' root programs.
                new_urls = value.get_urls(controllers=controllers, prefix_path=pp)
                urls.update(new_urls)

            elif isinstance(value, GiottoProgram):
                if not value.controllers or not controllers:
                    # no controllers defined on program. Always add.
                    # or no tags defined for this get_urls call. Always add.
                    urls.add(path)
                elif tag_match(value):
                    urls.add(path)
                else:
                    continue

            else:
                raise Exception("Invalid Manifest (this should never happen)")

        return urls

    def _get_suggestions(self, filter_word=None):
        """
        This only gets caled internally from the get_suggestion method.
        """
        keys = self.manifest.keys()
        words = []
        for key in keys:            
            if isinstance(self.manifest[key], ProgramManifest):
                # if this key is another manifest, append a slash to the 
                # suggestion so the user knows theres more items under this key
                words.append(key + '/')
            else:
                words.append(key)

        if filter_word:
            words = [x for x in words if x.startswith(filter_word)]

        return words

    def get_suggestion(self, front_path):
        """
        Returns suggestions for a path. Used in tab completion from the command
        line.
        """
        if '/' in front_path:
            # transverse the manifest, return the new manifest, then
            # get those suggestions with the remaining word
            splitted = front_path.split('/')
            new_manifest = self.manifest
            pre_path = ''
            for item in splitted:
                try:
                    new_manifest = new_manifest[item]
                except KeyError:
                    partial_word = item
                    break
                else:
                    pre_path += item + '/'

            if isinstance(new_manifest, GiottoProgram):
                return []
            matches = new_manifest._get_suggestions(partial_word)
            return [pre_path + match for match in matches]
        else:
            return self._get_suggestions(front_path or None)

    def get_program(self, program_path):
        """
        Find the program within this manifest. If key is found, and it contains
        a list, iterate over the list and return the program that matches
        the controller tag. NOTICE: program_path must have a leading slash.
        """
        if not program_path or program_path[0] != '/':
            raise ValueError("program_path must be a full path with leading slash")

        items = program_path[1:].split('/')
        result = self
        for item in items:
            result = result[item]

        if hasattr(result, "lower"):
            # string redirect
            return self.get_program(result)

        if type(result) is ProgramManifest:
            return result.get_program('/')

        return result

    def parse_invocation(self, invocation, controller_tag):
        """
        Given an invocation string, determine which part is the path, the program,
        and the args.
        """
        if invocation.endswith('/'):
            invocation = invocation[:-1]
        if not invocation.startswith('/'):
            invocation = '/' + invocation
        if invocation == '':
            invocation = '/'
        
        all_programs = self.get_urls(controllers=[controller_tag])

        matching_path = None
        for program_path in sorted(all_programs):
            if invocation.startswith(program_path):
                matching_path = program_path

        if not matching_path:
            raise ProgramNotFound("Can't find %s" % invocation)

        program_name = matching_path.split('/')[-1]
        path = "/".join(matching_path.split('/')[:-1]) + '/'
        args_fragment = invocation[len(matching_path):]
        args = args_fragment.split("/")[1:] if '/' in args_fragment else []
        result = self.get_program(matching_path)

        if '.' in program_name:
            raise NotImplementedError("Superformat not done yet")

        ret = {
            'program': result,
            'program_name': program_name,
            'superformat': None,
            'args': args,
            'path': path,
            'invocation': invocation,
        }
        return ret