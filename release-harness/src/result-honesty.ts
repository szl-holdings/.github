// SPDX-License-Identifier: Apache-2.0

const PLACEHOLDER = /\b(placeholder|lorem ipsum|coming soon|not implemented|dummy)\b/i;

export function assertRealAnswer(answer: string): void {
  const text = answer.trim();
  if (text.length < 24) {
    throw new Error(`result is too short to be real: ${text}`);
  }
  if (PLACEHOLDER.test(text)) {
    throw new Error('result is a placeholder');
  }
  if (/^(snapshot|stale)\b/i.test(text)) {
    throw new Error('result is a snapshot or stale stand-in');
  }
}
