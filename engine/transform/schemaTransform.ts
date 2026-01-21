/**
 * Deterministic schema transformation for normalized text.
 * Maps text fields to schema fields via explicit rules.
 * No inference, ML, or guessing—only rule-based mapping.
 */

/**
 * Defines a rule for mapping normalized text field(s) to a schema field.
 */
export interface FieldRule {
  /** Source field names from normalized text to consume */
  sourceFields: string[];
  
  /** Optional deterministic transformation function */
  transform?: (values: string[]) => any;
  
  /** Whether this field must be present */
  required?: boolean;
  
  /** Confidence assigned when rule succeeds [0-1] */
  confidence?: number;
  
  /** Validation predicate (deterministic only) */
  validate?: (value: any) => boolean;
}

/**
 * Schema definition specifying target structure and mapping rules.
 */
export interface SchemaDefinition {
  /** Schema name */
  name: string;
  
  /** Field rules keyed by target field name */
  fields: Record<string, FieldRule>;
}

/**
 * Explicit outcome for schema transformation.
 */
export type TransformOutcome =
  | 'SUCCESS'
  | 'MISSING_REQUIRED_FIELD'
  | 'AMBIGUOUS_FIELD'
  | 'TRANSFORM_ERROR';

/**
 * Result of schema transformation.
 */
export interface TransformResult {
  /** Outcome classification for deterministic handling */
  outcome: TransformOutcome;

  /** Structured data conforming to schema */
  structured: Record<string, any>;
  
  /** Confidence score per field [0-1] */
  confidence: Record<string, number>;
  
  /** Required fields that were not mapped */
  missing: string[];
  
  /** Fields where mapping was ambiguous or conflicted */
  ambiguous: string[];

  /** Fields where a deterministic transform error occurred */
  errors: string[];
  
  /** Whether transformation succeeded (no errors, all required fields present) */
  success: boolean;
}

/**
 * Normalized text input (flat key-value structure).
 */
export interface NormalizedText {
  [key: string]: string | string[] | null | undefined;
}

type FieldApplicationResult =
  | { kind: 'APPLIED'; value: any; confidence: number; ambiguous: boolean }
  | { kind: 'SKIPPED_OPTIONAL'; ambiguous: boolean }
  | { kind: 'MISSING_REQUIRED_FIELD' }
  | { kind: 'AMBIGUOUS_REQUIRED' }
  | { kind: 'AMBIGUOUS_OPTIONAL' }
  | { kind: 'TRANSFORM_ERROR'; detail: string };

/**
 * Deterministic schema transformer.
 * Applies explicit rules to map normalized text fields to a target schema.
 */
export class SchemaTransformer {
  private schema: SchemaDefinition;
  private usedSourceFields: Set<string> = new Set();
  private ambiguousFields: Set<string> = new Set();

  constructor(schema: SchemaDefinition) {
    this.schema = schema;
  }

  /**
   * Transform normalized text to structured schema output.
   *
   * @param normalized - Normalized text with field values
   * @returns Transformation result with structured output, confidence, and metadata
   */
  public transform(normalized: NormalizedText): TransformResult {
    const structured: Record<string, any> = {};
    const confidence: Record<string, number> = {};
    const missing: string[] = [];
    const errors: string[] = [];
    const ambiguousRequired: string[] = [];

    this.usedSourceFields.clear();
    this.ambiguousFields.clear();

    // Process each target field according to its rule
    for (const [targetField, rule] of Object.entries(this.schema.fields)) {
      const result = this.applyRule(targetField, rule, normalized);

      switch (result.kind) {
        case 'APPLIED': {
          structured[targetField] = result.value;
          confidence[targetField] = result.confidence;
          if (result.ambiguous) {
            this.ambiguousFields.add(targetField);
          }
          break;
        }
        case 'AMBIGUOUS_REQUIRED': {
          this.ambiguousFields.add(targetField);
          ambiguousRequired.push(targetField);
          confidence[targetField] = 0;
          break;
        }
        case 'AMBIGUOUS_OPTIONAL': {
          this.ambiguousFields.add(targetField);
          confidence[targetField] = 0;
          break;
        }
        case 'MISSING_REQUIRED_FIELD': {
          missing.push(targetField);
          confidence[targetField] = 0;
          break;
        }
        case 'SKIPPED_OPTIONAL': {
          confidence[targetField] = 0;
          break;
        }
        case 'TRANSFORM_ERROR': {
          errors.push(targetField);
          confidence[targetField] = 0;
          break;
        }
      }
    }

    let outcome: TransformOutcome = 'SUCCESS';
    if (errors.length > 0) {
      outcome = 'TRANSFORM_ERROR';
    } else if (missing.length > 0) {
      outcome = 'MISSING_REQUIRED_FIELD';
    } else if (ambiguousRequired.length > 0) {
      outcome = 'AMBIGUOUS_FIELD';
    }

    const success = outcome === 'SUCCESS';

    return {
      outcome,
      structured,
      confidence,
      missing,
      ambiguous: Array.from(this.ambiguousFields),
      errors,
      success,
    };
  }

