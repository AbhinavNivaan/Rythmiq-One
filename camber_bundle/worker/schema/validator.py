"""
Schema validator and transformer.

Deterministic field mapping from normalized text to structured output.
No ML, no inference, no heuristics - only explicit rule-based mapping.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import unicodedata
import re

from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage


@dataclass(frozen=True)
class FieldRule:
    """
    Rule for mapping source fields to a target field.
    
    source_fields: Priority-ordered list of field names to search for
    required: If True, transformation fails if field not found
    """
    source_fields: tuple  # Immutable tuple instead of list
    required: bool = False
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "FieldRule":
        """Parse from JSON-compatible dict."""
        return FieldRule(
            source_fields=tuple(data.get("source_fields", [])),
            required=data.get("required", False)
        )


@dataclass(frozen=True)
class SchemaDefinition:
    """
    Schema definition with field mapping rules.
    
    Passed in job payload from API Gateway - never hardcoded.
    """
    name: str
    fields: Dict[str, FieldRule]  # target_field -> rule
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SchemaDefinition":
        """Parse from JSON-compatible dict."""
        if not isinstance(data, dict):
            raise ProcessingError(
                code=ErrorCode.SCHEMA_INVALID,
                stage=ProcessingStage.TRANSFORM,
                details={"reason": "schema_not_object"}
            )
        
        name = data.get("name", "")
        if not name:
            raise ProcessingError(
                code=ErrorCode.SCHEMA_INVALID,
                stage=ProcessingStage.TRANSFORM,
                details={"reason": "schema_name_missing"}
            )
        
        fields_data = data.get("fields", {})
        if not isinstance(fields_data, dict):
            raise ProcessingError(
                code=ErrorCode.SCHEMA_INVALID,
                stage=ProcessingStage.TRANSFORM,
                details={"reason": "fields_not_object"}
            )
        
        fields = {
            k: FieldRule.from_dict(v) 
            for k, v in fields_data.items()
        }
        
        return SchemaDefinition(name=name, fields=fields)


@dataclass
class TransformResult:
    """
    Result of schema transformation.
    
    Contains structured output, per-field confidence, and quality metrics.
    """
    structured: Dict[str, str]
    confidence: Dict[str, float]
    quality_score: float
    missing_fields: List[str] = field(default_factory=list)
    ambiguous_fields: List[str] = field(default_factory=list)


def normalize_text(text: str) -> str:
    """
    Apply Unicode NFC normalization and whitespace collapsing.
    
    Deterministic - same input always produces same output.
    """
    # Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)
    
    # Collapse whitespace
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    
    # Normalize line endings
    normalized = re.sub(r'\r\n?', '\n', normalized)
    
    # Collapse multiple newlines
    normalized = re.sub(r'\n\n+', '\n', normalized)
    
    return normalized.strip()


def extract_key_values(text: str) -> Dict[str, str]:
    """
    Extract key:value pairs from normalized text.
    
    Looks for patterns like "Invoice Number: 12345" or "Date: 2026-01-15"
    Keys are normalized to lowercase with underscores.
    """
    fields: Dict[str, str] = {}
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Look for colon-separated key:value
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip().lower()
                # Normalize key: remove special chars, replace spaces with underscores
                key = re.sub(r'[^a-z0-9\s]', '', key)
                key = re.sub(r'\s+', '_', key)
                
                value = parts[1].strip()
                
                if key and value:
                    # If key already exists, mark as ambiguous by keeping first value
                    # (ambiguity detection happens in transform)
                    if key not in fields:
                        fields[key] = value
    
    return fields


def transform(
    ocr_text: str,
    schema: SchemaDefinition
) -> TransformResult:
    """
    Transform OCR text to structured output according to schema.
    
    Args:
        ocr_text: Raw text from OCR
        schema: Schema definition with field mapping rules
        
    Returns:
        TransformResult with structured data
        
    Raises:
        ProcessingError: For missing required fields or ambiguity
    """
    try:
        # Step 1: Normalize text
        normalized = normalize_text(ocr_text)
        
        # Step 2: Extract key-value pairs
        extracted = extract_key_values(normalized)
        
    except Exception:
        raise ProcessingError(
            code=ErrorCode.NORMALIZE_FAILED,
            stage=ProcessingStage.NORMALIZE,
            details={"reason": "normalization_error"}
        )
    
    # Step 3: Apply schema field rules
    structured: Dict[str, str] = {}
    confidence: Dict[str, float] = {}
    missing_fields: List[str] = []
    ambiguous_fields: List[str] = []
    
    for target_field, rule in schema.fields.items():
        # Search for value in priority order
        found_values: List[str] = []
        
        for source_field in rule.source_fields:
            if source_field in extracted:
                found_values.append(extracted[source_field])
        
        if not found_values:
            # No value found
            if rule.required:
                missing_fields.append(target_field)
            confidence[target_field] = 0.0
        elif len(found_values) > 1:
            # Multiple values found - ambiguous
            if rule.required:
                ambiguous_fields.append(target_field)
            confidence[target_field] = 0.0
        else:
            # Exactly one value found
            structured[target_field] = found_values[0]
            confidence[target_field] = 1.0
    
    # Check for errors (fail fast)
    if missing_fields:
        raise ProcessingError(
            code=ErrorCode.MISSING_REQUIRED_FIELD,
            stage=ProcessingStage.TRANSFORM,
            details={"missing_fields": missing_fields}
        )
    
    if ambiguous_fields:
        raise ProcessingError(
            code=ErrorCode.AMBIGUOUS_FIELD,
            stage=ProcessingStage.TRANSFORM,
            details={"ambiguous_fields": ambiguous_fields}
        )
    
    # Calculate quality score (average confidence)
    if confidence:
        quality_score = sum(confidence.values()) / len(confidence)
    else:
        quality_score = 0.0
    
    return TransformResult(
        structured=structured,
        confidence=confidence,
        quality_score=round(quality_score, 2),
        missing_fields=missing_fields,
        ambiguous_fields=ambiguous_fields
    )
