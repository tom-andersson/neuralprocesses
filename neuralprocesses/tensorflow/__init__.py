import lab.tensorflow  # noqa
from plum import convert

from .nn import *
from .. import *  # noqa
from ..util import modules, models


def create_init(module):
    def __init__(self, *args, **kw_args):
        Module.__init__(self)
        module.__init__(self, *args, **kw_args)

    return __init__


def create_tf_call(module):
    def call(self, x, training=False):
        args = convert(x, tuple)  # Deal with multiple arguments passed as a tuple.
        try:
            return module.__call__(self, *args, training=training)
        except TypeError:
            return module.__call__(self, *args)

    return call


for module in modules:
    name = module.__name__
    globals()[name] = type(
        name,
        (module, Module),
        {
            "__init__": create_init(module),
            "call": create_tf_call(module),
        },
    )


class Namespace:
    pass


ns = Namespace()
ns.__dict__.update(globals())

for model in models:
    name = "_".join(model.__name__.split("_")[1:])
    globals()[name] = model(ns)
