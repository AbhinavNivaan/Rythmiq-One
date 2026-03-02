# Red Team Security Audit - Remediation Guide

## Critical Issues - Action Items

### CRITICAL-001: Nonce Not Stored With Encrypted File
**Impact:** Data may become unrecoverable if database record is lost  
**Fix Complexity:** Medium  
**Estimated Time:** 4-6 hours

#### Recommended Solution
Prepend 12-byte nonce to ciphertext before storage. This keeps nonce and encrypted data atomic.

#### Code Changes Required

**File:** `app/api/crypto/encryption.py`
```python
# Add new function
def encrypt_file_with_nonce(plaintext: bytes, sek: bytes) -> bytes:
    """
    Encrypt file with nonce prepended to ciphertext.
    
    Format: [12-byte nonce][ciphertext + 16-byte tag]
    
    Args:
        plaintext: Raw file bytes
        sek: 32-byte Storage Encryption Key
        
    Returns:
        Encrypted data with prepended nonce (12 + len(plaintext) + 16 bytes)
    """
    nonce = os.urandom(NONCE_SIZE)
    cipher = AESGCM(sek)
    ciphertext = cipher.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext  # ← Prepend nonce


def decrypt_file_with_nonce(encrypted_data: bytes, sek: bytes) -> bytes:
    """
    Decrypt file with nonce prepended to ciphertext.
    
    Args:
        encrypted_data: [12-byte nonce][ciphertext + tag]
        sek: 32-byte Storage Encryption Key
        
    Returns:
        Plaintext bytes
        
    Raises:
        InvalidTag: If file was tampered with
    """
    if len(encrypted_data) < NONCE_SIZE + 16:
        raise ValueError(f"Encrypted data too short (min {NONCE_SIZE + 16} bytes)")
    
    nonce = encrypted_data[:NONCE_SIZE]
    ciphertext = encrypted_data[NONCE_SIZE:]
    
    cipher = AESGCM(sek)
    return cipher.decrypt(nonce, ciphertext, associated_data=None)
```

**File:** `worker/crypto.py` (match implementation)
```python
# Apply same changes
```

**File:** `worker/worker.py` - Update encryption call
```python
# Before:
# ciphertext, nonce = crypto_encrypt(upload_data, sek)
# upload_data = ciphertext
# encryption_nonce_b64 = nonce_to_base64(nonce)

# After:
upload_data = crypto_encrypt_with_nonce(upload_data, sek)  # Returns nonce + ciphertext
is_encrypted = True
# No need to separately track nonce - it's in the encrypted data

# Simpler artifacts output
artifacts=Artifacts(
    ...,
    encrypted=is_encrypted,
    encryption_nonce=None,  # Or remove this field
    master_path=master_path,
)
```

**File:** `app/api/services/packaging.py` - Update decryption
```python
# Before:
# nonce = nonce_from_base64(encryption_info[path])
# content = decrypt_file(content, nonce, sek)

# After:
content = decrypt_file_with_nonce(content, sek)  # Nonce extracted internally
```

**File:** `db/migrations/005_update_encryption_nonce_handling.sql`
```sql
-- Deprecate encryption_nonce column (but keep for migration)
-- Since nonce is now in the encrypted file, database doesn't need to store it
-- This migration is optional - keeping column doesn't hurt for backward compatibility

-- No schema changes required if we keep extra column for legacy data
```

#### Testing Checklist
- [ ] Encrypt/decrypt roundtrip with nonce prepended
- [ ] Verify nonce extraction works correctly
- [ ] Verify old encrypted files (nonce in DB) still decrypt correctly
- [ ] Verify backwards compatibility during transition

---

### CRITICAL-002: SEK Exposed in Job Payload Logging
**Impact:** SEK could be exposed in application logs  
**Fix Complexity:** Low  
**Estimated Time:** 2-3 hours

#### Recommended Solution
Implement logging redaction filter to mask sensitive fields.

