# Production model packaging

The fitted production estimators were not retrained or modified for Stage 8. The original ExtraTrees solar artefact was 337,998,881 bytes (322.34 MiB), which is unsuitable for ordinary GitHub storage.

Lossless joblib compression was benchmarked on 512 representative rows from the historical modelling dataset. Each candidate was reloaded and its predictions were compared with those from the original fitted estimator at `rtol=1e-12` and `atol=1e-12`.

| Candidate | Size (bytes) | Size (MiB) | Approx. load time | Maximum absolute prediction difference |
|---|---:|---:|---:|---:|
| zlib level 3 | 117,407,324 | 111.97 | 1.44 s | 0.0 |
| zlib level 5 | 115,949,277 | 110.58 | 1.77 s | 0.0 |
| lzma level 3 | 99,540,687 | 94.93 | 6.30 s | 0.0 |

The lzma level-3 candidate was selected and placed at the canonical path `models/solar_extratrees.joblib`. It is the same fitted ExtraTrees model and retains the locked historical metrics. The original uncompressed file and temporary candidates were removed after verification.

The selected artefact is below 100 MiB and below GitHub's 100,000,000-byte per-file limit, so Git LFS is not required. The Dash web process does not load this model during ordinary page views; model loading remains isolated in `python -m src.forecast_tomorrow`.
