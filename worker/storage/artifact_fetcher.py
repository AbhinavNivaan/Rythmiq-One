"""
Artifact fetcher for downloading documents from signed URLs.

Single responsibility: HTTP GET to artifact_url, return bytes or raise error.
No retries, no authentication (URL is pre-signed by API Gateway).
"""

import urllib.request
import urllib.error
from typing import Tuple

from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage


# Default timeout for artifact download (seconds)
DEFAULT_TIMEOUT_SECONDS = 30


def fetch_artifact(artifact_url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    """
    Download artifact from signed URL.
    
    Args:
        artifact_url: Pre-signed URL to artifact (provided by API Gateway)
        timeout: HTTP request timeout in seconds
        
    Returns:
        Raw bytes of the artifact
        
    Raises:
        ProcessingError: If download fails for any reason
    """
    try:
        # Simple HTTP GET - no auth headers needed (URL is pre-signed)
        request = urllib.request.Request(
            artifact_url,
            headers={"User-Agent": "RythmiqWorker/1.0"}
        )
        
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # Verify success status
            if response.status != 200:
                raise ProcessingError(
                    code=ErrorCode.ARTIFACT_FETCH_FAILED,
                    stage=ProcessingStage.FETCH,
                    details={"status_code": response.status}
                )
            
            return response.read()
            
    except urllib.error.HTTPError as e:
        raise ProcessingError(
            code=ErrorCode.ARTIFACT_FETCH_FAILED,
            stage=ProcessingStage.FETCH,
            details={"status_code": e.code, "reason": e.reason}
        )
    except urllib.error.URLError as e:
        raise ProcessingError(
            code=ErrorCode.ARTIFACT_FETCH_FAILED,
            stage=ProcessingStage.FETCH,
            details={"reason": str(e.reason)}
        )
    except TimeoutError:
        raise ProcessingError(
            code=ErrorCode.ARTIFACT_FETCH_FAILED,
            stage=ProcessingStage.FETCH,
            details={"reason": "timeout"}
        )
    except Exception as e:
        # Catch-all for unexpected errors - still deterministic error code
        raise ProcessingError(
            code=ErrorCode.ARTIFACT_FETCH_FAILED,
            stage=ProcessingStage.FETCH,
            details={"reason": type(e).__name__}
        )
