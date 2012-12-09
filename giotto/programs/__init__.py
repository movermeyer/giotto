import inspect
import re
import os

from giotto.exceptions import ProgramNotFound
from giotto.utils import super_accept_to_mimetype

class GiottoProgram(object):
    name = None
    input_middleware = ()
    controllers = ()
    cache = 0
    model = ()
    view = ()
    output_middleware = ()

    def __init__(self, **kwargs):
        self.__dict__ = kwargs

    def get_model_args_kwargs(self):
        """
        Inspect the model (or view in the case of no model) and return the args
        and kwargs. This functin is necessary because argspec returns in a silly format
        by default.
        """
        source = self.get_model()
        if not source:
            return [], {}

        if hasattr(source, 'render'):
            # if 'source' is a view object, try to get the render method,
            # otherwise, just use the __call__ method.
            source = source.render

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

    def get_model_mock(self):
        return self.model[1]

    def execute_input_middleware_stream(self, request, controller):
        """
        Request comes from the controller. Returned is a request.
        controller arg is the name of the controller.
        """
        for m in self.input_middleware:
            to_execute = getattr(m(), controller)
            if to_execute:
                request = to_execute(request)
        return request

    def execute_output_middleware_stream(self, request, response, controller):
        for m in self.output_middleware:
            to_execute = getattr(m(), controller, None)
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
        return self.view(data, errors).render(mimetype)

class ProgramManifest(object):
    """
    Represents a node in a larger manifest tree. Manifests are like URLS for
    giotto applications. All keys must be strings, and all values must be
    either GiottoPrograms or another ProgramManifest instance.
    """
    key_regex = r'^\w*$'

    def __init__(self, manifest):
        self.manifest = manifest
        # any sub manifests, convert to manifests objects
        for key, item in self.manifest.items():
            type_ = type(item)
            if type(key) == tuple:
                # if the key is a tuple with the controller tag attached.
                name_part_of_key = key[0]
            else:
                #if key is just the key (save as (key, '*'))
                name_part_of_key = key

            is_program = isinstance(item, GiottoProgram)
            is_manifest = type_ == ProgramManifest

            if not re.match(self.key_regex, name_part_of_key):
                raise ValueError("Invalid manifest key: %s" % key)

            if type_ is dict:
                self.manifest[key] = ProgramManifest(item)
            elif not is_manifest and not is_program:
                raise TypeError("Manifest value must be either a program or another manifest")

    def __repr__(self):
        return "<Manifest (%s nodes)>" % len(self.manifest)

    def __getitem__(self, key):
        return self.manifest[key]

    def get_program(self, program, controller_tag):
        for to_try in ((program, controller_tag), (program, '*'), program):
            try:
                return self.manifest[to_try]
            except KeyError:
                pass

        raise KeyError


    def get_all_programs(self):
        """
        Tranverse this manifest and return all programs exist in this manifest.
        """
        out = set()
        programs = self.manifest.values()
        for program in programs:
            if type(program) == ProgramManifest:
                program_set = program.get_all_programs()
            else:
                program_set = set([program])
            out.update(program_set)

        return out

    def extract_superformat(self, name):
        """
        In comes the program name, out comes the superformat (html, json, xml, etc)
        and the new program name with superstring removed.
        """
        if '.' in name:
            splitted = name.split('.')
            return (splitted[0], splitted[1])
        else:
            return (name, None)

    def parse_invocation(self, invocation, controller_tag=''):
        if invocation.endswith('/'):
            invocation = invocation[:-1]
        if invocation.startswith('/'):
            invocation = invocation[1:]

        splitted_path = invocation.split('/')
        start_name = splitted_path[0]
        start_args = splitted_path[1:]

        parsed = self._parse(start_name, start_args, controller_tag)
        parsed['invocation'] = invocation
        return parsed

    def _parse(self, program_name, args, controller_tag):
        """
        Recursive function to transversing nested manifests
        """
        program_name, superformat = self.extract_superformat(program_name)
        try:
            program = self.get_program(program_name, controller_tag)
        except KeyError:
            # program name is not in keys, drop down to root...
            if '' in self.manifest:
                result = self.get_program('', controller_tag)
                if type(result) == ProgramManifest:
                    return result._parse(program_name, args, controller_tag)
                else:
                    return {
                        'program': result,
                        'name': '',
                        'superformat': None,
                        'superformat_mime': None,
                        'args': [program_name] + args,
                    }
            else:
                raise ProgramNotFound('Program %s Does Not Exist' % program_name)
        else:
            if type(program) == ProgramManifest:
                if program_name == '':
                    return program._parse('', args, controller_tag)
                if not args:
                    raise ProgramNotFound('No root program for namespace, and no program match')
                return program._parse(args[0], args[1:], controller_tag)
            else:
                return {
                    'program': program,
                    'name': program_name,
                    'superformat': superformat,
                    'superformat_mime': super_accept_to_mimetype(superformat),
                    'args': args,
                }

from giotto.programs.shell import Shell
from giotto.programs.make_tables import MakeTables
management_manifest = ProgramManifest({
    'make_tables': MakeTables(),
    'shell': Shell(),
})