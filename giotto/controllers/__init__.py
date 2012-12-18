import inspect
import json

from giotto.programs import GiottoProgram
from giotto.exceptions import InvalidInput, ProgramNotFound, MockNotFound, ControlMiddlewareInterrupt, NotAuthorized
from giotto.primitives import GiottoPrimitive
from giotto.keyvalue import DummyKeyValue

class GiottoController(object):
    middleware_interrupt = None
    
    def __init__(self, request, manifest, model_mock=False, errors=None):
        from giotto import config
        self.request = request
        self.model_mock = model_mock
        self.cache = config.cache or DummyKeyValue()
        self.errors = errors
        self.manifest = manifest

        # the program that corresponds to this invocation
        invocation = self.get_invocation()
        name = self.get_controller_name()
        parsed = self.manifest.parse_invocation(invocation, name)

        self.program = parsed['program']
        self.program.name = parsed['name']
        self.path_args = parsed['args']
        self.mimetype = parsed['superformat_mime'] or self.mimetype_override() or self.default_mimetype

    def get_response(self):
        try:
            self.request = self.program.execute_input_middleware_stream(self.request, self)
        except ControlMiddlewareInterrupt as exc:
            # A middleware class returned a control object, save it to the class.
            # The get_data_response method will use it.
            self.middleware_interrupt = exc.control
        except NotAuthorized as exc:
            self.middleware_interrupt = exc

        response = self.get_concrete_response()

        return self.program.execute_output_middleware_stream(self.request, response, self)

    def get_data_response(self):
        """
        Execute the model and view, and handle the cache.
        Returns controller-agnostic response data.
        """
        if self.middleware_interrupt:
            return self.middleware_interrupt

        if self.model_mock and self.program.has_mock_defined():
            model_data = self.program.get_model_mock()
        else:
            args, kwargs = self.program.get_model_args_kwargs()
            data = self.get_data_for_model(args, kwargs)

            if self.program.cache and not self.errors:
                key = self.get_cache_key(data)
                hit = self.cache.get(key)
                if hit:
                    return hit
        
            model_data = self.program.execute_model(data)
        
        response = self.program.execute_view(model_data, self.mimetype, self.errors)

        if self.program.cache and not self.errors and not self.model_mock:
            self.cache.set(key, response, self.program.cache)

        return response

    def get_data_for_model(self, args, kwargs):
        """
        In comes args and kwargs expected for the model. Out comes the data from
        this invocation that will go to the model.
        In other words, this function does the 'data negotiation' between the
        controller and the model.
        """
        raw_data = self.get_raw_data()
        defaults = kwargs
        values = args + kwargs.keys()

        output = {}
        i = -1
        for i, value in enumerate(values):
            if value in defaults:
                may_be_primitive = defaults[value]
                if isinstance(may_be_primitive, GiottoPrimitive):
                    output[value] = self.get_primitive(may_be_primitive.name)
                else:
                    output[value] = may_be_primitive

            if i + 1 <= len(self.path_args):
                output[value] = self.path_args[i]
            if value in raw_data:
                output[value] = raw_data[value]

        if len(self.path_args) > i + 1:
            # there are too many positional arguments for this program.
            raise ProgramNotFound("Too many positional arguments for program: '%s'" % self.program.name)

        if not len(output) == len(values):
            raise ProgramNotFound("Not enough data for program '%s'" % self.program.name)

        return output


    def __repr__(self):
        controller = self.get_controller_name()
        model = self.get_program_name()
        data = self.get_data()
        return "<%s %s - %s - %s>" % (  
            self.__class__.__name__, controller, model, data
        )

    def mimetype_override(self):
        """
        In some circumstances, the returned mimetype can be changed. Return that here.
        Otherwise the default or superformat will be used.
        """
        return None

    def get_cache_key(self, data):
        try:
            controller_args = json.dumps(data, separators=(',', ':'), sort_keys=True)
        except TypeError:
            # controller contains info that can't be json serialized:
            controller_args = str(data)

        program = self.program.name
        return "%s(%s)(%s)" % (controller_args, program, self.mimetype)