  /**
   * Apply a single field rule to normalized text.
   *
   * @param targetField - Target schema field name
   * @param rule - Mapping rule for this field
   * @param normalized - Normalized text input
   * @returns Result of rule application
   */
  private applyRule(
    _targetField: string,
    rule: FieldRule,
    normalized: NormalizedText
  ): FieldApplicationResult {
    // Collect source values
    const sourceValues: string[] = [];
    let allFieldsPresent = true;
    let anyFieldPresent = false;

    for (const sourceField of rule.sourceFields) {
      const value = normalized[sourceField];

      if (value === null || value === undefined || value === '') {
        allFieldsPresent = false;
        continue;
      }

      anyFieldPresent = true;
      this.usedSourceFields.add(sourceField);

      // Normalize to string array
      if (Array.isArray(value)) {
        sourceValues.push(...value.map(String));
      } else {
        sourceValues.push(String(value));
      }
    }

    // If no source fields present, rule cannot apply
    if (!anyFieldPresent) {
      return rule.required
        ? { kind: 'MISSING_REQUIRED_FIELD' }
        : { kind: 'SKIPPED_OPTIONAL', ambiguous: false };
    }

    const defaultConfidence = rule.confidence ?? 1.0;
    const finalConfidence = allFieldsPresent ? defaultConfidence : defaultConfidence * 0.5;

    // Detect ambiguity: multiple source values without explicit transform
    const ambiguousFromValues = !rule.transform && sourceValues.length > rule.sourceFields.length;

    // Apply transformation if provided
    let transformedValue: any;
    if (rule.transform) {
      try {
        transformedValue = rule.transform(sourceValues);
      } catch (err) {
        const detail = err instanceof Error ? err.message : 'transform threw';
        return { kind: 'TRANSFORM_ERROR', detail } as FieldApplicationResult;
      }
    } else {
      transformedValue =
        sourceValues.length === 1 ? sourceValues[0] : sourceValues.join(' ');
    }

    // Validate if validator provided
    if (rule.validate) {
      try {
        const isValid = rule.validate(transformedValue);
        if (!isValid) {
          return { kind: 'TRANSFORM_ERROR', detail: 'validation failed' } as FieldApplicationResult;
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message : 'validation threw';
        return { kind: 'TRANSFORM_ERROR', detail } as FieldApplicationResult;
      }
    }

    if (ambiguousFromValues) {
      return rule.required
        ? { kind: 'AMBIGUOUS_REQUIRED' }
        : { kind: 'AMBIGUOUS_OPTIONAL' };
    }

    return {
      kind: 'APPLIED',
      value: transformedValue,
      confidence: Math.max(0, Math.min(1, finalConfidence)), // Clamp to [0, 1]
      ambiguous: false,
    };
  }

  /**
   * Get the schema this transformer was initialized with.
   */
  public getSchema(): SchemaDefinition {
    return this.schema;
  }
}

/**
 * Helper to build a schema definition with common patterns.
 */
export class SchemaBuilder {
  private schema: SchemaDefinition;

  constructor(name: string) {
    this.schema = { name, fields: {} };
  }

  /**
   * Add a simple field that maps from a single source field.
   */
  public addField(targetName: string, sourceField: string, required = false): this {
    this.schema.fields[targetName] = {
      sourceFields: [sourceField],
      required,
      confidence: 1.0,
    };
    return this;
  }

  /**
   * Add a field with explicit rule.
   */
  public addRule(targetName: string, rule: FieldRule): this {
    this.schema.fields[targetName] = rule;
    return this;
  }

  /**
   * Add a composite field from multiple sources.
   */
  public addComposite(
    targetName: string,
    sourceFields: string[],
    transform: (values: string[]) => any,
    required = false
  ): this {
    this.schema.fields[targetName] = {
      sourceFields,
      transform,
      required,
      confidence: 1.0,
    };
    return this;
  }

  /**
   * Build and return the schema.
   */
  public build(): SchemaDefinition {
    return this.schema;
  }
}

/**
 * Utility to validate transformation results.
 */
export class TransformValidator {
  /**
   * Check if transformation succeeded (no missing required fields).
   */
  static isSuccessful(result: TransformResult): boolean {
    return result.outcome === 'SUCCESS';
  }

  /**
   * Get fields with confidence below threshold.
   */
  static getLowConfidenceFields(result: TransformResult, threshold = 0.5): string[] {
    return Object.entries(result.confidence)
      .filter(([_, conf]) => conf < threshold)
      .map(([field]) => field);
  }

  /**
   * Check for data quality issues.
   */
  static getQualityReport(result: TransformResult): {
    hasMissing: boolean;
    hasAmbiguous: boolean;
    hasLowConfidence: boolean;
    avgConfidence: number;
  } {
    const confidenceValues = Object.values(result.confidence);
    const avgConfidence =
      confidenceValues.length > 0
        ? confidenceValues.reduce((a, b) => a + b, 0) / confidenceValues.length
        : 0;

    return {
      hasMissing: result.missing.length > 0,
      hasAmbiguous: result.ambiguous.length > 0,
      hasLowConfidence: this.getLowConfidenceFields(result).length > 0,
      avgConfidence,
    };
  }
}
