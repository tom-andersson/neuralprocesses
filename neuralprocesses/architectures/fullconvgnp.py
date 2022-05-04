import lab as B
import wbml.out as out

import neuralprocesses as nps  # This fixes inspection below.
from .convgnp import (
    _convgnp_init_dims,
    _convgnp_resolve_architecture,
    _convgnp_construct_encoder_setconvs,
    _convgnp_optional_division_by_density,
    _convgnp_construct_decoder_setconv,
)
from .util import parse_transform
from ..util import register_model

__all__ = ["construct_fullconvgnp"]


@register_model
def construct_fullconvgnp(
    dim_x=1,
    dim_y=1,
    dim_yc=None,
    dim_yt=None,
    points_per_unit=64,
    margin=0.1,
    conv_arch="unet",
    unet_channels=(64,) * 6,
    unet_kernels=5,
    unet_activations=None,
    unet_resize_convs=False,
    unet_resize_conv_interp_method="nearest",
    dws_receptive_field=None,
    dws_layers=6,
    dws_channels=64,
    encoder_scales=None,
    decoder_scale=None,
    divide_by_density=True,
    epsilon=1e-4,
    transform=None,
    dtype=None,
    nps=nps,
):
    """A Fully Convolutional Gaussian Neural Process.

    Sets the attribute `receptive_field` to the receptive field of the model.

    Args:
        dim_x (int, optional): Dimensionality of the inputs. Defaults to 1.
        dim_y (int, optional): Dimensionality of the outputs. Defaults to 1.
        dim_yc (int or tuple[int], optional): Dimensionality of the outputs of the
            context set. You should set this if the dimensionality of the outputs
            of the context set is not equal to the dimensionality of the outputs
            of the target set. You should also set this if you want to use multiple
            context sets. In that case, set this equal to a tuple of integers
            indicating the respective output dimensionalities.
        dim_yt (int, optional): Dimensionality of the outputs of the target set. You
            should set this if the dimensionality of the outputs of the target set is
            not equal to the dimensionality of the outputs of the context set.
        points_per_unit (float, optional): Density of the internal discretisation.
            Defaults to 64.
        margin (float, optional): Margin of the internal discretisation. Defaults to
            0.1.
        conv_arch (str, optional): Convolutional architecture to use. Must be one of
            `"unet"` or `"dws"`. Defaults to `"unet"`.
        unet_channels (tuple[int], optional): Channels of every layer of the UNet.
            Defaults to six layers each with 64 channels.
        unet_kernels (int or tuple[int], optional): Sizes of the kernels in the UNet.
            Defaults to 5.
        unet_activations (object or tuple[object], optional): Activation functions
            used by the UNet.
        unet_resize_convs (bool, optional): Use resize convolutions rather than
            transposed convolutions in the UNet. Defaults to `False`.
        unet_resize_conv_interp_method (str, optional): Interpolation method for the
            resize convolutions in the UNet. Can be set to "bilinear". Defaults
            to "nearest".
        dws_receptive_field (float, optional): Receptive field of the DWS architecture.
            Must be specified if `conv_arch` is set to "dws".
        dws_layers (int, optional): Layers of the DWS architecture. Defaults to 8.
        dws_channels (int, optional): Channels of the DWS architecture. Defaults to 64.
        encoder_scales (float or tuple[float], optional): Initial value for the length
            scales of the set convolutions for the context sets embeddings. Defaults
            to `2 / points_per_unit`.
        decoder_scale (float, optional): Initial value for the length scale of the
            set convolution in the decoder. Defaults to `2 / points_per_unit`.
        divide_by_density (bool, optional): Divide by the density channel. Defaults
            to `True`.
        epsilon (float, optional): Epsilon added by the set convolutions before
            dividing by the density channel. Defaults to `1e-4`.
        transform (str or tuple[float, float], optional): Bijection applied to the
            output of the model. This can help deal with positive of bounded data.
            Must be either `"positive"` for positive data or `(lower, upper)` for data
            in this open interval.
        dtype (dtype, optional): Data type.

    Returns:
        :class:`.model.Model`: FullConvGNP model.
    """
    dim_yc, dim_yt, conv_in_channels = _convgnp_init_dims(dim_yc, dim_yt, dim_y)

    # This model does not yet support multi-dimensional inputs.
    if dim_x != 1:
        raise NotImplementedError(
            "The FullConvGNP for now only supports single-dimensional inputs."
        )

    # Resolve the architecture.
    _convgnp_resolve_architecture(
        conv_arch,
        unet_channels,
        dws_channels,
        dws_receptive_field,
    )

    # Construct the core CNN architectures of the model.
    if conv_arch == "unet":
        conv_mean = nps.UNet(
            dim=dim_x,
            in_channels=conv_in_channels,
            out_channels=2 * dim_yt,  # Mean and noise
            channels=unet_channels,
            kernels=unet_kernels,
            activations=unet_activations,
            resize_convs=unet_resize_convs,
            resize_conv_interp_method=unet_resize_conv_interp_method,
            dtype=dtype,
        )
        conv_kernel = nps.UNet(
            dim=2 * dim_x,
            in_channels=conv_in_channels + 1,  # Add identity channel.
            # We need covariance matrices for every pair of outputs.
            out_channels=dim_yt * dim_yt,
            # Keep the parameters in check.
            channels=tuple(n // 2 for n in unet_channels),
            kernels=unet_kernels,
            activations=unet_activations,
            resize_convs=unet_resize_convs,
            resize_conv_interp_method=unet_resize_conv_interp_method,
            dtype=dtype,
        )
        receptive_field = conv_mean.receptive_field / points_per_unit
    elif conv_arch == "dws":
        conv_mean = nps.ConvNet(
            dim=dim_x,
            in_channels=conv_in_channels,
            out_channels=2 * dim_yt,  # Mean and noise
            channels=dws_channels,
            num_layers=dws_layers,
            points_per_unit=points_per_unit,
            receptive_field=dws_receptive_field,
            dtype=dtype,
        )
        conv_kernel = nps.ConvNet(
            dim=2 * dim_x,
            in_channels=conv_in_channels + 1,  # Add identity channel.
            # We need covariance matrices for every pair of outputs.
            out_channels=dim_yt * dim_yt,
            channels=dws_channels // 2,  # Keep the parameters in check.
            num_layers=dws_layers,
            points_per_unit=points_per_unit // 2,  # Keep memory in control.
            receptive_field=dws_receptive_field,
            dtype=dtype,
        )
        receptive_field = dws_receptive_field
    else:
        raise ValueError(f'Architecture "{conv_arch}" invalid.')

    # Construct the discretisations, taking into account that the input to the UNet
    # must play nice with the halving layers.
    disc_mean = nps.Discretisation(
        points_per_unit=points_per_unit,
        multiple=2**conv_mean.num_halving_layers,
        margin=margin,
        dim=dim_x,
    )
    disc_kernel = nps.Discretisation(
        points_per_unit=points_per_unit // 2,  # Keep memory in control.
        multiple=2**conv_kernel.num_halving_layers,
        margin=margin,
        dim=dim_x,  # Only 1D, because the input is later repeated to make it 2D.
    )

    # Construct model.
    model = nps.Model(
        nps.Parallel(
            nps.FunctionalCoder(
                disc_mean,
                nps.Chain(
                    nps.PrependDensityChannel(),
                    _convgnp_construct_encoder_setconvs(
                        nps,
                        encoder_scales,
                        dim_yc,
                        disc_mean,
                        dtype,
                    ),
                    _convgnp_optional_division_by_density(
                        nps,
                        divide_by_density,
                        epsilon,
                    ),
                    nps.Materialise(),
                    nps.DeterministicLikelihood(),
                ),
            ),
            nps.FunctionalCoder(
                disc_kernel,
                nps.MapDiagonal(  # Map to diagonal of squared space.
                    nps.Chain(
                        nps.PrependDensityChannel(),
                        _convgnp_construct_encoder_setconvs(
                            nps,
                            encoder_scales,
                            dim_yc,
                            disc_kernel,
                            dtype,
                            # Multiply the initialisation by two since we halved the
                            # PPU.
                            init_factor=2,
                        ),
                        _convgnp_optional_division_by_density(
                            nps,
                            divide_by_density,
                            epsilon,
                        ),
                        nps.Materialise(),
                        # We only need the identity channel once, so insert it after
                        # materialising.
                        nps.PrependIdentityChannel(),
                        nps.DeterministicLikelihood(),
                    ),
                ),
            ),
        ),
        nps.Chain(
            nps.Parallel(
                nps.Chain(
                    conv_mean,
                    nps.RepeatForAggregateInputs(
                        nps.Chain(
                            _convgnp_construct_decoder_setconv(
                                nps,
                                decoder_scale,
                                disc_mean,
                                dtype,
                            ),
                            # Select the right target output.
                            nps.SelectFromChannels(dim_y, dim_y),
                        )
                    ),
                ),
                nps.MapDiagonal(
                    nps.Chain(
                        conv_kernel,
                        nps.ToDenseCovariance(),
                        nps.DenseCovariancePSDTransform(),
                        nps.FromDenseCovariance(),
                        nps.RepeatForAggregateInputPairs(
                            nps.Chain(
                                _convgnp_construct_decoder_setconv(
                                    nps,
                                    decoder_scale,
                                    disc_kernel,
                                    dtype,
                                    # Multiply the initialisation by two since we halved
                                    # the PPU.
                                    init_factor=2,
                                ),
                                nps.ToDenseCovariance(),
                                # Select the right target output.
                                nps.SelectFromDenseCovarianceChannels(),
                            ),
                        ),
                    ),
                ),
            ),
            nps.DenseGaussianLikelihood(),
            parse_transform(nps, transform=transform),
        ),
    )

    # Set attribute `receptive_field`.
    out.kv("Receptive field", receptive_field)
    model.receptive_field = receptive_field

    return model