**File:** `app/api/config.py` (logging configuration)
```python
import logging
import re

class SensitiveDataRedactionFilter(logging.Filter):
    """Redact sensitive data from log records."""
    
    SENSITIVE_PATTERNS = {
        'sek_b64': r'sek_b64["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        'storage_encryption_key': r'storage_encryption_key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        'password': r'password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        'token': r'token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
        'refresh_token': r'refresh_token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)',
    }
    
    SENSITIVE_FIELDS = {
        'sek_b64', 'storage_encryption_key', 'password', 'token', 'refresh_token',
        'authorization', 'access_token'
    }
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive fields from log record."""
        
        # Redact message
        if record.msg:
            msg = str(record.msg)
            for field, pattern in self.SENSITIVE_PATTERNS.items():
                msg = re.sub(pattern, f'{field}="[REDACTED]"', msg, flags=re.IGNORECASE)
            record.msg = msg
        
        # Redact extra fields
        if hasattr(record, '__dict__'):
            for key in list(record.__dict__.keys()):
                if key in self.SENSITIVE_FIELDS:
                    record.__dict__[key] = "[REDACTED]"
        
        return True


def configure_logging():
    """Configure logging with redaction."""
    logger = logging.getLogger()
    
    # Add redaction filter to all handlers
    redaction_filter = SensitiveDataRedactionFilter()
    for handler in logger.handlers:
        handler.addFilter(redaction_filter)
```

**File:** `app/api/main.py` (application startup)
```python
# In create_app() or app setup:
from app.api.config import configure_logging

configure_logging()  # Apply redaction filters
```

#### Testing Checklist
- [ ] Log a message with sek_b64 - verify it's redacted
- [ ] Log a message with password - verify it's redacted
- [ ] Log a message with token - verify it's redacted
- [ ] Verify normal logs still appear and are readable

---

### CRITICAL-003: Raw Upload Not Deleted After Processing
**Impact:** Plaintext files permanently stored in bucket  
**Fix Complexity:** Medium  
**Estimated Time:** 3-4 hours

#### Recommended Solution
Delete raw upload after successful encryption and storage of master file.

**File:** `worker/worker.py` - Add cleanup in process_job
```python
def process_job(payload: JobPayload) -> SuccessResult:
    """...[existing docstring]..."""
    start_time = time.time()
    warnings: List[str] = []
    
    # Create storage client
    storage = create_client_from_spec(...)
    
    # Stage 1: FETCH
    raw_data = storage.download(...)
    
    # ... processing stages ...
    
    # Stage 7: UPLOAD
    master_path = storage.upload_master(
        data=upload_data,
        user_id=payload.user_id,
        job_id=payload.job_id,
    )
    
    preview_path = storage.upload_preview(...)
    
    # Stage 8: CLEANUP - Delete raw upload after successful encryption
    raw_upload_deleted = False
    if payload.input.raw_path:  # Only if using direct path (not signed URL)
        try:
            storage.delete_object(payload.input.raw_path)
            logger.info(f"Cleaned up raw upload: {payload.input.raw_path}")
            raw_upload_deleted = True
        except Exception as e:
            logger.warning(
                f"Failed to cleanup raw upload: {e}",
                extra={"raw_path": payload.input.raw_path}
            )
            warnings.append(f"Failed to cleanup raw upload: {str(e)}")
            # Non-fatal: continue
    
    # Clean up sensitive data from memory
    del upload_data, final_image_data, raw_data
    
    # Calculate processing time
    processing_ms = int((time.time() - start_time) * 1000)
    
    return SuccessResult(
        job_id=payload.job_id,
        processing_ms=processing_ms,
        messages=warnings,
        artifacts=Artifacts(
            ...,
            raw_upload_deleted=raw_upload_deleted,  # Track in result
        ),
    )
```

**File:** `worker/storage/spaces_client.py` - Add delete_object method
```python
def delete_object(self, path: str) -> None:
    """
    Delete an object from Spaces.
    
    Args:
        path: Storage path (e.g., raw/{user_id}/{job_id}/file.jpg)
        
    Raises:
        WorkerError: If deletion fails
    """
    try:
        self._client.delete_object(
            Bucket=self._config.bucket,
            Key=path,
        )
        logger.info(f"Deleted object: {path}")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        
        if error_code == 'NoSuchKey':
            # Object already deleted or doesn't exist - not an error
            logger.warning(f"Object not found (already deleted?): {path}")
            return
        
        raise upload_failed(f"Failed to delete object ({error_code}): {str(e)}")
    except Exception as e:
        raise upload_failed(f"Unexpected error deleting object: {str(e)}")
```

#### Testing Checklist
- [ ] Upload document → Raw file created
- [ ] Process job → Encryption succeeds
- [ ] Verify raw file deleted from storage
- [ ] Verify master file still exists and is encrypted
- [ ] Test cleanup failure handling (non-fatal)
- [ ] Verify cleanup doesn't run for signed URL uploads (external storage)

