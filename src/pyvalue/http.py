"""Fetch one document over HTTPS from one named host, and from nowhere else.

pyvalue downloads from a few places: the SEC, which is sent a contact string
that names a person; a fund sponsor's website; and a data provider, which is
sent an API key. All go through this one function, which is strict about
where a request may go: only the host the caller names, only over HTTPS, and
never along a redirect. So whatever a caller sends stays with the host it was
meant for.

It is as strict about what it says. A message names the address and the cause
and nothing that was sent: no header, and none of the secret parts of an
address (a provider's API key travels in the address itself).

The module lives outside every component, like ``pyvalue.errors``, so that
each component can download without depending on another.

Author: Emre Tezel
"""

import gzip
import http.client
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Mapping
from email.message import Message
from typing import IO

from pyvalue.errors import PyvalueError

# A holdings filing of a broad fund is up to about ten megabytes.
_TIMEOUT_SECONDS: float = 120.0

# What stands in a message where a secret would otherwise be quoted.
_HIDDEN: str = "[hidden]"

# The status a host answers with when it has no document at the address.
_NOT_FOUND: int = 404


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect.

    urllib would repeat the request, headers and address included, at whatever
    address a redirect names. Declining to build that second request turns a
    redirect into an HTTP error, so nothing that was sent leaves the host it
    was sent to.
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


def _without(text: str, secrets: Mapping[str, str]) -> str:
    """Return ``text`` with every secret value, plain or encoded, taken out.

    The causes caught below do not normally quote the address. One does (a
    malformed address), and a later version of the standard library may add
    another, so the cause is cleaned whatever it is.
    """
    for value in secrets.values():
        # An empty value would match between every two characters.
        if not value:
            continue
        for form in (value, urllib.parse.quote(value), urllib.parse.quote_plus(value)):
            text = text.replace(form, _HIDDEN)
    return text


def fetch_https(
    url: str,
    host: str,
    headers: Mapping[str, str],
    error: type[PyvalueError],
    *,
    secret_query: Mapping[str, str] | None = None,
    not_found: type[PyvalueError] | None = None,
) -> bytes:
    """Fetch one document from one host over HTTPS.

    Args:
        url: The address to fetch, without any secret part.
        host: The only host the address may be on.
        headers: The request headers. ``Accept-Encoding: gzip`` is added, and
            a compressed answer is unpacked.
        error: The error to raise. Each caller has its own, so that a failed
            filing download and a failed provider request read as what they
            are.
        secret_query: Query parts that are added to the address for the
            request and appear in no message, such as a provider's API key.
        not_found: The error to raise when the host answers that it has no
            document at the address. Without it, that is a failed download
            like any other.

    Returns:
        The document's bytes, decompressed.

    Raises:
        PyvalueError: Of the class given as ``error`` (or as ``not_found``),
            if the address is not on ``host`` over HTTPS, or the download
            fails. The message names ``url`` and the cause, and never a
            header or a secret query part.
    """
    secrets: Mapping[str, str] = secret_query or {}
    address = urllib.parse.urlsplit(url)
    if address.scheme != "https" or address.hostname != host:
        raise error(f"refusing to fetch {url}: only https://{host}/ is allowed")
    target = url
    if secrets:
        # urlencode escapes every character that could break the address or
        # start a second query part, so a secret cannot change where the
        # request goes.
        joiner = "&" if address.query else "?"
        target = f"{url}{joiner}{urllib.parse.urlencode(secrets)}"
    request = urllib.request.Request(target, headers={**headers, "Accept-Encoding": "gzip"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except (OSError, EOFError, zlib.error, http.client.HTTPException) as failure:
        # urllib's own errors derive from OSError; EOFError and zlib.error are
        # what a cut-off or damaged compressed body raises; HTTPException is
        # what the standard library raises for an address or an answer it
        # cannot handle. None of them carries the request headers.
        kind = error
        if (
            not_found is not None
            and isinstance(failure, urllib.error.HTTPError)
            and failure.code == _NOT_FOUND
        ):
            kind = not_found
        message = f"cannot download {url}: {_without(str(failure), secrets)}"
        if secrets:
            # The cause is not chained: its own text may quote the address
            # that was requested, secret parts included, and a traceback would
            # print it.
            raise kind(message) from None
        raise kind(message) from failure
    return body
