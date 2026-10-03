import assert from "node:assert/strict";
import test from "node:test";

import {
  SOURCE_OWNED_DATASETS,
  assertBadgeWriteAllowed,
  isSourceOwnedDataset,
  publishReadmeCommit,
} from "./hf_dataset_badge_refresh.mjs";

const LAKE = "SZLHOLDINGS/szl-lake";
const LAKE_ALIASES = [
  LAKE,
  "szlholdings/szl-lake",
  "SzlHoldings/szl-lake",
  "SZLHOLDINGS/SZL-LAKE",
];

test("source-owned Lake and case aliases are explicitly excluded", () => {
  assert.equal(SOURCE_OWNED_DATASETS.has(LAKE), true);
  for (const id of LAKE_ALIASES) {
    assert.equal(isSourceOwnedDataset(id), true);
    assert.throws(
      () => assertBadgeWriteAllowed(id),
      /badge write refused; dataset is source-owned/,
    );
  }
});

test("publish helper refuses Lake aliases before network access", async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    throw new Error("network must not run");
  };

  for (const id of LAKE_ALIASES) {
    await assert.rejects(
      publishReadmeCommit({
        id,
        content: "---\nlicense: cc-by-4.0\n---\n",
        nfiles: 431,
        license: "cc-by-4.0",
        fetch: fetchImpl,
        headers: { Authorization: "Bearer test-only" },
      }),
      /badge write refused; dataset is source-owned/,
    );
  }
  assert.equal(calls, 0);
});

test("non-source-owned datasets retain the commit path", async () => {
  const requests = [];
  const response = { ok: true, status: 200 };
  const fetchImpl = async (...args) => {
    requests.push(args);
    return response;
  };

  const actual = await publishReadmeCommit({
    id: "SZLHOLDINGS/example-dataset",
    content: "example",
    nfiles: 7,
    license: "apache-2.0",
    fetch: fetchImpl,
    headers: { Authorization: "Bearer test-only" },
  });

  assert.equal(actual, response);
  assert.equal(requests.length, 1);
  assert.equal(
    requests[0][0],
    "https://huggingface.co/api/datasets/SZLHOLDINGS/example-dataset/commit/main",
  );
  assert.equal(requests[0][1].method, "POST");
  assert.match(requests[0][1].body, /docs: refresh badge stats/);
});
