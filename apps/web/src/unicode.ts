/**
 * Cross-language text offsets.
 *
 * Canonical InlineMark start/end values are Unicode code-point indexes
 * (Python 3 `str` offsets). JavaScript `String.slice` uses UTF-16 code units,
 * so non-BMP characters (mathematical letters, supplementary CJK) must be
 * sliced via code-point iteration.
 */

export function codePointLength(text: string): number {
  return [...text].length;
}

export function sliceByCodePoint(text: string, start: number, end: number): string {
  return [...text].slice(start, end).join("");
}

export function codePointSliceOrOutOfRange(text: string, start: number, end: number): string {
  const length = codePointLength(text);
  if (start >= 0 && end >= start && end <= length) {
    return sliceByCodePoint(text, start, end);
  }
  return "mark out of range";
}
