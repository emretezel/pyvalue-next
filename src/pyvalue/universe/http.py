"""Fetch one document over HTTPS from one named host, and from nowhere else.

The universe load downloads from two places: the SEC, which is sent a contact
string that names a person, and a fund sponsor's website. Both go through this
one function, which is strict about where a request may go: only the host the
caller names, only over HTTPS, and never along a redirect. So whatever a
caller puts into the headers stays with the host it was meant for.

Author: Emre Tezel
"""

import gzip
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Mapping
from email.message import Message
from typing import IO

from pyvalue.universe.errors import UniverseError

# A holdings filing of a broad fund is up to about ten megabytes.
_TIMEOUT_SECONDS: float = 120.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect.

    urllib would repeat the request, headers included, at whatever address a
    redirect names. Declining to build that second request turns a redirect
    into an HTTP error, so the headers never leave the host they were sent to.
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


def fetch_https(
    url: str, host: str, headers: Mapping[str, str], error: type[UniverseError]
) -> bytes:
    """Fetch one document from one host over HTTPS.

    Args:
        url: The address to fetch.
        host: The only host the address may be on.
        headers: The request headers. ``Accept-Encoding: gzip`` is added, and
            a compressed answer is unpacked.
        error: The error to raise. Each caller has its own, so that a failed
            filing download and a failed sponsor file read as what they are.

    Returns:
        The document's bytes, decompressed.

    Raises:
        UniverseError: Of the class given as ``error``, if the address is not
            on ``host`` over HTTPS, or the download fails. The message names
            the address and the cause and never a header.
    """
    address = urllib.parse.urlsplit(url)
    if address.scheme != "https" or address.hostname != host:
        raise error(f"refusing to fetch {url}: only https://{host}/ is allowed")
    request = urllib.request.Request(url, headers={**headers, "Accept-Encoding": "gzip"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except (OSError, EOFError, zlib.error) as failure:
        # urllib's own errors derive from OSError; the other two are what a
        # cut-off or damaged compressed body raises. None of them carries the
        # request headers, so the message cannot leak what was sent in them.
        raise error(f"cannot download {url}: {failure}") from failure
    return body
