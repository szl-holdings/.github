# Shared HF HTTP transport boundaries — review candidate

Owner: existing `.github#742` / PR `.github#743`; organization queue `.github#694`.

This is a successor to PR head `8331e2dc7490fd057223057b900cc51f32d11a17`, not a
new publisher, provider controller, or merge operator. Only the existing `_http`
definition changes among pre-existing publisher functions/classes. New helpers
constrain reads. The original source selection, deployment, SDK mutations,
restart, source/byte identity and public application probes remain unchanged.
The existing public-smoke test suite remains intact, with its opener assertion
updated to require an explicit empty environment-proxy policy.

## Read boundary

- Only HTTPS in the fixed Hugging Face host families is accepted. URL userinfo,
  fragments, non-443 ports, control characters and other origins are refused.
- Management Authorization is accepted only at `huggingface.co`. Same-origin
  management redirects may retain it. Other permitted delivery origins receive
  no Authorization, Cookie, Proxy-Authorization or inherited Host header.
- Redirects to `*.hf.space` applications are refused. Existing public application
  probes remain anonymous and nonredirecting; tenant authentication is not relaxed.
- Redirect response bodies are closed without being read. This avoids the
  standard redirect handler's unbounded drain while retaining its method and
  redirect-loop controls.
- Environment proxies are disabled for this dedicated read transport. No
  browser, account, application or provider authorization policy is changed.

## Bounds and failure behavior

Successful response bodies are limited to 64 MiB, nonretryable HTTP error bodies
are limited to 64 KiB, and individual reads request no more than 64 KiB. Oversize,
nonbyte, ambiguous Content-Length and truncated observations fail instead of
being truncated and called verified. Retryable errors are closed without reading
their bodies. These limits may reject legitimate larger artifacts; expand only
through an explicit reviewed contract and tests, not by removing the bound.

HTTP 429 and 5xx may retry, at most ten attempts. Retry-After delays are capped at
30 seconds, invalid/nonfinite/negative values fall back, and the final attempt
never sleeps. Provider exceptions and signed URLs are not included in the new
transport error. Existing caller-level bounded polling remains separate.

The socket timeout is 45 seconds, not a strict whole-call wall-clock deadline.
This does not eliminate slow streaming. The existing workflow deadline remains
separate. A strict total-deadline transport would require further implementation
and qualification. Direct signed delivery outside the fixed HF host families is
refused; legitimate delivery and private-file access require native validation.

## Qualification and release

150 unique unittest methods pass locally on Python 3.13.5: 46 new HTTP methods,
11 retained public-smoke methods and 93 retained publisher methods. The same
methods also pass with optimization enabled. All transports use inert offline
fixtures; no real token, provider mutation, or live deployment was used. The
new boundary suite fails against the exact preceding HTTP implementation.

The existing workflow now runs and hashes the new test file alongside every
original suite in its Python 3.11/3.12 matrix. Its pins, read-only permissions,
main-push and merge-group triggers are unchanged. This is source configuration,
not evidence that hosted checks ran on this successor.

Before admission: reconcile with the actual latest PR/base, run all current
native and merge-group checks, complete source review and use the normal queue.
Update consumers only to an admitted immutable controller revision/blob, then
verify canonical publication and live bytes/application behavior. Do not reuse
an older head's green results, skip failed smoke routes, restore public bearer
headers, bypass checks or turn failed model evaluations into positive results.