---

## High-Risk Issues - Action Items

### HIGH-001: SEK Availability Not Communicated to Client
**Impact:** User doesn't know if documents are encrypted  
**Fix Complexity:** Low  
**Estimated Time:** 1-2 hours

**File:** `app/api/routes/auth.py` - Update SessionResponse
```python
class SessionResponse(BaseModel):
    user_id: str
    email: str | None
    expires_at: int
    has_sek: bool = False  # ← Add this field


@router.get("/session", response_model=SessionResponse)
async def get_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """
    Validate current session and return user info.
    
    Includes: has_sek - whether user's documents will be encrypted
    """
    db = get_db_client()
    
    # Check if user has SEK
    user_result = (
        db.table("users")
        .select("storage_encryption_key")
        .eq("id", str(user.id))
        .limit(1)
        .execute()
    )
    
    has_sek = bool(
        user_result.data 
        and user_result.data[0].get("storage_encryption_key")
    )
    
    return SessionResponse(
        user_id=str(user.id),
        email=user.email,
        expires_at=user.exp,
        has_sek=has_sek,
    )
```

**Frontend:** Use this to warn users
```typescript
useEffect(() => {
    if (sessionData && !sessionData.has_sek) {
        showAlert({
            type: 'warning',
            title: 'Encryption Not Active',
            message: 'Your documents will not be encrypted. Contact support to enable encryption.',
        });
    }
}, [sessionData]);
```

---

### HIGH-002: No Rate Limiting on Auth Endpoints
**Impact:** Brute force attacks possible  
**Fix Complexity:** Medium  
**Estimated Time:** 2-3 hours

**File:** `app/api/config.py` - Add rate limiting config
```python
# Rate limiting configuration
RATE_LIMIT_LOGIN = "5/minute"         # 5 login attempts per minute per IP
RATE_LIMIT_SIGNUP = "3/minute"        # 3 signups per minute per IP
RATE_LIMIT_REFRESH = "10/minute"      # 10 refresh attempts per minute per IP
RATE_LIMIT_DEFAULT = "100/minute"     # Default rate limit
```

**File:** `app/api/main.py` - Configure rate limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please try again later.",
        },
    )
```

**File:** `app/api/routes/auth.py` - Apply rate limits
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

@router.post("/signup", response_model=AuthResponse)
@limiter.limit("3/minute")  # 3 signups per minute per IP
async def signup(request: Request, request_body: SignUpRequest, ...):
    ...


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")  # 5 login attempts per minute per IP
async def login(request: Request, request_body: LoginRequest, ...):
    ...


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit("10/minute")  # 10 refresh attempts per minute per IP
async def refresh_token(request: Request, request_body: RefreshRequest, ...):
    ...
```

#### Testing Checklist
- [ ] Make 5 login attempts in 1 minute → 6th request gets 429
- [ ] Wait 1 minute, can login again
- [ ] Test signup rate limit (3/minute)
- [ ] Test refresh rate limit (10/minute)
- [ ] Verify different IPs have separate limits

---

### HIGH-003: Encryption Failure Fallback to Unencrypted
**Impact:** Documents uploaded unencrypted despite having SEK  
**Fix Complexity:** Low  
**Estimated Time:** 1 hour

**File:** `worker/worker.py` - Fail if SEK not provided for new users
```python
# Stage 6: ENCRYPT
upload_data = schema_result.image_data
is_encrypted = False
encryption_nonce_b64: str | None = None

if payload.sek_b64:
    try:
        sek = sek_from_base64(payload.sek_b64)
        ciphertext, nonce = crypto_encrypt(upload_data, sek)
        upload_data = ciphertext
        encryption_nonce_b64 = nonce_to_base64(nonce)
        is_encrypted = True
        logger.info("Output encrypted with AES-256-GCM")
        del sek
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise WorkerError(
            code=ErrorCode.UPLOAD_FAILED,
            stage=ProcessingStage.UPLOAD,
            message=f"Encryption failed: {str(e)}",
        )
else:
    # NEW: Fail if SEK is expected but not provided
    logger.error("No SEK provided - encryption required for current users")
    raise WorkerError(
        code=ErrorCode.MISSING_ENCRYPTION_KEY,  # Add to ErrorCode enum
        stage=ProcessingStage.ENCRYPT,
        message="User encryption key not found. Contact support.",
    )
```

