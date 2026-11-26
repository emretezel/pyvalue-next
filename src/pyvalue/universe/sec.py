"""Download a pinned filing from the SEC.

The SEC asks automated clients to identify themselves with a contact string in
the ``User-Agent`` header. That string names a person, so this module is
careful with it: it goes to ``www.sec.gov`` over HTTPS and nowhere else, it is
never followed along a redirect, and it never appears in a message.

Author: Emre Tezel
"""

import contextlib
import gzip
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import IO

from pyvalue.universe.errors import FilingError
from pyvalue.universe.funds import FundDefinition, read_pinned_filing

# The one host a contact string may be sent to.
SEC_HOST: str = "www.sec.gov"

# A holdings filing of a broad fund is up to about ten megabytes.
_TIMEOUT_SECONDS: float = 120.0

# What fetches a URL: (url, contact string) -> the bytes of the response. A
# parameter of this type lets tests stand in for the network.
type Fetch = Callable[[str, str], bytes]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect.

    urllib would repeat the request, headers included, at whatever address a
    redirect names. Declining to build that second request turns a redirect
    into an HTTP error, so the contact string never leaves ``www.sec.gov``.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Build no follow-up request, whatever the redirect says."""
        return None


def fetch_from_sec(url: str, user_agent: str) -> bytes:
    """Fetch one document from ``www.sec.gov``.

    Args:
        url: An ``https://www.sec.gov/`` address.
        user_agent: The contact string the SEC asks for.

    Returns:
        The document's bytes, decompressed.

    Raises:
        FilingError: If the address is not on ``www.sec.gov`` over HTTPS, or
            the download fails.
    """
    address = urllib.parse.urlsplit(url)
    if address.scheme != "https" or address.hostname != SEC_HOST:
        raise FilingError(f"refusing to fetch {url}: only https://{SEC_HOST}/ is allowed")
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except (OSError, EOFError, zlib.error) as error:
        # urllib's own errors derive from OSError; the other two are what a
        # cut-off or damaged compressed body raises. None of them carries the
        # request headers, so the message cannot leak the contact string.
        raise FilingError(f"cannot download {url}: {error}") from error
    return body


def download_filing(
    fund: FundDefinition, destination: Path, user_agent: str, fetch: Fetch = fetch_from_sec
) -> None:
    """Download a fund's pinned filing and keep it only if it is that filing.

    The document is written under a temporary name, read back and checked
    against the pin, and only then given its final name. So a file with the
    final name is always a complete, verified filing, even if the download was
    interrupted or the SEC answered with an error page.

    Args:
        fund: The fund whose pinned filing is downloaded.
        destination: Where to keep it.
        user_agent: The contact string the SEC asks for.
        fetch: What performs the request. Tests pass their own.

    Raises:
        FilingError: If the download fails, the file cannot be written, or
            what arrived is not the pinned filing.
    """
    body = fetch(fund.filing_url, user_agent)
    partial = destination.with_name(destination.name + ".part")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial.write_bytes(body)
        try:
            read_pinned_filing(partial, fund)
        except FilingError as error:
            # The reader's message names the temporary file, which is about to
            # be removed. Say where the document came from instead.
            raise FilingError(
                f"{fund.filing_url} did not return the pinned {fund.code} filing; nothing was kept"
            ) from error
        partial.replace(destination)
    except OSError as error:
        raise FilingError(
            f"cannot save the {fund.code} filing to {destination}: {error}"
        ) from error
    finally:
        # The temporary file must not stay, whatever happened. If it cannot be
        # removed either, the error already on its way is the one to report.
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
