"""Contracts on where release provenance is minted and what credential mints it.

Every runtime guard in the release lane - the subject enumeration, the
``gh attestation verify`` gate, the completeness assertion - runs only inside a
release. None of them has executed once: the attestation wiring landed after
v0.1.73 and no tag contains it, so the file describes behaviour nothing has
observed. The checks here are what *can* be asserted without cutting a release,
and they are deliberately structural: they assert the shape those runtime
guards depend on, so a refactor cannot quietly take the shape away while the
runtime guard that would have noticed still waits for its first run.

Three properties are held here.

*Where provenance is minted.* ``actions/attest`` must not run in the job that
uploads the release assets. The ordering guarantee - nothing unattested becomes
a release asset - was step ordering inside one job and is now a job edge, so the
edge and its success condition are the guarantee and must be asserted as such.

*What credential mints it.* ``id-token: write`` lets any step in the job holding
it mint an OIDC token for any audience it names. The inventory of jobs holding
it is therefore fixed here by name: a new one is a decision, not an accident.

*What the documentation promises.* ``docs/channels.md`` told users to run
``gh attestation verify`` against assets that carry no attestation. What
replaced that instruction says which release provenance starts at, before
teaching the command - a frozen fact rather than a caveat with an expiry date.
The first attempt at this fix did write an expiring caveat, and the guards held
it by failing once the named release was cut. That is worse than it sounds: the
version lands in the release-please pull request, whose branch is regenerated
and force-pushed, so the repair would have had to be made under release
pressure on the one branch least able to hold it. The claims are worded to stay
true instead, and the tests below hold the wording rather than a deadline.

What is deliberately NOT done, because it looked like the obvious answer: a
smoke workflow that attests a throwaway file on every push, to exercise the
lane before a tag. It would work, and it would cost the users the documented
check is for. ``gh attestation verify <asset> --repo nevenincs/vaultspec-core``
- the command the documentation leads with - accepts a bundle minted by ANY
workflow in this repository that can obtain ``id-token: write``. A second
attesting workflow therefore widens what that command accepts, permanently, so
that a guard could be observed. The lane stays exercised only by a release, and
the structural checks below are the compensation rather than a substitute.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import TypedDict, cast

import pytest
import yaml

pytestmark = [pytest.mark.repo]

#: Repository root (``dev/guards/`` -> ``dev/`` -> repo).
ROOT = Path(__file__).resolve().parents[2]

#: Workflow directory, relative to the repository root.
WORKFLOWS = ROOT / ".github" / "workflows"

#: Every job, in any workflow, permitted to mint an OIDC token. Written out
#: rather than derived: the point of the assertion is that adding a job to this
#: set is an edit somebody makes on purpose and a reviewer sees.
#:
#: ``publish.yml:publish-pypi`` holds the grant for PyPI trusted publishing,
#: which is the credential that job exists to use. Its attestation reuses that
#: token rather than justifying a second one, so splitting an attest job out of
#: it - the change made to ``binaries.yml`` - would narrow nothing there.
TOKEN_MINTING_JOBS = frozenset(
    {
        ("binaries.yml", "attest"),
        ("publish.yml", "publish-pypi"),
    }
)

#: The mutable, co-authored manifest that must never be an attestation subject.
#: Both release workflows write it to the same release on the same tag, so
#: whichever finishes last replaces the bytes an earlier attestation covered.
MUTABLE_MANIFEST = "SHA256SUMS"

_VERSION = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")

_FIRST_ATTESTED = re.compile(
    r"v(?P<version>\d+\.\d+\.\d+) is the first release whose assets carry "
    r"build provenance"
)

_LAST_UNATTESTED = re.compile(
    r"The wiring that mints attestations landed after v(?P<version>\d+\.\d+\.\d+)"
)

#: Phrasings that state the unattested condition as universal rather than as a
#: property of releases up to a named version. Each one is true only until the
#: first attested release ships and silently wrong afterwards, which is the
#: same defect as the unqualified instruction - pointed the other way.
_UNIVERSALLY_UNATTESTED = (
    "no release published so far carries a build attestation",
    "build provenance is not available yet",
    "no published asset carries an attestation",
)

_SIGNER_WORKFLOW = re.compile(
    r"--signer-workflow nevenincs/vaultspec-core/\.github/workflows/(?P<name>[\w.-]+)"
)


#: One job in a GitHub Actions workflow, narrowed to what is read here.
#: Declared functionally because `if` is a Python keyword and so cannot be an
#: attribute in the class syntax - and the job-level `if:` is exactly the field
#: that carries the ordering guarantee this module asserts.
_WorkflowJob = TypedDict(
    "_WorkflowJob",
    {
        "name": str,
        "needs": "str | list[str]",
        "permissions": "dict[str, str]",
        "steps": "list[dict[str, object]]",
        "if": str,
    },
    total=False,
)


class _Workflow(TypedDict, total=False):
    """The top-level shape of a workflow file, narrowed to what is read here."""

    permissions: dict[str, str]
    jobs: dict[str, _WorkflowJob]


def _workflow_paths() -> list[Path]:
    """Every workflow file, proven to exist before anything reads them."""
    paths = sorted(WORKFLOWS.glob("*.yml"))
    assert paths, f"no workflow files found under {WORKFLOWS}"
    return paths


def _load(path: Path) -> _Workflow:
    """Parse one workflow file into the slice of its schema read here."""
    return cast("_Workflow", yaml.safe_load(path.read_text(encoding="utf-8")))


def _steps(job: _WorkflowJob) -> list[dict[str, object]]:
    """The job's steps, with a missing or null ``steps:`` read as none."""
    return job.get("steps") or []


