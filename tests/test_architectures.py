import lab as B
import numpy as np
import pytest

from .util import nps, generate_data  # noqa


def generate_arch_variations(name, **kw_args):
    variations = [
        {
            "unet_channels": (4, 8),
            "unet_kernels": (5,) * 2,
            "unet_activations": (B.relu,) * 2,
        },
        {
            "unet_channels": (8, 16),
            "unet_kernels": (5,) * 2,
            "unet_activations": (B.relu,) * 2,
            "unet_resize_convs": False,
        },
        {
            "unet_channels": (8, 16),
            "unet_kernels": (5,) * 2,
            "unet_activations": (B.relu,) * 2,
            "unet_resize_convs": True,
        },
        {
            "conv_arch": "dws",
            "dws_channels": 8,
            "dws_layers": 4,
            "dws_receptive_field": 0.5,
        },
    ]
    return [(name, dict(config, **kw_args)) for config in variations]


@pytest.mark.parametrize("float64", [False, True])
@pytest.mark.parametrize(
    "construct_name, kw_args",
    [
        (model, dict(base_kw_args, dim_x=dim_x, dim_y=dim_y, likelihood=lik))
        for model, base_kw_args in [
            (
                "construct_gnp",
                {"num_basis_functions": 4},
            )
        ]
        + generate_arch_variations(
            "construct_convgnp",
            points_per_unit=16,
            num_basis_functions=16,
            epsilon=1e-4,
        )
        for dim_x in [1, 2]
        for dim_y in [1, 2]
        for lik in ["het", "lowrank"]
    ]
    + generate_arch_variations(
        "construct_fullconvgnp",
        dim_x=1,
        dim_y=1,
        points_per_unit=16,
        epsilon=1e-4,
    ),
)
@pytest.mark.flaky(reruns=3)
def test_architectures(nps, float64, construct_name, kw_args):
    if float64:
        nps.dtype = nps.dtype64
    model = getattr(nps, construct_name)(**kw_args, dtype=nps.dtype)
    # Generate data.
    xc, yc, xt, yt = generate_data(nps, dim_x=kw_args["dim_x"], dim_y=kw_args["dim_y"])
    model(xc, yc, xt)  # Run the model once to make sure all parameters exist.

    # Perturb all parameters to make sure that the biases aren't initialised to zero. If
    # biases are initialised to zero, then this can give zeros in the output if the
    # input is zero.
    if isinstance(nps.dtype, B.TFDType):
        weights = []
        for p in model.get_weights():
            weights.append(p + 0.01 * B.randn(p))
        model.set_weights(weights)
    elif isinstance(nps.dtype, B.TorchDType):
        for p in model.parameters():
            p.data = p.data + 0.01 * B.randn(p.data)
    else:
        raise RuntimeError("I don't know how to perturb the parameters of the model.")

    # Check passing in a non-empty context set.
    pred = model(xc, yc, xt, batch_size=2, unused_arg=None)
    objective = B.sum(pred.logpdf(yt))
    # Check that the objective is finite and of the right data type.
    assert np.isfinite(B.to_numpy(objective))
    assert B.dtype(objective) == nps.dtype

    # Also check passing the edge case of an empty context set.
    if isinstance(xc, B.Numeric):
        xc = xc[:, :, :0]
    elif isinstance(xc, tuple):
        xc = tuple(xci[:, :, :0] for xci in xc)
    else:
        raise RuntimeError("Failed to contruct empty context set.")
    yc = yc[:, :, :0]
    pred = model(xc, yc, xt, batch_size=2, unused_arg=None)
    objective = B.sum(pred.logpdf(yt))
    # Again check that the objective is finite and of the right data type.
    assert np.isfinite(B.to_numpy(objective))
    assert B.dtype(objective) == nps.dtype


def test_transform_positive(nps):
    model = nps.construct_convgnp(
        dim_x=1,
        dim_y=1,
        points_per_unit=16,
        unet_channels=(8, 16),
        transform="positive",
    )
    xc, yc, xt, yt = generate_data(nps, dim_x=1, dim_y=1)
    # Make data positive.
    yc = B.exp(yc)
    yt = B.exp(yt)

    pred = model(xc, yc, xt)
    objective = B.sum(pred.logpdf(yt))
    # Again check that the objective is finite and of the right data type.
    assert np.isfinite(B.to_numpy(objective))
    # Check that predictions and samples satisfy the constraint.
    assert B.all(pred.mean > 0)
    assert B.all(pred.sample() > 0)


def test_transform_bounded(nps):
    model = nps.construct_convgnp(
        dim_x=1,
        dim_y=1,
        points_per_unit=16,
        unet_channels=(8, 16),
        transform=(10, 11),
    )
    xc, yc, xt, yt = generate_data(nps, dim_x=1, dim_y=1)
    # Force data in the range `(10, 11)`.
    yc = 10 + 1 / (1 + B.exp(yc))
    yt = 10 + 1 / (1 + B.exp(yt))

    pred = model(xc, yc, xt)
    objective = B.sum(pred.logpdf(yt))
    # Again check that the objective is finite and of the right data type.
    assert np.isfinite(B.to_numpy(objective))
    # Check that predictions and samples satisfy the constraint.
    assert B.all(pred.mean > 10) and B.all(pred.mean < 11)
    assert B.all(pred.sample() > 10) and B.all(pred.sample() < 11)
