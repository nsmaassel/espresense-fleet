"""Bounded direct HTTP to the inventory node; never follow redirects or proxies."""
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

from tooling.fleet.inventory import ENDPOINTS


class NodeError(ValueError):
    """Safe category-only failure; transport exception text is never surfaced."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, address, timeout=5):
        self.base = f"http://{address}"
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None, timeout=None):
        request = urllib.request.Request(self.base + path, data=data,
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(request, timeout=self.timeout if timeout is None else timeout) as response:
                if not 200 <= response.status < 300:
                    raise NodeError("HTTP request rejected")
                if data is not None:
                    return None  # Firmware response text can contain private settings.
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise NodeError("node response exceeds size limit")
                return json.loads(body)
        except (OSError, urllib.error.URLError, http.client.HTTPException):
            raise NodeError("node request failed or response unconfirmed") from None
        except (ValueError, UnicodeError, RecursionError):
            raise NodeError("invalid node response") from None

    def read(self, endpoint, timeout=None):
        if endpoint not in ENDPOINTS:
            raise NodeError("unsupported endpoint")
        return self.request(f"/wifi/{endpoint}", timeout=timeout)

    def save(self, endpoint, form):
        if endpoint not in ENDPOINTS:
            raise NodeError("unsupported endpoint")
        try:
            body = urllib.parse.urlencode(form).encode("utf-8")
        except (TypeError, ValueError):
            raise NodeError("cannot encode settings form") from None
        self.request(f"/wifi/{endpoint}", body)

    def restart(self):
        self.request("/restart", b"")
