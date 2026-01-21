/**
 * Text normalization for OCR output.
 * 
 * Deterministic transformations only - no heuristics or language detection.
 * Preserves character offsets for downstream traceability.
 */

/**
 * Character offset mapping from original to normalized text.
 */
export interface OffsetMap {
  /** Original position in source text */
  original: number;
  /** Position in normalized text */
  normalized: number;
}

/**
 * Text segment with type and boundaries.
 */
export interface TextSegment {
  /** Segment type */
  type: 'line' | 'paragraph' | 'whitespace';
  /** Content */
  text: string;
  /** Start offset in normalized text */
  start: number;
  /** End offset in normalized text */
  end: number;
  /** Start offset in original text */
  originalStart: number;
  /** End offset in original text */
  originalEnd: number;
}

/**
 * Normalization result with offset tracking.
 */
export interface NormalizedText {
  /** Normalized text */
  text: string;
  /** Offset mapping */
  offsetMap: OffsetMap[];
  /** Text segments */
  segments: TextSegment[];
}

/**
 * Normalization options.
 */
export interface NormalizeOptions {
  /** Unicode normalization form (default: NFC) */
  unicodeForm?: 'NFC' | 'NFD' | 'NFKC' | 'NFKD';
  /** Collapse consecutive whitespace (default: true) */
  collapseWhitespace?: boolean;
  /** Normalize line endings to \n (default: true) */
  normalizeLineEndings?: boolean;
  /** Trim leading/trailing whitespace (default: false) */
  trim?: boolean;
  /** Remove zero-width characters (default: true) */
  removeZeroWidth?: boolean;
}

/**
 * Zero-width and control characters to remove.
 */
const ZERO_WIDTH_CHARS = [
  '\u200B', // Zero-width space
  '\u200C', // Zero-width non-joiner
  '\u200D', // Zero-width joiner
  '\uFEFF', // Zero-width no-break space (BOM)
];

/**
 * Normalize text with offset tracking.
 */
export function normalizeText(
  text: string,
  options: NormalizeOptions = {}
): NormalizedText {
  const {
    unicodeForm = 'NFC',
    collapseWhitespace = true,
    normalizeLineEndings = true,
    trim = false,
    removeZeroWidth = true,
  } = options;

  let normalized = text;
  const offsetMap: OffsetMap[] = [];

  // Initialize 1:1 offset mapping
  for (let i = 0; i < text.length; i++) {
    offsetMap.push({ original: i, normalized: i });
  }

  // Step 1: Unicode normalization
  if (unicodeForm) {
    const result = applyUnicodeNormalization(normalized, offsetMap, unicodeForm);
    normalized = result.text;
  }

  // Step 2: Remove zero-width characters
  if (removeZeroWidth) {
    const result = removeZeroWidthChars(normalized, offsetMap);
    normalized = result.text;
  }

  // Step 3: Normalize line endings
  if (normalizeLineEndings) {
    const result = normalizeLineBreaks(normalized, offsetMap);
    normalized = result.text;
  }

  // Step 4: Collapse whitespace
  if (collapseWhitespace) {
    const result = collapseWhitespaceChars(normalized, offsetMap);
    normalized = result.text;
  }

  // Step 5: Trim
  if (trim) {
    const result = trimWhitespace(normalized, offsetMap);
    normalized = result.text;
  }

  // Step 6: Segment text
  const segments = segmentText(normalized, offsetMap);

  return {
    text: normalized,
    offsetMap,
    segments,
  };
}

/**
 * Apply unicode normalization and update offset map.
 */
function applyUnicodeNormalization(
  text: string,
  offsetMap: OffsetMap[],
  form: 'NFC' | 'NFD' | 'NFKC' | 'NFKD'
): { text: string; offsetMap: OffsetMap[] } {
  const normalized = text.normalize(form);

  // If length unchanged, no remapping needed
  if (normalized.length === text.length) {
    return { text: normalized, offsetMap };
  }

  // Rebuild offset map for character-level changes
  const newOffsetMap: OffsetMap[] = [];
  let normalizedIdx = 0;

  for (let originalIdx = 0; originalIdx < text.length; originalIdx++) {
    const char = text[originalIdx];
    const normalizedChar = char.normalize(form);

    // Map all positions in normalized form to original position
    for (let i = 0; i < normalizedChar.length; i++) {
      const originalPos = offsetMap[originalIdx]?.original ?? originalIdx;
      newOffsetMap.push({
        original: originalPos,
        normalized: normalizedIdx++,
      });
    }
  }

  return { text: normalized, offsetMap: newOffsetMap };
}

/**
 * Remove zero-width characters and update offset map.
 */
function removeZeroWidthChars(
  text: string,
  offsetMap: OffsetMap[]
): { text: string; offsetMap: OffsetMap[] } {
  const chars: string[] = [];
  const newOffsetMap: OffsetMap[] = [];

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (!ZERO_WIDTH_CHARS.includes(char)) {
      chars.push(char);
      newOffsetMap.push({
        original: offsetMap[i]?.original ?? i,
        normalized: chars.length - 1,
      });
    }
  }

  return { text: chars.join(''), offsetMap: newOffsetMap };
}

/**
 * Normalize line breaks to \n and update offset map.
 */
