# Public application smoke contract

Owner: `.github#742`; continuation: `a11oy#2154` and `a11oy#2155`.

The shared Dockerfile publisher has separate Hub control/file requests and
public application probes. Public probes do not attach Hub authentication.
They continue to require every declared same-host route to return exactly
HTTP 200 with non-empty content, without following redirects. Hub state and
immutable file reads retain their existing authentication and identity checks.

This does not grant anonymous tenant access or alter application authentication.
A private or authenticated route still fails this public contract and needs a
separate application-owned acceptance contract. A public smoke pass is not a
model-quality, inference, tenant-authentication, or production-authorization
certificate. Application-specific source and semantic checks remain required.

## Reproduction

The dedicated read-only workflow executes both the new public-transport tests
and the entire existing deployer regression module, normally and optimized,
on Python 3.11 and 3.12. Fixtures use inert tokens and a recording opener. The
real request construction, Hub state/file readers, route checker and complete
attestation CLI execute without a network request or provider mutation.

```sh
python -I -P .github/scripts/test_hf_public_smoke.py
python -I -P -O .github/scripts/test_hf_public_smoke.py
python -I -P .github/scripts/test_hf_deploy_from_dockerfile.py
python -I -P -O .github/scripts/test_hf_deploy_from_dockerfile.py
```

Source and interpreter receipts distinguish the tested checkout from the PR
head. A successful fixture run does not close a live deployment incident.

## Rollout boundary

After normal source admission, update each affected consumer's controller
revision and byte pin through its owning reviewed PR. In particular, the Lyte
publisher must consume the admitted controller rather than silently loading a
moving branch. Preserve every smoke path and the separate Lyte live contract.
Retain failed deployment manifests and native publication receipts, then prove
the actual exact-source child/job/receipt outcome before estate repair closure.

Shared credential/publication holds must be legitimately resolved before any
affected automatic publisher is allowed to run. This change does not rotate
credentials, mutate a Space, dispatch a writer, change allocation or visibility,
start training, or make a live-completion claim. Existing historical failure
receipts remain evidence for their original source and observation time.