def _job_text(path: Path, job_name: str) -> str:
    """The raw source of one job, comments included.

    Parsed YAML cannot answer questions about secrets referenced in comments or
    about a grant a reader would see, so the assertions that are about what the
    file *says* read the text of exactly one job rather than the whole file.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line == f"  {job_name}:"),
        None,
    )
    assert start is not None, f"{path.name} has no job block for '{job_name}'"
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  [\w-]+:$", lines[i])),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _needs(job: _WorkflowJob) -> list[str]:
    """A job's dependencies, as a list whatever the YAML spelling."""
    declared = job.get("needs")
    if declared is None:
        return []
    return [declared] if isinstance(declared, str) else list(declared)


def _jobs_running(workflow: _Workflow, action: str) -> list[str]:
    """Names of jobs with a step whose ``uses:`` names ``action``."""
    return [
        job_name
        for job_name, job in (workflow.get("jobs") or {}).items()
        if any(str(step.get("uses", "")).startswith(action) for step in _steps(job))
    ]


def _project_version() -> tuple[int, int, int]:
    """The version in ``pyproject.toml``, which is the newest release cut."""
    raw = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = cast("dict[str, object]", raw["project"])["version"]
    matched = _VERSION.match(str(version))
    assert matched is not None, f"pyproject version '{version}' is not X.Y.Z"
    return (
        int(matched["major"]),
        int(matched["minor"]),
        int(matched["patch"]),
    )


def _as_tuple(version: str) -> tuple[int, int, int]:
    """Split an ``X.Y.Z`` string into a comparable tuple."""
    major, minor, micro = version.split(".")
    return int(major), int(minor), int(micro)


def _doc_paths() -> list[Path]:
    """Every Markdown file under ``docs/``, proven non-empty before it is read.

    Derived here rather than in the test that scans it: a glob that matches
    nothing yields no offenders and passes, so a renamed directory would retire
    the scan instead of failing it.
    """
    paths = sorted((ROOT / "docs").rglob("*.md"))
    assert paths, f"no Markdown files found under {ROOT / 'docs'}"
    return paths


def _channels_prose() -> str:
    """``docs/channels.md`` with its line wrapping flattened.

    ``mdformat --wrap 88`` decides where these sentences break, so a claim is
    matched against the prose rather than against the lines it happens to
    occupy this week.
    """
    text = (ROOT / "docs" / "channels.md").read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text.replace("**", ""))


def test_no_workflow_grants_id_token_at_workflow_scope() -> None:
    """A workflow-scope ``id-token`` grant lands on every job in the file.

    That is the defect this repository was checked for and does not have: the
    grant is declared per job in both workflows that use it. Asserted so it
    stays a property rather than a coincidence, because the cost of losing it is
    silent - every job in the file gains the capability and nothing fails.
    """
    offenders: list[str] = []
    for path in _workflow_paths():
        permissions = _load(path).get("permissions") or {}
        if permissions.get("id-token") == "write":
            offenders.append(path.name)

    assert not offenders, (
        "these workflows grant `id-token: write` at workflow scope, which gives "
        f"it to every job in the file: {offenders}"
    )


