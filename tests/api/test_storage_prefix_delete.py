# tests/api/test_storage_prefix_delete.py
"""Unit tests for StorageService.delete_objects_by_prefix."""
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError
from app.api.services.storage import StorageService
from app.api.errors import StorageException

USER_ID = "abc123-user"


def _make_svc() -> StorageService:
    """StorageService with a fully mocked boto3 client."""
    settings = MagicMock()
    settings.spaces_bucket = "test-bucket"
    settings.spaces_endpoint = "https://sgp1.digitaloceanspaces.com"
    settings.spaces_region = "sgp1"
    settings.spaces_access_key = "key"
    settings.spaces_secret_key = "secret"
    with patch("app.api.services.storage.boto3"):
        svc = StorageService(settings)
    svc._client = MagicMock()
    return svc


def _make_paginator(pages: list[dict]) -> MagicMock:
    p = MagicMock()
    p.paginate.return_value = pages
    return p


def test_returns_deleted_count_on_success():
    svc = _make_svc()
    page = {"Contents": [
        {"Key": f"uploads/{USER_ID}/job1/f.jpg"},
        {"Key": f"uploads/{USER_ID}/job2/f.jpg"},
    ]}
    svc._client.get_paginator.return_value = _make_paginator([page])
    svc._client.delete_objects.return_value = {
        "Deleted": [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}, {"Key": f"uploads/{USER_ID}/job2/f.jpg"}],
        "Errors": [],
    }

    deleted, failed = svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)

    assert deleted == 2
    assert failed == 0


def test_skips_keys_not_containing_user_id():
    svc = _make_svc()
    page = {"Contents": [
        {"Key": f"uploads/{USER_ID}/job1/f.jpg"},
        {"Key": "uploads/other-user/job9/f.jpg"},   # should be skipped
    ]}
    svc._client.get_paginator.return_value = _make_paginator([page])
    svc._client.delete_objects.return_value = {
        "Deleted": [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}],
        "Errors": [],
    }

    deleted, failed = svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)

    assert deleted == 1
    assert failed == 0
    # Confirm only the valid key was sent to delete_objects
    sent_keys = svc._client.delete_objects.call_args.kwargs["Delete"]["Objects"]
    assert sent_keys == [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}]


def test_counts_batch_delete_errors_as_failed():
    svc = _make_svc()
    page = {"Contents": [
        {"Key": f"uploads/{USER_ID}/job1/f.jpg"},
        {"Key": f"uploads/{USER_ID}/job2/f.jpg"},
    ]}
    svc._client.get_paginator.return_value = _make_paginator([page])
    svc._client.delete_objects.return_value = {
        "Deleted": [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}],
        "Errors": [{"Key": f"uploads/{USER_ID}/job2/f.jpg", "Code": "AccessDenied"}],
    }

    deleted, failed = svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)

    assert deleted == 1
    assert failed == 1


def test_raises_storage_exception_on_paginator_failure():
    svc = _make_svc()
    paginator = MagicMock()
    paginator.paginate.side_effect = ClientError(
        {"Error": {"Code": "InternalError", "Message": "oops"}}, "ListObjectsV2"
    )
    svc._client.get_paginator.return_value = paginator

    with pytest.raises(StorageException):
        svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)


def test_returns_zero_zero_for_empty_prefix():
    svc = _make_svc()
    svc._client.get_paginator.return_value = _make_paginator([{"Contents": []}])

    deleted, failed = svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)

    assert deleted == 0
    assert failed == 0
    svc._client.delete_objects.assert_not_called()


def test_accumulates_counts_across_multiple_pages():
    svc = _make_svc()
    page1 = {"Contents": [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}]}
    page2 = {"Contents": [{"Key": f"uploads/{USER_ID}/job2/f.jpg"}]}
    svc._client.get_paginator.return_value = _make_paginator([page1, page2])
    svc._client.delete_objects.side_effect = [
        {"Deleted": [{"Key": f"uploads/{USER_ID}/job1/f.jpg"}], "Errors": []},
        {"Deleted": [{"Key": f"uploads/{USER_ID}/job2/f.jpg"}], "Errors": []},
    ]

    deleted, failed = svc.delete_objects_by_prefix(f"uploads/{USER_ID}/", USER_ID)

    assert deleted == 2
    assert failed == 0
    assert svc._client.delete_objects.call_count == 2
