import time
import random
import requests
from requests.adapters import HTTPAdapter
from typing import Callable, Any, Dict, Optional
from utils.config import API_CONNECT_TIMEOUT, API_READ_TIMEOUT, API_MAX_RETRIES, API_BACKOFF_BASE, API_BACKOFF_MAX
from utils.logger import setup_logger

logger = setup_logger("Resilience")

class TimeoutHTTPAdapter(HTTPAdapter):
    """
    Enforces connect and read timeouts on all session calls.
    """
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.pop("timeout", (API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)

def get_resilient_session() -> requests.Session:
    """
    Generates a resilient requests Session configured with default timeouts.
    """
    session = requests.Session()
    adapter = TimeoutHTTPAdapter(timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def resilient_request(
    request_func: Callable[[], requests.Response],
    provider: str,
    ticker: Optional[str] = None,
    fallback_value: Any = None,
    max_retries: int = API_MAX_RETRIES,
    backoff_base: float = API_BACKOFF_BASE,
    backoff_max: float = API_BACKOFF_MAX
) -> Any:
    """
    Executes a request function with bounded exponential backoff and retry mechanisms.
    Retries only transient errors (timeouts, connection issues, 429 rate limit, 5xx server errors).
    Fails immediately for non-transient status errors (400, 401, 403, 404).
    Logs terminal failures in the observable [API_FAILURE] format.
    """
    attempts = 0
    last_error = "Unknown"
    
    while attempts <= max_retries:
        attempts += 1
        start_time = time.time()
        try:
            response = request_func()
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                return response
                
            last_error = f"HTTP {response.status_code}"
            
            # Transient failures (Retryable)
            if response.status_code in [429, 500, 502, 503, 504]:
                if attempts <= max_retries:
                    # Exponential backoff with jitter
                    sleep_time = min(backoff_max, backoff_base * (2 ** (attempts - 1)) + random.uniform(0.0, 0.5))
                    logger.warning(
                        f"Transient HTTP status {response.status_code} received from {provider}. "
                        f"Retry attempt {attempts}/{max_retries} in {sleep_time:.2f}s."
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    break
            else:
                # Permanent errors (Non-retryable)
                break
                
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            last_error = "ConnectTimeout"
            if attempts <= max_retries:
                sleep_time = min(backoff_max, backoff_base * (2 ** (attempts - 1)) + random.uniform(0.0, 0.5))
                logger.warning(f"Connection timeout/error for {provider}. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                continue
            else:
                break
        except requests.exceptions.ReadTimeout as e:
            last_error = "ReadTimeout"
            if attempts <= max_retries:
                sleep_time = min(backoff_max, backoff_base * (2 ** (attempts - 1)) + random.uniform(0.0, 0.5))
                logger.warning(f"Read timeout for {provider}. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                continue
            else:
                break
        except Exception as e:
            last_error = type(e).__name__
            break

    # If all attempts exhausted, log in the required telemetry format
    logger.error(
        f"[API_FAILURE] provider={provider} ticker={ticker or 'N/A'} attempts={attempts} "
        f"error={last_error} fallback=NEUTRAL"
    )
    return fallback_value
