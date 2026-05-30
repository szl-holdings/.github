/**
 * doctrine_v7_checker.ts
 * a11oy TypeScript checker — SZL Doctrine v7 compliance scanner
 *
 * Scans markdown files for v7 violations and emits a DSSE receipt per file.
 *
 * Usage:
 *   npx ts-node doctrine_v7_checker.ts [--dir <path>] [--canonical <path>] [--output <path>]
 *
 * Output:
 *   One DSSE receipt JSON file per scanned markdown file, written to <output>/.
 *   A SUMMARY.json aggregating all violations.
 *
 * Doctrine reference: /home/user/workspace/szl/audit_2026-05-29_evening/doctrine_v7/DOCTRINE_V7.md
 * Session: 2026-05-29 evening audit
 *
 * No emoji in file-level comments per §6.
 */

import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViolationCode =
  | "SUPERLATIVE"        // §1
  | "BADGE_UNSCOPED"     // §10 / §2
  | "STALE_CANONICAL"    // §11
  | "OUTRIGHT_CLAIM"     // §12
  | "ARTIFACT_NO_URL"    // §13
  | "DOI_UNRESOLVED"     // §9
  | "EMOJI_IN_HEADER"    // §6
  | "UNCITED_CLAIM"      // §7
  | "NO_LINEAGE_TAG"     // §8
  | "MISSING_ORCHESTRATOR_TAG"  // §14
  | "INVARIANT_LOW_CORPORA"     // §15
  | "PROTECTION_TOGGLE_NO_HUMAN"; // §16

interface Violation {
  code: ViolationCode;
  clause: string;
  line: number;
  column?: number;
  text: string;
  suggestion: string;
}

interface DSSEPayload {
  _type: "https://szl.holdings/governance/DoctrineV7Receipt";
  subject: {
    name: string;
    sha256: string;
  };
  scanned_at: string;  // ISO 8601
  doctrine_version: "v7";
  violations: Violation[];
  pass: boolean;
  violation_count: number;
  receipt_id: string;
}

interface DSSEEnvelope {
  payload: string;         // base64url(JSON(DSSEPayload))
  payloadType: string;
  signatures: Array<{     // stubbed — production would use actual signing
    sig: string;
    keyid: string;
  }>;
}

interface CanonicalNumbers {
  [key: string]: {
    value: string;
    propagation_targets: string[];
    updated_at: string;
  };
}

// ---------------------------------------------------------------------------
// §1 — Superlative checker
// ---------------------------------------------------------------------------

const SUPERLATIVE_TERMS: string[] = [
  "revolutionary",
  "unprecedented",
  "world-class",
  "seamless",
  "industry-leading",
  "cutting-edge",
  "game-changing",
  "breakthrough",
];

// Only flag "first" and "only" when NOT followed by a citation within 5 lines
const CITATION_SENSITIVE_TERMS: string[] = ["first", "only"];

