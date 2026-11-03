import time
from urllib.parse import urlsplit

import httpx

from app.schemas.monitor import resolve_public_url


def perform_http_check(monitor) -> dict:
    """
    Perform one HTTP check using a DNS-validated, pinned public IP.

    The original hostname is retained for the Host header and TLS SNI.
    Redirects are disabled and response bodies are never stored.
    """

    start_time = time.perf_counter()

    result = {
        "status": "down",
        "status_code": None,
        "latency_ms": None,
        "error_code": None,
    }

    try:
        # Resolve and validate every DNS result immediately before the request.
        host, port, addresses = resolve_public_url(monitor.url)

        # Select one validated public IP deterministically.
        pinned_ip = sorted(
            addresses,
            key=lambda address: (address.version, int(address)),
        )[0]

        original_url = httpx.URL(monitor.url)

        # Replace the hostname in the connection URL with the validated IP.
        pinned_url = original_url.copy_with(host=str(pinned_ip))

        # Preserve the original HTTP authority, including an explicit port.
        original_authority = urlsplit(monitor.url).netloc

        timeout = httpx.Timeout(monitor.timeout_seconds)

        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            # Send directly to the pinned IP while preserving Host and TLS SNI.
            with client.stream(
                "GET",
                pinned_url,
                headers={
                    "Host": original_authority,
                },
                extensions={
                    "sni_hostname": host,
                },
            ) as response:

                result["status_code"] = response.status_code

                result["status"] = (
                    "up"
                    if response.status_code == monitor.expected_status
                    else "down"
                )

                if result["status"] == "down":
                    result["error_code"] = "unexpected_status"
    except ValueError:
        result["error_code"] = "unsafe_url"

    except httpx.TimeoutException:
        result["error_code"] = "timeout"

    except httpx.ConnectError:
        result["error_code"] = "connection_error"

    except httpx.RequestError:
        result["error_code"] = "request_error"

    finally:
        result["latency_ms"] = round(
            (time.perf_counter() - start_time) * 1000
        )

    return result