**File:** `worker/errors.py` - Add new error code
```python
class ErrorCode(str, Enum):
    """...[existing codes]..."""
    MISSING_ENCRYPTION_KEY = "MISSING_ENCRYPTION_KEY"
```

---

### HIGH-004: Nonce Not Validated on Decryption Input
**Impact:** Corrupted nonce could cause silent failures  
**Fix Complexity:** Low  
**Estimated Time:** 1-2 hours

**File:** `app/api/crypto/encryption.py` - Add validation
```python
def decrypt_file(ciphertext: bytes, nonce: bytes, sek: bytes) -> bytes:
    """
    Decrypt file with AES-256-GCM.

    Args:
        ciphertext: Encrypted bytes (includes auth tag)
        nonce: 12-byte nonce
        sek: 32-byte Storage Encryption Key

    Returns:
        Plaintext bytes

    Raises:
        ValueError: If inputs are invalid
        cryptography.exceptions.InvalidTag: If file was tampered with
    """
    # Validate input sizes
    if not isinstance(ciphertext, bytes):
        raise TypeError("Ciphertext must be bytes")
    if len(nonce) != NONCE_SIZE:
        raise ValueError(f"Nonce must be {NONCE_SIZE} bytes, got {len(nonce)}")
    if len(sek) != SEK_SIZE:
        raise ValueError(f"SEK must be {SEK_SIZE} bytes, got {len(sek)}")
    if len(ciphertext) < 16:  # Minimum: 16-byte tag
        raise ValueError(f"Ciphertext too short: {len(ciphertext)} bytes (min 16)")

    cipher = AESGCM(sek)

    try:
        plaintext = cipher.decrypt(nonce, ciphertext, associated_data=None)
    except Exception as e:
        # Wrap cryptographic exceptions for clarity
        if "InvalidTag" in type(e).__name__:
            raise
        raise ValueError(f"Decryption failed: {type(e).__name__}: {str(e)}")

    return plaintext
```

**File:** `app/api/services/packaging.py` - Use validated decryption
```python
if path in encryption_info and sek_b64:
    try:
        sek = sek_from_base64(sek_b64)
        nonce = nonce_from_base64(encryption_info[path])
        
        # Validation happens in decrypt_file()
        content = decrypt_file(content, nonce, sek)
        del sek
    except ValueError as e:
        logger.error(
            "Invalid decryption inputs",
            extra={"job_id": str(job_id), "path": path, "error": str(e)},
        )
        raise PackagingException(f"Cannot decrypt file: {str(e)}")
    except Exception as e:
        logger.error(
            "Failed to decrypt artifact for packaging",
            extra={"job_id": str(job_id), "path": path, "error": str(e)},
        )
        raise PackagingException(f"Decryption error: {str(e)}")
```

---

## Implementation Priority

### Phase 1: Critical Issues (1-2 weeks)
1. ✅ CRITICAL-003: Delete raw uploads
2. ✅ CRITICAL-002: Add logging redaction
3. ✅ CRITICAL-001: Nonce in encrypted file (more complex)

### Phase 2: High-Risk Issues (1 week)
1. ✅ HIGH-002: Rate limiting
2. ✅ HIGH-001: SEK availability indicator
3. ✅ HIGH-003: Fail on missing SEK
4. ✅ HIGH-004: Input validation

### Phase 3: Medium-Risk Issues (2 weeks)
1. Encrypt preview images
2. Implement CORS configuration
3. Reduce download URL expiration
4. Add secret deletion library

---

## Testing Strategy

### Unit Tests (Per Fix)
- Decrypt with new nonce-prepended format
- Verify logging redaction
- Test storage cleanup

### Integration Tests
- End-to-end encryption/decryption
- Multi-user isolation
- Rate limiting

### Security Tests
- Attempt to brute force login
- Attempt to access other user's data
- Verify raw uploads are deleted
- Verify logs don't contain SEK

---

## Rollout Plan

1. **Code Review:** All fixes reviewed by 2+ security engineers
2. **Testing:** Run full test suite + security tests
3. **Staging:** Deploy to staging, monitor logs for issues
4. **Canary:** Deploy to 5% production traffic
5. **Production:** Full rollout with monitoring

---

**Prepared by:** Red Team Security  
**Date:** February 18, 2026

