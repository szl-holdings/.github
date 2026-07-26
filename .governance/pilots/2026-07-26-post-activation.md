# FORGE-9 queue conflict control

This inert record is the later queue candidate for the AT-22 serialization
test. It deliberately adds the same path as pull request #319 with different
content.

Each pull request is independently applicable to the current default branch,
but the two additions cannot be combined. The merge queue must retain the
earlier valid entry and reject this later conflicting entry. This file does not
assert the test result; the queue timeline and rule-suite records are the source
of truth.
