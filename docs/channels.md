# Distribution channels

Install Core with Scoop on Windows or Homebrew on macOS and Linux. Both channels install
`vaultspec-core` and `vaultspec-mcp`.

You don't need a separate Python installation. First launch needs network access to
fetch `uv` and install the pinned Vaultspec package and its dependencies from PyPI;
later launches run entirely offline.

## Coverage

| Platform | Architecture          | Availability |
| -------- | --------------------- | ------------ |
| Windows  | x86-64                | Scoop        |
| macOS    | arm64 (Apple Silicon) | Homebrew     |
| macOS    | x86-64 (Intel)        | Unavailable  |
| Linux    | x86-64                | Homebrew     |
| Linux    | arm64                 | Homebrew     |

Windows with Scoop:

```powershell
scoop bucket add nevenincs https://github.com/nevenincs/homebrew-tap
scoop install vaultspec-core
```

macOS and Linux with Homebrew:

```sh
brew tap nevenincs/tap https://github.com/nevenincs/homebrew-tap
brew install vaultspec-core
```

## Binaries are not code-signed

Core's binaries carry no publisher signature, and they won't get one. Code signing needs
a paid, per-year identity tied to a legal entity - a hardware-held certificate on
Windows, Apple Developer Program membership on macOS. This is an open-source project and
neither is being bought. That's a settled decision, not a gap waiting to be filled:
don't wait for a signed build.

What it costs you is one warning, once, on each platform. Both are your operating system
reporting that it doesn't know who published the file - not that the file is damaged or
that the download went wrong.

### Windows

Running a binary you downloaded from the release page in a browser shows
`Windows protected your PC`. Choose **More info**, then **Run anyway**. Installing with
Scoop avoids it: Scoop fetches the binary itself rather than through a browser, so the
download isn't marked as having come from the internet.

### macOS

Gatekeeper quarantines anything a browser downloads, and an unsigned, un-notarized
binary is then refused with `cannot be opened because the developer cannot be verified`.

**Install with Homebrew and you never meet it** - `brew` fetches without setting the
quarantine attribute. That's the supported path on macOS and the reason to prefer it.

For a binary you did download directly, clear the attribute and mark it executable:

```sh
xattr -d com.apple.quarantine ./vaultspec-core-aarch64-apple-darwin
chmod +x ./vaultspec-core-aarch64-apple-darwin
```

Verify the download first - the checks below are what tells you the file is the one this
repository published, and clearing quarantine tells macOS to stop asking.

## Verifying what you downloaded

Download `SHA256SUMS` from the same release as your asset. Compute the asset's SHA-256
hash with the command for your platform, replacing `./asset` with its path:

| Platform             | Command                                                 |
| -------------------- | ------------------------------------------------------- |
| Windows (PowerShell) | `Get-FileHash -Algorithm SHA256 -LiteralPath './asset'` |
| macOS                | `shasum -a 256 './asset'`                               |
| Linux                | `sha256sum './asset'`                                   |

Compare the result with the hash beside that asset's filename in `SHA256SUMS`; letter
case doesn't matter. If they differ, don't run the asset. Download it again from the
same release and recheck.

A matching checksum confirms agreement with the release manifest. It doesn't establish
where the asset came from: whoever can replace a binary on a release page can replace
the manifest beside it in the same act.

Build provenance answers that second question, and it's the supported way to establish
that an asset came from this repository's release workflow. It's what this project
offers in place of a publisher signature, and unlike a signature it costs nothing to
produce and nothing to check.

### Build provenance is not available yet

**No release published so far carries a build attestation.** The wiring that mints one
landed after v0.1.73, so **v0.1.74 is the first release whose assets will have build
provenance**. Until it's out, `gh attestation verify` fails on every asset you can
download, and that failure means the attestation was never minted - not that your
download is bad. Check the checksum above and stop there.

From v0.1.74 onward, verify an asset's provenance with
[GitHub CLI](https://cli.github.com/manual/gh_attestation_verify):

```sh
gh attestation verify <asset> --repo nevenincs/vaultspec-core
```

Replace `<asset>` with the downloaded file's path. Assets from v0.1.73 and earlier stay
unattested permanently; nothing is minted retroactively. If verification fails on a
release that should carry provenance, check the command's error before running the
asset.

To require a particular signing workflow, add `--signer-workflow`. For the release
binaries:

```sh
gh attestation verify <asset> --repo nevenincs/vaultspec-core --signer-workflow nevenincs/vaultspec-core/.github/workflows/binaries.yml
```

For a wheel or source distribution, use
`nevenincs/vaultspec-core/.github/workflows/publish.yml` instead. `SHA256SUMS` itself
has no attestation because both release workflows update it; verify the individual
assets.

A build attestation is not a code signature and doesn't act like one: it changes nothing
about SmartScreen or Gatekeeper, which ask who published a file rather than where it was
built. Those warnings are expected and permanent - see
[Binaries are not code-signed](#binaries-are-not-code-signed). Provenance is the
integrity check this project does offer, and it needs no certificate from anybody.

For release maintenance, see
[updating package-manager manifests](README.md#update-package-manager-manifests).