def test_only_the_named_jobs_can_mint_an_oidc_token() -> None:
    """The inventory of token-minting jobs is fixed, not discovered."""
    holders: set[tuple[str, str]] = set()
    for path in _workflow_paths():
        for job_name, job in (_load(path).get("jobs") or {}).items():
            if (job.get("permissions") or {}).get("id-token") == "write":
                holders.add((path.name, job_name))

    assert holders == TOKEN_MINTING_JOBS, (
        "the set of jobs that can mint an OIDC token changed; expected "
        f"{sorted(TOKEN_MINTING_JOBS)}, found {sorted(holders)}"
    )


def test_the_attesting_job_holds_only_the_credential_it_signs_with() -> None:
    """``binaries.yml``'s attest job grants exactly the signing permissions.

    ``contents: write`` here would put an asset-uploading capability beside a
    token-minting one, which is the arrangement this job was split out to end.
    """
    workflow = _load(WORKFLOWS / "binaries.yml")
    jobs = workflow.get("jobs") or {}
    attesting = _jobs_running(workflow, "actions/attest@")
    assert attesting == ["attest"], (
        f"expected `actions/attest` in the 'attest' job only, found {attesting}"
    )

    assert jobs["attest"].get("permissions") == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }, "the attest job's permissions are no longer the minimum signing set"


