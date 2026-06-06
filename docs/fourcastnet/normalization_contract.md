# FourCastNet V0 Normalization Contract

Contract version: `fcn_v0_nvlabs_20ch_first20stats`

This contract defines the raw tensor emitted by the Platinum Parquet to
FourCastNet pipeline and the normalization required before passing that tensor
to a FourCastNet V0 backbone.

## Tensor

- Shape: `(1, 20, 720, 1440)`
- Dtype: `float32`
- Latitude order: descending, `90.0 -> -89.75`, step `-0.25`
- Longitude order: ascending, `0.0 -> 359.75`, step `0.25`
- ECMWF 721-latitude policy: `drop_south_pole`
- Longitude policy: normalize to `[0, 360)` and sort ascending
- Tensor emitted by Glue: raw physical values, not normalized
- Model input requirement: normalize before Batch Transform or inside the model wrapper

Normalization formula:

```text
normalized[:, channel, :, :] =
  (raw[:, channel, :, :] - global_mean[channel]) / global_std[channel]
```

## Stats Policy

Use NVlabs FourCastNet V0 global stats from `data/fourcastnet_assets_v0`:

- `global_means.npy`
- `global_stds.npy`

Those stats can contain 21 channels because of a legacy SST channel. This
contract uses `stats_channel_policy=first_20_channels`.

- Original stats channels: `21`
- Used stats channels: `20`
- Dropped stats channel index: `20`
- Dropped stats channel name: `sst`

If stats have 21 channels and the policy is omitted, validation must fail.

## Channel Order

| Index | Variable | Level | Expected raw unit | Stats index used | Notes |
|---:|---|---:|---|---:|---|
| 0 | `u10` | surface | `m s**-1` | 0 | 10 m U wind |
| 1 | `v10` | surface | `m s**-1` | 1 | 10 m V wind |
| 2 | `t2m` | surface | `K` | 2 | 2 m temperature |
| 3 | `sp` | surface | `Pa` | 3 | Surface pressure |
| 4 | `msl` | surface | `Pa` | 4 | Mean sea-level pressure |
| 5 | `t` | 850 hPa | `K` | 5 | Air temperature |
| 6 | `u` | 1000 hPa | `m s**-1` | 6 | U wind |
| 7 | `v` | 1000 hPa | `m s**-1` | 7 | V wind |
| 8 | `z` | 1000 hPa | `m**2 s**-2` | 8 | Geopotential |
| 9 | `u` | 850 hPa | `m s**-1` | 9 | U wind |
| 10 | `v` | 850 hPa | `m s**-1` | 10 | V wind |
| 11 | `z` | 850 hPa | `m**2 s**-2` | 11 | Geopotential |
| 12 | `u` | 500 hPa | `m s**-1` | 12 | U wind |
| 13 | `v` | 500 hPa | `m s**-1` | 13 | V wind |
| 14 | `z` | 500 hPa | `m**2 s**-2` | 14 | Geopotential |
| 15 | `t` | 500 hPa | `K` | 15 | Air temperature |
| 16 | `z` | 50 hPa | `m**2 s**-2` | 16 | Geopotential |
| 17 | `r` | 500 hPa | `%` | 17 | Relative humidity |
| 18 | `r` | 850 hPa | `%` | 18 | Relative humidity |
| 19 | `tcwv` | surface/integrated | `kg m**-2` | 19 | Total column water vapor |

## Validation Gate

Do not run Batch Transform until a validation report says:

- `tensor_ok=true`
- `stats_ok=true`
- `normalization_ok=true`
- `contract_version=fcn_v0_nvlabs_20ch_first20stats`

Recommended scoped acceptance run:

```text
YEAR=2026
MONTH=06
DAY=02
HOUR=06z
LEAD_HOURS=0
MAX_FILES=1
STATS_CHANNEL_POLICY=first_20_channels
```
