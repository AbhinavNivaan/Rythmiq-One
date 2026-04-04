"""
Test suite for raw upload cleanup functionality.

Verifies that:
1. Raw uploads are deleted after processing (code verification)
2. Cleanup error handling is in place
3. WorkerSpacesClient has delete() method
"""

import pytest
import os
import sys


class TestRawUploadCleanupCodePresence:
    """Verify raw upload deletion is deferred to the API layer (not done in worker)."""

    def test_worker_does_not_call_storage_delete(self):
        """Verify worker.py does NOT call storage.delete — deletion is API-layer responsibility."""
        worker_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker', 'worker.py'
        )

        with open(worker_path) as f:
            worker_code = f.read()

        assert 'storage.delete(payload.input.raw_path)' not in worker_code, \
            "Worker must NOT delete the raw upload — deferred to API dismiss/feedback endpoints"

    def test_raw_upload_deleted_flag_kept_for_compatibility(self):
        """Verify raw_upload_deleted variable is still present (SuccessResult compatibility)."""
        worker_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker', 'worker.py'
        )

        with open(worker_path) as f:
            worker_code = f.read()

        assert 'raw_upload_deleted = False' in worker_code, \
            "raw_upload_deleted = False must remain for SuccessResult compatibility"

    def test_deferral_comment_present(self):
        """Verify the deferral comment is present to explain why deletion was removed."""
        worker_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker', 'worker.py'
        )

        with open(worker_path) as f:
            worker_code = f.read()

        assert 'deferred to the API layer' in worker_code, \
            "Comment explaining API-layer deferral not found in worker.py"
    
    def test_delete_method_in_spaces_client(self):
        """Verify delete() method exists in WorkerSpacesClient."""
        spaces_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker', 
            'storage', 'spaces_client.py'
        )
        
        with open(spaces_path) as f:
            spaces_code = f.read()
        
        assert 'def delete(self, path: str)' in spaces_code, \
            "delete() method not found in WorkerSpacesClient"
        
        # Verify uses boto3 delete_object
        delete_start = spaces_code.find('def delete(self, path: str)')
        delete_end = delete_start + 1000
        delete_section = spaces_code[delete_start:delete_end]
        
        assert 'delete_object' in delete_section, \
            "delete() should use boto3 delete_object()"
        assert 'self._client' in delete_section, \
            "delete() should use self._client"
    
    def test_delete_handles_nokey_error(self):
        """Verify delete() handles NoSuchKey gracefully."""
        spaces_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker',
            'storage', 'spaces_client.py'
        )
        
        with open(spaces_path) as f:
            spaces_code = f.read()
        
        delete_start = spaces_code.find('def delete(self, path: str)')
        delete_end = delete_start + 1100
        delete_section = spaces_code[delete_start:delete_end]
        
        assert 'NoSuchKey' in delete_section, \
            "NoSuchKey error handling not found"
        assert 'return False' in delete_section, \
            "Should return False on NoSuchKey (file already deleted)"


class TestRedactionCodePresence:
    """Verify log redaction code is present in API files."""
    
    def test_redacting_formatter_in_main(self):
        """Verify RedactingFormatter is integrated in main.py."""
        main_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'app', 'api', 'main.py'
        )
        
        with open(main_path) as f:
            main_code = f.read()
        
        assert 'RedactingFormatter' in main_code, \
            "RedactingFormatter import not found"
        assert 'setup_redacting_logger' in main_code, \
            "setup_redacting_logger call not found"
        assert 'Log redaction enabled' in main_code, \
            "Redaction confirmation message not found"
    
    def test_logging_utility_exists(self):
        """Verify logging utility module exists."""
        logging_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'app', 'api', 
            'utils', 'logging.py'
        )
        
        assert os.path.exists(logging_path), \
            "logging.py utility not found"
        
        with open(logging_path) as f:
            content = f.read()
        
        # Check for critical components
        assert 'class RedactingFormatter' in content, \
            "RedactingFormatter class not found"
        assert 'def redact_sensitive_data' in content, \
            "redact_sensitive_data function not found"
        assert 'def redact_dict' in content, \
            "redact_dict function not found"
        assert 'REDACT_PATTERNS' in content, \
            "Pattern definitions not found"
    
    def test_redacting_formatter_in_worker(self):
        """Verify RedactingFormatter is integrated in worker/server.py."""
        server_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'worker', 'server.py'
        )
        
        with open(server_path) as f:
            server_code = f.read()
        
        assert 'RedactingFormatter' in server_code, \
            "RedactingFormatter import not found in worker"
        assert 'setup_redacting_logger' in server_code, \
            "setup_redacting_logger call not found in worker"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
