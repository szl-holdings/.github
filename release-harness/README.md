# Release harness

Staging checks for the a11oy command-centre journey. The harness lives
in this governance repo and does not deploy anything.

Read from `szl-holdings/a11oy` at
`9467fa988ff63c919954adbd8e23e930412321b5`:

- Page: `GET /command-centre` (mobile and desktop).
- Build id: `#source-sha`, fed by `GET /api/build-info`
  (`build.revision` when `status` is `OBSERVED`).
- Turn: `POST /api/a11oy/v1/atelier/turn` with a bearer credential.
  `401` is missing auth, `403` is `AUTH_FORBIDDEN`, `402` is
  `PROVIDER_HTTP_402` from the provider.
- Evidence: the outcome receipt rendered in `#receipt`. Its
  `receipt.payload.source_revision` must equal the build id above.

## Layout

- `tests/critical-journey.spec.ts` opens the journey on a mobile
  viewport, sends one valid request, requires a real answer, and
  checks the same build id in the evidence.
- `tests/accessibility.spec.ts` runs `@axe-core/playwright` with
  WCAG 2.2 AA tags, keyboard-only navigation, and name/role checks.
- `playwright.config.ts` has Chromium, Firefox, and WebKit, each on
  desktop, Pixel 7, and iPhone 14.
- `contract/` checks configured HTTP statuses. Schema checks use
  OpenAPI when the document and the path both exist.
- `canary/compare.py` compares canary and control error rate and p95.
  Caps and stop thresholds are set before the run.
- `fixtures/a11oy_fixture.py` is the local stand-in used by self-tests.

## Staging gate

`canary/compare.py` refuses every host when `--staging` is absent.
It also refuses these production hosts:

- `a-11-oy.com` and `www.a-11-oy.com`
- `a11oy.net` and `www.a11oy.net`
- `inference.a-11-oy.com`
- any other host under those two zones
- `*.hf.space`

An apex in that list is never accepted. A denylist host is accepted
only when the staging flag is set, `--target-class staging` is set,
and a DNS label is `staging`, `stage`, `preview`, or ends in
`-staging`, `-stage`, or `-preview`. Absolute ceilings are 5 RPS,
30 seconds, and 40 requests. The canary issues GETs only.

Playwright calls the same host check before opening a browser.

## Local commands

```bash
python3 -m unittest discover -s canary -p 'test_*.py' -v
python3 -m unittest discover -s contract -p 'test_*.py' -v
npm ci
npm run test:unit
npm run typecheck
npx playwright install --with-deps chromium firefox webkit
HARNESS_FIXTURE=1 STAGING=true \
  BASE_URL=http://127.0.0.1:8765 API_URL=http://127.0.0.1:8765 \
  A11OY_OPERATOR_CREDENTIAL=fixture-operator \
  npx playwright test
```

`fixture-operator` is a local fixture token, not a production
credential.

The gap fixture omits the build id from the receipt:

```bash
HARNESS_FIXTURE=1 FIXTURE_GAP=omit-evidence-build-id STAGING=true \
  BASE_URL=http://127.0.0.1:8876 API_URL=http://127.0.0.1:8876 \
  A11OY_OPERATOR_CREDENTIAL=fixture-operator \
  npx playwright test tests/critical-journey.spec.ts \
  --project=chromium-pixel7
```

That command is expected to fail the same-build check.

## Reusable workflow

`.github/workflows/release-harness.yml` is a `workflow_call`.
Inputs are `base_url`, `api_url`, `browsers`, and `staging`.
`staging` must be true. Permissions are `contents: read`.
Actions are pinned to full SHAs. Playwright traces and the HTML
report are uploaded as artifacts.

The same file runs fixture self-tests on pull requests that touch
this directory. Those tests do not need a secret.

## Unknowns

- No a11oy staging or preview URL was found in the source that was
  read. Production origins were not probed and were not loaded.
- The public verifier `GET /api/a11oy/v1/verify/receipt/{receipt_id}`
  checks a signature, a payload digest, and a hash chain. It was not
  confirmed to echo the build id. The journey compares the build id
  on the command-centre receipt.
- A committed flagship OpenAPI document was not in the a11oy tree.
  The app can serve `/api/a11oy/openapi.json` at runtime.
  `POST /api/a11oy/v1/atelier/turn` and the atelier health route are
  registered with `include_in_schema=False`, so schema coverage of
  those routes stays `UNKNOWN` unless a spec starts documenting them.
- A live governed turn needs an operator credential this harness does
  not carry. The fixture token only works on the fixture.

## Rollback

Close the pull request, or revert the squash commit on `main`.
Deleting `release-harness/` and
`.github/workflows/release-harness.yml` removes the harness.
Nothing in this change publishes a Space, a profile, or a deploy.
