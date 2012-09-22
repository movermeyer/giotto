#!/usr/bin/env python

import sys

module_name = sys.argv[1]
model = sys.argv[2]
args = sys.argv[3:]

module = __import__(module_name, globals(), locals(), [], -1)
model_name = module.__name__ + '.' + model

raise SystemExit()

ret = controller_maps['http'].get(model_name, None)

if not ret:
    raise GiottoHttpException('Can not find model: %s in %s' % (model_name, controller_maps))

model = ret['app']
argspec = ret['argspec']

model_args = primitive_from_argspec(request, argspec)
html = model(**model_args)


def primitive_from_argspec(request, argspec):
    """
    Fill in primitives from the argspec
    """
    kwargs = dict(zip(*[reversed(l) for l in (argspec.args, argspec.defaults or [])]))
    args2 = [item for item in argspec.args if item not in kwargs.keys()]

    for item, value in kwargs.iteritems():
        if GiottoPrimitive in value.mro():
            kwargs[item] = get_primitive(request, value)

    for arg in args2:
        kwargs[arg] = request.args[arg]

    return kwargs


def get_primitive(request, primitive):
    """
    Exract a primitive from the request and return it.
    """
    if primitive.__name__ == "LOGGED_IN_USER":
        user = request.cookies.get('user')
        if user:
            return User()
        else:
            return AnonymousUser()