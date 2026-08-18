# Contributing to pycommon

This library is shared by several services. A bug here is a bug in all of them
at once, and a breaking change here is an upgrade someone else has to absorb.
That shapes most of what follows.

> **Note on licensing:** the repository currently ships under a proprietary
> [LICENSE](LICENSE). Until that changes, contributions come from people with
> push access rather than from public forks.

## Getting set up

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
make install && make pre-commit
```

`make help` lists every target. The one to remember is `make check`, which runs
exactly what CI runs — lint, format check, mypy `--strict`, and the test suite
under its coverage floor. Run it before you push and CI will rarely tell you
anything new.

`make audit` runs `pip-audit` against the exported lockfile. CI runs it as its
own job, so an advisory published overnight can turn a branch red without
anything in it having changed — that is a dependency to upgrade, not a mistake
you made.

## Branching

Work happens on short-lived branches off `main`, merged by pull request. There
is no `develop` branch: this library releases by tag, so there is nothing for a
second long-lived branch to buffer.

Name branches `<type>/<short-slug>`, where type is one of `feat`, `fix`,
`docs`, `refactor`, `test`, `perf`, or `chore` — for example
`fix/rate-limiter-fail-open`.

Aim to merge within a week. A branch that lives longer usually wants to be
split: long branches drift from `main`, and they arrive as a review nobody has
time to do properly.

## Commits

Write the subject line in the imperative mood, and say what the change *does*
for the system rather than which files it touched — "Stop the rate limiter
failing closed on a Redis outage", not "Update rate_limit.py".

Use the body to explain **why**. What was the behaviour before, what breaks
because of it, and why this fix rather than another. Six months from now the
diff will still be readable and the reasoning will not be recoverable from
anywhere else. Wrap it at 72 characters.

Keep each commit to one logical change. A commit that fixes two unrelated
things cannot be reverted or cherry-picked without dragging the other one
along.

## Pull requests

Fill in the template. The part that matters most is *why* — a reviewer who
understands the failure you are preventing can tell you the fix is wrong; one
who only sees the diff can only tell you it looks fine.

Requirements:

- CI green (`lint-test` and `audit`).
- Tests that fail without your change. For a bug fix, the test should reproduce
  the original failure, not merely exercise the new code path.
- Coverage stays above the floor in `pyproject.toml`. If a change genuinely
  needs the floor lowered, say why in the pull request — it is a decision, not a
  formality.
- `CHANGELOG.md` updated under `## [Unreleased]` for anything a consumer can
  observe — new API, changed behaviour, bug fixes. Skip it for internal
  refactors and test-only changes.
- Breaking changes marked **BREAKING** in the changelog **with a migration
  note**. Show the before and after; a consumer should be able to follow it
  without reading the diff.
- Public API carries type hints and a docstring saying what it does and how it
  fails.

### How PRs get merged

- **Squash** by default — one pull request becomes one commit on `main`, which
  keeps `git bisect` meaningful.
- **Rebase** when the branch's commits each stand on their own and each one
  passes CI. Squashing a well-sequenced branch throws away the reasoning in
  every commit body but the last.

Merge commits are disabled; `main` stays linear.

## Testing

`make test`, or `make test-cov` for coverage.

Tests use `pytest-asyncio`, with `fakeredis` for Redis and `aiosqlite` for the
database, so the suite needs no running services. Prefer those over mocks:
a fake that implements the real protocol catches errors a mock is configured to
ignore.

Redis is faked with `fakeredis`, which does not model Lua scripting, cluster
behaviour or connection failure faithfully. Anything depending on those — the
rate limiters, the distributed lock — deserves scepticism about what its tests
actually prove.

`pycommon.testing.fakes` holds the in-memory doubles this library ships for its
*consumers*. When you extend an interface, extend the fake in the same PR —
otherwise the fake quietly stops being a substitute for the real thing, and
every service that tests against it loses coverage without any test turning
red.

## Design conventions

These come up in review often enough to write down:

- **Fail open on infrastructure, fail closed on authorization.** A rate limiter
  or cache that returns 500 when Redis is unreachable is worse than one that
  lets traffic through; auth is the opposite. When something degrades, say so in
  the result, so that traffic stays distinguishable in metrics from traffic that
  genuinely passed.
- **Bound anything keyed by caller-controlled input.** Client IPs, URL paths and
  header values all arrive from the network. Unbounded dicts become memory
  leaks, and unbounded metric labels become a bill.
- **Optional dependencies stay optional.** Anything beyond the base install
  belongs in an extra in `pyproject.toml`, imported inside the module that needs
  it. Consumers install `pycommon[http]`, not the whole world.
- **No secrets in logs or error messages**, including in exception context.
- Follow the shape of the code around you before introducing a new pattern.

## Reporting bugs

Include the pycommon version (the tag you pinned), what you expected, what
happened, and the smallest reproduction you can manage. If it involves a
downstream service, say which extras you installed.

For anything security-sensitive, do not open a public issue — contact the
maintainer directly.

## Releasing

Maintainers only: see [RELEASING.md](RELEASING.md).
