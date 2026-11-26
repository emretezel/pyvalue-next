# pyvalue

A value-investing toolkit with a curated global stock universe, data-quality checks on fundamentals, and quality-at-a-reasonable-price screening.

> **Status: under construction.** This repository (`pyvalue-next`) is the ground-up successor to the original pyvalue (0.1.0). So far it can create its database, load the companies and securities of its stock universe, keep a data provider's exchange and symbol lists, and give each security its exchange listing from those lists; prices and fundamentals come next. It takes over the `pyvalue` name once its first phase is complete.

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

## Usage

Create the database, or bring an existing one up to the latest schema:

```bash
pyvalue db migrate
```

The database is `data/pyvalue.db` in the folder you run the command from. `--db PATH` points it elsewhere. Running the command again is harmless: it applies only what is missing.

Fill the stock universe with the companies and securities held by two broad index funds (VTI and VXUS):

```bash
pyvalue universe load
```

The first run downloads the funds' holdings filings from the SEC into `data/sec/`, and Vanguard's own holdings files, which add a ticker to each holding, into `data/vanguard/`. The SEC asks automated clients to identify themselves, so put your contact details into `private/config.toml` first; they are sent to the SEC only:

```toml
[sec]
user_agent = "Your Name your@email.address"
```

The command lists what it did not load in `data/universe/`. Running it again adds nothing.

The design is described in [`docs/architecture.md`](docs/architecture.md), the tables in [`docs/database/`](docs/database/README.md), and the decisions behind both in [`docs/adr/`](docs/adr/).
