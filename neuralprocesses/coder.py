import lab as B
import matrix  # noqa

from . import _dispatch
from .util import register_module

__all__ = ["InputsCoder", "FunctionalCoder", "DeepSet", "MapDiagonal"]


@register_module
class InputsCoder:
    """Encode with the target inputs."""


@_dispatch
def code(coder: InputsCoder, xz, z, x, **kw_args):
    return x, x


@register_module
class FunctionalCoder:
    """A coder that codes to a discretisation for a functional representation.

    Args:
        disc (:class:`.discretisation.AbstractDiscretisation`): Discretisation.
        coder (coder): Coder.

    Attributes:
        disc (:class:`.discretisation.AbstractDiscretisation`): Discretisation.
        coder (coder): Coder.
    """

    def __init__(self, disc, coder):
        self.disc = disc
        self.coder = coder


@_dispatch
def code(coder: FunctionalCoder, xz, z, x, **kw_args):
    x = coder.disc(xz, x, **kw_args)
    return code(coder.coder, xz, z, x, **kw_args)


@register_module
class DeepSet:
    """Deep set.

    Args:
        phi (function): Pre-aggregation function.
        rho (function): Post-aggregation function.
        agg (function, optional): Aggregation function. Defaults to summing.

    Attributes:
        phi (function): Pre-aggregation function.
        rho (function): Post-aggregation function.
        agg (function): Aggregation function.
    """

    def __init__(
        self,
        phi,
        rho,
        agg=lambda x: B.sum(x, axis=2, squeeze=False),
    ):
        self.phi = phi
        self.rho = rho
        self.agg = agg


@_dispatch
def code(coder: DeepSet, xz, z, x, **kw_args):
    z = B.concat(xz, z, axis=1)
    z = coder.phi(z)
    z = coder.agg(z)  # This aggregates over the data dimension.
    z = coder.rho(z)
    return x, z


@register_module
class MapDiagonal:
    """Map to the diagonal of the squared space.

    Args:
        coder (coder): Coder to apply the mapped vales to.
        map_encoding (bool, optional): Also map the encoding to the diagonal. Set
            this to `False` if the encoder had already been mapped to the diagonal.
            Defaults to `True`.

    Attributes:
        coder (function): Pre-aggregation function.
        map_encoding (bool): Map the encoding to the diagonal.
    """

    def __init__(self, coder, map_encoding=True):
        self.coder = coder
        self.map_encoding = map_encoding


@_dispatch
def code(coder: MapDiagonal, xz, z, x, **kw_args):
    if coder.map_encoding:
        xz = B.concat(xz, xz, axis=1)
    return code(coder.coder, xz, z, (x, x))


def _map_encoding_to_diagonal(xz: B.Numeric):
    return B.concat(xz, xz, axis=1)
