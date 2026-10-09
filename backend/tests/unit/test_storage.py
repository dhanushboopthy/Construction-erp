"""Storage adapters: the local folder and the S3-compatible bucket (with a stubbed client)."""

from io import BytesIO

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.services.storage import LocalStorage, S3Storage, StorageError


def test_local_storage_round_trip_and_traversal_guard(tmp_path):
    store = LocalStorage(tmp_path)
    store.put("closing/S1/2026/10/2026-10-09.pdf", b"%PDF-1")
    assert store.get("closing/S1/2026/10/2026-10-09.pdf") == b"%PDF-1"
    assert store.exists("closing/S1/2026/10/2026-10-09.pdf")
    assert not store.exists("closing/S1/2026/10/none.pdf")
    store.put("closing/S1/2026/10/2026-10-09.pdf", b"%PDF-2")  # a re-close replaces the file
    assert store.get("closing/S1/2026/10/2026-10-09.pdf") == b"%PDF-2"
    for bad in ("../outside.pdf", "a/../../outside.pdf", "/etc/passwd"):
        with pytest.raises(StorageError):
            store.put(bad, b"x")
    with pytest.raises(StorageError, match="missing"):
        store.get("nothing.pdf")
    assert list(tmp_path.glob("**/tmp*")) == []  # no temporary files are left behind


def client():
    return boto3.client(
        "s3",
        region_name="ap-south-1",
        aws_access_key_id="x",
        aws_secret_access_key="y",
        endpoint_url="http://localhost:9",
    )


def test_s3_put_get_exists_with_a_prefix():
    c = client()
    store = S3Storage(c, "shop-files", prefix="/erp/")
    with Stubber(c) as stub:
        stub.add_response(
            "put_object", {}, {"Bucket": "shop-files", "Key": "erp/closing/a.pdf", "Body": b"data"}
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(b"data"), 4)},
            {"Bucket": "shop-files", "Key": "erp/closing/a.pdf"},
        )
        stub.add_response("head_object", {}, {"Bucket": "shop-files", "Key": "erp/closing/a.pdf"})
        store.put("closing/a.pdf", b"data")
        assert store.get("closing/a.pdf") == b"data"
        assert store.exists("closing/a.pdf")


def test_s3_failures_become_storage_errors():
    c = client()
    store = S3Storage(c, "shop-files")
    with Stubber(c) as stub:
        stub.add_client_error("put_object", "AccessDenied", http_status_code=403)
        with pytest.raises(StorageError, match="did not accept"):
            store.put("a.pdf", b"x")
        stub.add_client_error("get_object", "NoSuchKey", http_status_code=404)
        with pytest.raises(StorageError, match="missing"):
            store.get("a.pdf")
        stub.add_client_error("get_object", "InternalError", http_status_code=500)
        with pytest.raises(StorageError, match="could not be read"):
            store.get("a.pdf")
        stub.add_client_error("head_object", "404", http_status_code=404)
        assert not store.exists("a.pdf")
        stub.add_client_error("head_object", "InternalError", http_status_code=500)
        with pytest.raises(StorageError):
            store.exists("a.pdf")
    for bad in ("../x", "/x", "a/../b"):
        with pytest.raises(StorageError):
            store.put(bad, b"x")


def test_s3_needs_a_bucket():
    from app.core.config import Settings, StorageProvider
    from app.services.storage import build_s3

    with pytest.raises(StorageError, match="S3_BUCKET"):
        build_s3(Settings(storage_provider=StorageProvider.S3))
    store = build_s3(
        Settings(
            storage_provider=StorageProvider.S3,
            s3_bucket="b",
            s3_access_key_id="k",
            s3_secret_access_key="s",
        )
    )
    assert isinstance(store, S3Storage)