function normalizeLineBreaks(
  text: string,
  offsetMap: OffsetMap[]
): { text: string; offsetMap: OffsetMap[] } {
  const chars: string[] = [];
  const newOffsetMap: OffsetMap[] = [];
  let i = 0;

  while (i < text.length) {
    const char = text[i];
    const nextChar = text[i + 1];

    // Handle \r\n
    if (char === '\r' && nextChar === '\n') {
      chars.push('\n');
      newOffsetMap.push({
        original: offsetMap[i]?.original ?? i,
        normalized: chars.length - 1,
      });
      i += 2;
    }
    // Handle standalone \r
    else if (char === '\r') {
      chars.push('\n');
      newOffsetMap.push({
        original: offsetMap[i]?.original ?? i,
        normalized: chars.length - 1,
      });
      i++;
    }
    // Handle all other characters
    else {
      chars.push(char);
      newOffsetMap.push({
        original: offsetMap[i]?.original ?? i,
        normalized: chars.length - 1,
      });
      i++;
    }
  }

  return { text: chars.join(''), offsetMap: newOffsetMap };
}

/**
 * Collapse consecutive whitespace and update offset map.
 */
function collapseWhitespaceChars(
  text: string,
  offsetMap: OffsetMap[]
): { text: string; offsetMap: OffsetMap[] } {
  const chars: string[] = [];
  const newOffsetMap: OffsetMap[] = [];
  let inWhitespace = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const isWhitespace = char === ' ' || char === '\t';

    if (isWhitespace) {
      if (!inWhitespace) {
        chars.push(' ');
        newOffsetMap.push({
          original: offsetMap[i]?.original ?? i,
          normalized: chars.length - 1,
        });
        inWhitespace = true;
      }
      // Skip additional whitespace chars
    } else {
      chars.push(char);
      newOffsetMap.push({
        original: offsetMap[i]?.original ?? i,
        normalized: chars.length - 1,
      });
      inWhitespace = false;
    }
  }

  return { text: chars.join(''), offsetMap: newOffsetMap };
}

/**
 * Trim leading and trailing whitespace and update offset map.
 */
function trimWhitespace(
  text: string,
  offsetMap: OffsetMap[]
): { text: string; offsetMap: OffsetMap[] } {
  let start = 0;
  let end = text.length;

  // Find first non-whitespace
  while (start < text.length && /\s/.test(text[start])) {
    start++;
  }

  // Find last non-whitespace
  while (end > start && /\s/.test(text[end - 1])) {
    end--;
  }

  if (start === 0 && end === text.length) {
    return { text, offsetMap };
  }

  const trimmed = text.substring(start, end);
  const newOffsetMap = offsetMap.slice(start, end).map((entry, idx) => ({
    original: entry.original,
    normalized: idx,
  }));

  return { text: trimmed, offsetMap: newOffsetMap };
}

/**
 * Segment text into lines and paragraphs.
 */
function segmentText(text: string, offsetMap: OffsetMap[]): TextSegment[] {
  const segments: TextSegment[] = [];
  let currentStart = 0;
  let segmentType: 'line' | 'paragraph' | 'whitespace' = 'line';

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    // Single newline = line break
    if (char === '\n') {
      // Push current segment
      if (i > currentStart) {
        segments.push({
          type: segmentType,
          text: text.substring(currentStart, i),
          start: currentStart,
          end: i,
          originalStart: offsetMap[currentStart]?.original ?? currentStart,
          originalEnd: offsetMap[i - 1]?.original ?? i - 1,
        });
      }

      // Check for paragraph break (double newline)
      const nextChar = text[i + 1];
      if (nextChar === '\n') {
        // Skip consecutive newlines and mark as paragraph break
        let newlineEnd = i;
        while (newlineEnd < text.length && text[newlineEnd] === '\n') {
          newlineEnd++;
        }

        segments.push({
          type: 'paragraph',
          text: text.substring(i, newlineEnd),
          start: i,
          end: newlineEnd,
          originalStart: offsetMap[i]?.original ?? i,
          originalEnd: offsetMap[newlineEnd - 1]?.original ?? newlineEnd - 1,
        });

        i = newlineEnd - 1; // Continue after newlines
        currentStart = newlineEnd;
        segmentType = 'line';
      } else {
        // Single newline
        segments.push({
          type: 'whitespace',
          text: '\n',
          start: i,
          end: i + 1,
          originalStart: offsetMap[i]?.original ?? i,
          originalEnd: offsetMap[i]?.original ?? i,
        });

        currentStart = i + 1;
        segmentType = 'line';
      }
    }
  }

  // Push final segment
  if (currentStart < text.length) {
    segments.push({
      type: segmentType,
      text: text.substring(currentStart),
      start: currentStart,
      end: text.length,
      originalStart: offsetMap[currentStart]?.original ?? currentStart,
      originalEnd: offsetMap[text.length - 1]?.original ?? text.length - 1,
    });
  }

  return segments;
}

/**
 * Find original position for normalized position.
 */
export function getOriginalOffset(
  offsetMap: OffsetMap[],
  normalizedPos: number
): number {
  const entry = offsetMap.find((m) => m.normalized === normalizedPos);
  return entry?.original ?? normalizedPos;
}

/**
 * Find normalized position for original position.
 */
export function getNormalizedOffset(
  offsetMap: OffsetMap[],
  originalPos: number
): number {
  const entry = offsetMap.find((m) => m.original === originalPos);
  return entry?.normalized ?? originalPos;
}
