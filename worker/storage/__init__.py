# Worker storage module
from .spaces_client import (
    WorkerSpacesClient,
    SpacesConfig,
    create_client_from_spec,
    validate_artifact_source,
    ArtifactSourceError,
)
from .artifact_fetcher import fetch_artifact

__all__ = [
    'WorkerSpacesClient',
    'SpacesConfig',
    'create_client_from_spec',
    'validate_artifact_source',
    'ArtifactSourceError',
    'fetch_artifact',
]
