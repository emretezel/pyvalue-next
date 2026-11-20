# pyvalue

A value-investing toolkit with a curated global stock universe, data-quality checks on fundamentals, and quality-at-a-reasonable-price screening.

> **Status: under construction.** This repository (`pyvalue-next`) is the ground-up successor to the original pyvalue (0.1.0). It holds the project skeleton only, and takes over the `pyvalue` name once its first phase is complete.

## Disclaimer

This project is provided for educational and informational purposes only and does not constitute investment, financial, legal, or tax advice. Outputs may be inaccurate, incomplete, or delayed and are provided "as is" without warranties of any kind. You are solely responsible for any investment decisions and outcomes based on this software; use at your own risk. Nothing here is an offer or solicitation to buy or sell any security, and past performance is not indicative of future results. Consult a licensed professional before making investment decisions.

## Installation

Requires Python 3.14 or newer and [uv](https://docs.astral.sh/uv/). The original pyvalue installs a package with the same name, so give this project its own environment.

```bash
conda create -n pyvalue-next python=3.14
conda activate pyvalue-next
UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX" uv sync --locked --extra dev
```

This installs the exact dependency versions recorded in `uv.lock`. `python -m pip install -e ".[dev]"` also works without uv, but it resolves the newest versions the ranges in `pyproject.toml` allow.