def test_the_attesting_job_checks_out_nothing_and_reads_no_secret() -> None:
    """Nothing in the signing job can reach a credential beyond its own token.

    A checkout would bring project code into the job holding ``id-token``, and
    a ``secrets.`` reference would put a second credential there. The job needs
    neither: it downloads artifacts, enumerates them, and calls the action.
    """
    workflow = _load(WORKFLOWS / "binaries.yml")
    job = (workflow.get("jobs") or {})["attest"]

    checkouts = [
        str(step.get("name", step.get("uses")))
        for step in _steps(job)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert not checkouts, (
        f"the attest job checks out a repository, which puts code beside the "
        f"OIDC credential: {checkouts}"
    )

    source = _job_text(WORKFLOWS / "binaries.yml", "attest")
    referenced = set(re.findall(r"secrets\.(\w+)", source))
    assert not referenced, (
        f"the attest job references secrets, so it holds more than the "
        f"credential it signs with: {sorted(referenced)}"
    )


def test_the_uploading_job_cannot_mint_a_token() -> None:
    """The job holding the deploy key must not also hold ``id-token``.

    ``release`` checks out the shared distribution repository with
    ``CHANNEL_ROOT_DEPLOY_KEY`` and runs ``dev/packaging`` tree code. The two
    capabilities do not compose - an SSH key is not OIDC-federated - but a job
    that both runs project code and can mint tokens for any audience is the
    widest surface in this repository, and it no longer needs to be.
    """
    workflow = _load(WORKFLOWS / "binaries.yml")
    jobs = workflow.get("jobs") or {}
    uploading = [
        job_name
        for job_name, job in jobs.items()
        if any("gh release upload" in str(step.get("run", "")) for step in _steps(job))
    ]
    assert uploading == ["release"], (
        f"expected only 'release' to upload assets, found {uploading}"
    )

    permissions = jobs["release"].get("permissions") or {}
    assert "id-token" not in permissions, (
        "the release job can mint an OIDC token again; it holds the channel "
        "deploy key and runs tree code, and needs neither to upload or verify"
    )
    assert "attestations" not in permissions, (
        "the release job can publish attestations again; it only reads them back"
    )


def test_no_asset_is_uploaded_unless_the_attestation_succeeded() -> None:
    """The ordering guarantee is a job edge now, so assert the edge.

    ``needs`` alone is not enough: ``release`` runs under ``!cancelled()`` so a
    partial matrix still publishes what built, and that same condition would
    happily run the upload after a failed attestation. The success check on
    ``needs.attest`` is what forbids it.
    """
    workflow = _load(WORKFLOWS / "binaries.yml")
    jobs = workflow.get("jobs") or {}
    release = jobs["release"]

    assert "attest" in _needs(release), (
        "the release job no longer depends on the attest job, so an unattested "
        "asset can reach the release"
    )
    condition = release.get("if", "")
    assert "needs.attest.result == 'success'" in condition, (
        "the release job's `if:` no longer requires the attestation to have "
        f"succeeded, so `!cancelled()` would publish unattested assets: {condition!r}"
    )


def test_the_verification_gate_compares_against_the_attesting_job() -> None:
    """The verify step must read the subject set from ``needs``, not itself.

    While both derivations lived in one job the comparison was a list against
    itself and could not fail. It is only a real check because the expectation
    crosses the job edge from the job that actually signed.
    """
    workflow = _load(WORKFLOWS / "binaries.yml")
    steps = _steps((workflow.get("jobs") or {})["release"])
    # Matched on the invocation over a subject, not on the substring
    # `gh attestation verify`: the step above it asks `--help` the same
    # question to establish that the runner's `gh` is new enough, and matching
    # that one would have made this assertion read a step with no subjects.
    gate = next(
        (
            step
            for step in steps
            if 'gh attestation verify "${asset}"' in str(step.get("run", ""))
        ),
        None,
    )
    assert gate is not None, "the release job no longer verifies the attestations"

    declared = cast("dict[str, object]", gate.get("env", {}))
    env = " ".join(str(value) for value in declared.values())
    assert "needs.attest.outputs.names" in env, (
        "the verification gate no longer compares the attached set against the "
        "set the attest job signed"
    )
    assert "needs.attest.outputs.count" in env, (
        "the verification gate's expected count is no longer taken from the "
        "attest job, so it can agree with a list it derived itself"
    )


@pytest.mark.parametrize(
    ("workflow_name", "job_name"),
    sorted(TOKEN_MINTING_JOBS),
)
def test_the_mutable_manifest_is_never_an_attestation_subject(
    workflow_name: str, job_name: str
) -> None:
    """Both lanes must exclude ``SHA256SUMS`` from the subject derivation.

    Both release workflows write that file to the same release on the same tag
    and merge into it, so whichever finishes last replaces the bytes an earlier
    attestation covered - and ``gh attestation verify`` then fails on the one
    asset whose whole purpose is to be checked.
    """
    workflow = _load(WORKFLOWS / workflow_name)
    steps = _steps((workflow.get("jobs") or {})[job_name])
    derivations = [
        str(step.get("run", ""))
        for step in steps
        if "GITHUB_OUTPUT" in str(step.get("run", ""))
        and "subjects" in str(step.get("run", ""))
    ]
    assert derivations, (
        f"{workflow_name}:{job_name} no longer derives an attestation subject list"
    )
    for derivation in derivations:
        assert f"! -name {MUTABLE_MANIFEST}" in derivation, (
            f"{workflow_name}:{job_name} would attest {MUTABLE_MANIFEST}, which "
            "both release workflows rewrite after it is minted"
        )


def test_every_documented_signer_workflow_actually_attests() -> None:
    """A ``--signer-workflow`` a user is told to pin must mint attestations.

    Pinned to a workflow that signs nothing, the command fails for a reason the
    error message does not name, and the user reads it as a bad download.
    """
    prose = (ROOT / "docs" / "channels.md").read_text(encoding="utf-8")
    # `publish.yml` is named in prose rather than in a flag, as the lane a
    # wheel or sdist was signed by, so it is added rather than matched.
    named = set(_SIGNER_WORKFLOW.findall(prose)) | {"publish.yml"}
    assert named, "docs/channels.md documents no signer workflow"

    for name in sorted(named):
        path = WORKFLOWS / name
        assert path.is_file(), f"docs/channels.md pins {name}, which does not exist"
        assert _jobs_running(_load(path), "actions/attest@"), (
            f"docs/channels.md tells users to pin --signer-workflow to {name}, "
            "which runs no attestation step"
        )


def test_the_provenance_instruction_is_never_unqualified() -> None:
    """``gh attestation verify`` must not be taught before the docs say from when.

    This is the defect the module exists for. The page carried the command with
    no statement of which releases can satisfy it while every published asset
    was unattested, so a user following the instruction got a failure whose only
    available readings were "this binary is not authentic" and "verification is
    broken, skip it". The second is the expensive one: it is learned once and
    applied to every project afterwards.

    Asserted as an ordering rather than as the presence of a caveat, because
    presence is satisfiable by a sentence anywhere on the page. What protects
    the reader is meeting the boundary BEFORE the command.
    """
    prose = _channels_prose()
    boundary = _FIRST_ATTESTED.search(prose)
    assert boundary is not None, (
        "docs/channels.md no longer names the release build provenance starts "
        "at, so the verification instruction is unqualified again"
    )
    taught = prose.find("gh attestation verify")
    assert taught != -1, "docs/channels.md no longer documents `gh attestation verify`"
    assert boundary.start() < taught, (
        "docs/channels.md teaches `gh attestation verify` before it says which "
        "releases carry provenance; a reader on an older release meets the "
        "command first and reads its failure as a bad download"
    )


def test_the_documented_provenance_boundary_is_self_consistent() -> None:
    """The two versions the page names must describe one boundary, not two.

    Both are frozen historical facts - which release the wiring landed after,
    and which release first carried it - so neither expires and neither may be
    edited alone. The comparison against ``pyproject.toml`` is the one tie to
    the present, and it holds in the only direction that can be true: the
    wiring cannot have landed after a release that has not been cut.
    """
    prose = _channels_prose()
    last = _LAST_UNATTESTED.search(prose)
    first = _FIRST_ATTESTED.search(prose)
    assert last is not None, (
        "docs/channels.md no longer says which release the attestation wiring "
        "landed after, so the boundary cannot be checked for consistency"
    )
    assert first is not None, (
        "docs/channels.md no longer names the first release to carry provenance"
    )

    unattested = _as_tuple(last["version"])
    attested = _as_tuple(first["version"])
    assert attested > unattested, (
        f"docs/channels.md says provenance starts at v{first['version']} but "
        f"that the wiring landed after v{last['version']}; the first attested "
        "release cannot precede the last unattested one"
    )
    current = _project_version()
    assert unattested <= current, (
        f"docs/channels.md says the wiring landed after v{last['version']}, "
        f"which is newer than v{'.'.join(map(str, current))} in pyproject.toml "
        "- that release does not exist yet"
    )


def test_the_docs_never_state_the_unattested_condition_as_universal() -> None:
    """Nothing may say provenance is unavailable outright, only up to a version.

    An earlier pass fixed the unqualified instruction with a "not available
    yet" section, which trades a page that is wrong today for one that goes
    wrong on the release that makes it false - and does so silently, with no
    edit to notice. Every claim on the page is instead written as a property of
    releases up to a named version, which is a fact that never changes and
    needs no maintenance at release time.
    """
    prose = _channels_prose().lower()
    offenders = [phrase for phrase in _UNIVERSALLY_UNATTESTED if phrase in prose]
    assert not offenders, (
        "docs/channels.md states the unattested condition as universal rather "
        "than as a property of releases up to a named version, so it becomes "
        f"wrong the moment an attested release ships: {offenders}"
    )


def test_the_docs_never_describe_code_signing_as_forthcoming() -> None:
    """Publisher identity is settled as not planned, so nothing may promise it.

    The issues that tracked a code-signing certificate on Windows and Apple
    Developer membership on macOS are closed without work. Prose that reads as
    "not signed yet" leaves a user waiting for a build that is never coming,
    and it also quietly demotes attestation to a stopgap when it is in fact the
    whole verification story this project offers.

    Matched on phrasings rather than on the word "signing", which the docs must
    keep using: the section that explains the SmartScreen and Gatekeeper
    warnings cannot be written without it.
    """
    forthcoming = (
        "publisher signing is tracked",
        "signing is planned",
        "not signed yet",
        "not yet signed",
        "until signing",
        "once signing",
        "issues/405",
        "issues/342",
        "issues/336",
    )
    offenders: list[str] = []
    for path in _doc_paths():
        lowered = path.read_text(encoding="utf-8").lower()
        offenders.extend(
            f"{path.relative_to(ROOT).as_posix()}: {phrase!r}"
            for phrase in forthcoming
            if phrase in lowered
        )

    assert not offenders, (
        "these documents present code signing as forthcoming, but it is closed "
        f"as not planned: {offenders}"
    )