function checkSuperlatives(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const lower = line.toLowerCase();
    for (const term of SUPERLATIVE_TERMS) {
      if (lower.includes(term)) {
        // Check for citation within 5 lines (simple heuristic: look for http or doi)
        const window = lines.slice(idx, Math.min(idx + 5, lines.length)).join(" ");
        const hasCitation = /https?:\/\/|doi\.org|10\.\d{4,}/.test(window);
        if (!hasCitation) {
          violations.push({
            code: "SUPERLATIVE",
            clause: "§1",
            line: idx + 1,
            text: line.trim().substring(0, 100),
            suggestion: `Remove "${term}" or add an adjacent citation (URL or DOI) within 5 lines.`,
          });
        }
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §6 — Emoji in level-2/3 headers
// ---------------------------------------------------------------------------

const HEADER_PATTERN = /^(#{2,3})\s+(.*)/;
// Non-ASCII detection (proxy for emoji)
const NON_ASCII_PATTERN = /[^\x00-\x7F]/;

function checkEmojiInHeaders(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const match = HEADER_PATTERN.exec(line);
    if (match && NON_ASCII_PATTERN.test(match[2])) {
      violations.push({
        code: "EMOJI_IN_HEADER",
        clause: "§6",
        line: idx + 1,
        text: line.trim().substring(0, 120),
        suggestion: "Remove all non-ASCII characters (including emoji) from ## and ### headers.",
      });
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §9 — DOI dereferencing (concept-DOI alias detection)
// ---------------------------------------------------------------------------

// Known concept-DOI aliases from tonight's audit
const KNOWN_CONCEPT_ALIASES: string[] = [
  "10.5281/zenodo.19944926",
];

const DOI_PATTERN = /10\.\d{4,}\/\S+/g;
const CONCEPT_ALIAS_LABEL_PATTERN = /\[concept-DOI-alias\]/;

function checkDOIDereferencing(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const matches = line.matchAll(DOI_PATTERN);
    for (const match of matches) {
      const doi = match[0].replace(/[.,;)\]]+$/, ""); // strip trailing punctuation
      if (KNOWN_CONCEPT_ALIASES.includes(doi)) {
        // Check for label within 2 lines
        const window = lines.slice(Math.max(0, idx - 1), Math.min(idx + 3, lines.length)).join(" ");
        if (!CONCEPT_ALIAS_LABEL_PATTERN.test(window)) {
          violations.push({
            code: "DOI_UNRESOLVED",
            clause: "§9",
            line: idx + 1,
            text: line.trim().substring(0, 120),
            suggestion: `DOI ${doi} is a concept-DOI alias. Add [concept-DOI-alias] annotation adjacent to this citation.`,
          });
        }
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §10 — Version-scoped badges
// ---------------------------------------------------------------------------

const BADGE_PATTERN = /!\[.*?\]\(https?:\/\/[^)]*(?:badge|shield|passing|green|status)[^)]*\)/gi;
const VERSION_ANCHOR_PATTERN = /\(as of [0-9a-f]{7,40}|as of v\d+\.\d+/i;

function checkBadgeScoping(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const matches = line.matchAll(BADGE_PATTERN);
    for (const match of matches) {
      // Check the badge URL itself and the 10 lines following
      const window = lines.slice(idx, Math.min(idx + 10, lines.length)).join(" ");
      if (!VERSION_ANCHOR_PATTERN.test(window)) {
        violations.push({
          code: "BADGE_UNSCOPED",
          clause: "§10 / §2",
          line: idx + 1,
          text: match[0].substring(0, 120),
          suggestion: 'Add version anchor "(as of <commit-sha>)" or "(as of v<semver>)" within 10 lines of this badge.',
        });
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §11 — Canonical-number propagation (compared against canonical_numbers.json)
// ---------------------------------------------------------------------------

function checkCanonicalNumbers(
  lines: string[],
  filePath: string,
  canonicals: CanonicalNumbers
): Violation[] {
  const violations: Violation[] = [];
  const content = lines.join("\n");

  for (const [key, entry] of Object.entries(canonicals)) {
    // Only check files that are in the propagation target list
    const isTarget = entry.propagation_targets.some((t) =>
      filePath.endsWith(t) || filePath.includes(t)
    );
    if (!isTarget) continue;

    // Look for a stale numeric value pattern (naive substring search)
    // In production: use structured numeric extraction
    if (content.includes(key) && !content.includes(entry.value)) {
      violations.push({
        code: "STALE_CANONICAL",
        clause: "§11",
        line: 0, // file-level violation; no single line
        text: `Canonical key "${key}" expected value "${entry.value}" not found in file.`,
        suggestion: `Update this file to reflect the current canonical value for "${key}": ${entry.value}`,
      });
    }
  }
  return violations;
}

// ---------------------------------------------------------------------------
// §12 — Staged-advisory language for unverified claims
// ---------------------------------------------------------------------------

const OUTRIGHT_CLAIM_TERMS: RegExp[] = [
  /catalog-grade/i,
  /SLSA[- ]compliant/i,
  /production-ready/i,
  /air-gap-ready/i,
  /catalog[- ]ready/i,
];

const STAGED_ADVISORY_PREFIXES: RegExp[] = [
  /STAGED-ADVISORY:/i,
  /claimed \(unverified\):/i,
  /target \(not yet achieved\):/i,
];

const ARTIFACT_URL_PATTERN = /https?:\/\/(?:github\.com|ghcr\.io|huggingface\.co|zenodo\.org)/;

function checkStagedAdvisory(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    for (const term of OUTRIGHT_CLAIM_TERMS) {
      if (term.test(line)) {
        // Check for staged-advisory prefix in window [-1, +1]
        const window = lines.slice(Math.max(0, idx - 1), Math.min(idx + 2, lines.length)).join(" ");
        const hasStagedAdvisory = STAGED_ADVISORY_PREFIXES.some((p) => p.test(window));
        const hasArtifactURL = ARTIFACT_URL_PATTERN.test(window);
        if (!hasStagedAdvisory && !hasArtifactURL) {
          violations.push({
            code: "OUTRIGHT_CLAIM",
            clause: "§12",
            line: idx + 1,
            text: line.trim().substring(0, 120),
            suggestion: `Prefix with "STAGED-ADVISORY:" or add a verifiable artifact URL (github.com, ghcr.io, zenodo.org).`,
          });
        }
        break;
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §13 — Artifact claims require verifiable URLs
// ---------------------------------------------------------------------------

const ARTIFACT_IDENTIFIER_PATTERN =
  /ghcr\.io\/[^\s)]+|(?:v\d+\.\d+\.\d+-[^\s)]+\.tar\.zst|\.sig|\.sha256|\.pub)\b/g;

function checkArtifactURLs(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const matches = line.matchAll(ARTIFACT_IDENTIFIER_PATTERN);
    for (const match of matches) {
      // Check for adjacent URL in the same line or within 2 lines
      const window = lines.slice(Math.max(0, idx - 1), Math.min(idx + 3, lines.length)).join(" ");
      const hasURL = /https?:\/\//.test(window);
      if (!hasURL) {
        violations.push({
          code: "ARTIFACT_NO_URL",
          clause: "§13",
          line: idx + 1,
          text: line.trim().substring(0, 120),
          suggestion: `Add a verifiable URL for artifact "${match[0]}" in the same sentence or footnote.`,
        });
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// §7 — Uncited numeric claims
// ---------------------------------------------------------------------------

// Heuristic: percentages and counts in prose without adjacent citation
const NUMERIC_CLAIM_PATTERN = /\b\d+(?:\.\d+)?%|\b\d{2,}(?:\s+(?:files|assets|datasets|declarations|sorries|tools|problems))/g;
const CITATION_NEARBY_PATTERN = /https?:\/\/|doi\.org|10\.\d{4,}|\(.*\d{4}.*\)/;

function checkUncitedClaims(lines: string[]): Violation[] {
  const violations: Violation[] = [];
  lines.forEach((line, idx) => {
    const matches = line.matchAll(NUMERIC_CLAIM_PATTERN);
    for (const match of matches) {
      const window = lines.slice(Math.max(0, idx - 2), Math.min(idx + 3, lines.length)).join(" ");
      if (!CITATION_NEARBY_PATTERN.test(window)) {
        violations.push({
          code: "UNCITED_CLAIM",
          clause: "§7",
          line: idx + 1,
          text: line.trim().substring(0, 120),
          suggestion: `Add a citation (URL, DOI, or artifact path) near the numeric claim "${match[0]}".`,
        });
      }
    }
  });
  return violations;
}

// ---------------------------------------------------------------------------
// DSSE receipt builder
// ---------------------------------------------------------------------------

function sha256Hex(content: string): string {
  return crypto.createHash("sha256").update(content, "utf8").digest("hex");
}

function buildDSSEReceipt(
  filePath: string,
  fileContent: string,
  violations: Violation[]
): DSSEEnvelope {
  const payload: DSSEPayload = {
    _type: "https://szl.holdings/governance/DoctrineV7Receipt",
    subject: {
      name: path.basename(filePath),
      sha256: sha256Hex(fileContent),
    },
    scanned_at: new Date().toISOString(),
    doctrine_version: "v7",
    violations,
    pass: violations.length === 0,
    violation_count: violations.length,
    receipt_id: crypto.randomUUID(),
  };

  const payloadJSON = JSON.stringify(payload, null, 2);
  const payloadB64 = Buffer.from(payloadJSON).toString("base64url");

  return {
    payload: payloadB64,
    payloadType: "application/vnd.szl.governance.v7+json",
    signatures: [
      {
        // Stub signature — production uses cosign or sigstore keyless
        sig: "STUB_SIG_" + sha256Hex(payloadJSON).substring(0, 16),
        keyid: "szl-doctrine-v7-checker",
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Main scanner
// ---------------------------------------------------------------------------

interface ScanOptions {
  dir: string;
  canonicalPath?: string;
  outputDir: string;
}

async function scanDirectory(opts: ScanOptions): Promise<void> {
  const { dir, canonicalPath, outputDir } = opts;

  // Load canonical numbers if provided
  let canonicals: CanonicalNumbers = {};
  if (canonicalPath && fs.existsSync(canonicalPath)) {
    canonicals = JSON.parse(fs.readFileSync(canonicalPath, "utf8"));
  }

  // Ensure output directory exists
  fs.mkdirSync(outputDir, { recursive: true });

  // Find all markdown files
  const mdFiles = findMarkdownFiles(dir);

  const summary: {
    scanned_at: string;
    total_files: number;
    passing: number;
    failing: number;
    violations_by_code: Record<string, number>;
    files: Array<{ file: string; pass: boolean; violation_count: number; receipt_file: string }>;
  } = {
    scanned_at: new Date().toISOString(),
    total_files: mdFiles.length,
    passing: 0,
    failing: 0,
    violations_by_code: {},
    files: [],
  };

  for (const filePath of mdFiles) {
    const content = fs.readFileSync(filePath, "utf8");
    const lines = content.split("\n");

    const violations: Violation[] = [
      ...checkSuperlatives(lines),
      ...checkEmojiInHeaders(lines),
      ...checkDOIDereferencing(lines),
      ...checkBadgeScoping(lines),
      ...checkCanonicalNumbers(lines, filePath, canonicals),
      ...checkStagedAdvisory(lines),
      ...checkArtifactURLs(lines),
      ...checkUncitedClaims(lines),
    ];

    const receipt = buildDSSEReceipt(filePath, content, violations);

    const receiptFileName = path.basename(filePath, ".md") + "_v7_receipt.json";
    const receiptPath = path.join(outputDir, receiptFileName);
    fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2), "utf8");

    const pass = violations.length === 0;
    if (pass) summary.passing++; else summary.failing++;

    for (const v of violations) {
      summary.violations_by_code[v.code] = (summary.violations_by_code[v.code] || 0) + 1;
    }

    summary.files.push({
      file: path.relative(dir, filePath),
      pass,
      violation_count: violations.length,
      receipt_file: receiptFileName,
    });

    const status = pass ? "PASS" : `FAIL (${violations.length} violation(s))`;
    console.log(`  ${status}: ${path.relative(dir, filePath)}`);
    if (!pass) {
      for (const v of violations) {
        console.log(`    [${v.code}] L${v.line}: ${v.text.substring(0, 80)}`);
      }
    }
  }

  fs.writeFileSync(
    path.join(outputDir, "SUMMARY.json"),
    JSON.stringify(summary, null, 2),
    "utf8"
  );

  console.log(
    `\nScan complete: ${summary.passing}/${summary.total_files} passing. ` +
    `Receipts in ${outputDir}/`
  );
  if (summary.failing > 0) {
    process.exitCode = 1;
  }
}

function findMarkdownFiles(dir: string): string[] {
  const results: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "node_modules") {
      results.push(...findMarkdownFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      results.push(fullPath);
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// CLI entrypoint
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const dirFlagIdx = args.indexOf("--dir");
const canonFlagIdx = args.indexOf("--canonical");
const outFlagIdx = args.indexOf("--output");

const scanDir = dirFlagIdx >= 0 ? args[dirFlagIdx + 1] : ".";
const canonPath = canonFlagIdx >= 0 ? args[canonFlagIdx + 1] : undefined;
const outputDir = outFlagIdx >= 0 ? args[outFlagIdx + 1] : "./v7_receipts";

console.log(`SZL Doctrine v7 Checker`);
console.log(`Scanning: ${path.resolve(scanDir)}`);
console.log(`Output:   ${path.resolve(outputDir)}`);
if (canonPath) console.log(`Canonicals: ${path.resolve(canonPath)}`);
console.log("");

scanDirectory({ dir: scanDir, canonicalPath: canonPath, outputDir }).catch((err) => {
  console.error("Scanner error:", err);
  process.exit(1);
});
