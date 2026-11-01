import time

import httpx

from app.schemas.monitor import validate_public_url


def perform_http_check(monitor) -> dict:
    """
    Perform one HTTP check for a monitor.

    This MVP version does not follow redirects or store response bodies.
    """

    start_time = time.perf_counter()

    result = {
        "status": "down",
        "status_code": None,
        "latency_ms": None,
        "error_code": None,
    }

    try:
        # Validate URL again immediately before making the request.
        validate_public_url(monitor.url)

        timeout = httpx.Timeout(monitor.timeout_seconds)

        # Redirects are disabled to avoid following an unchecked URL.
        # Response body is not read or stored.
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            with client.stream("GET", monitor.url) as response:
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
