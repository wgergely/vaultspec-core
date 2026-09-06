# Distribution channels

Install Core with Scoop on Windows or Homebrew on macOS and Linux. Both channels install
`vaultspec-core` and `vaultspec-mcp`.

You don't need a separate Python installation and you don't need network access. Each
binary carries its own interpreter, Vaultspec and the whole dependency tree, so the
first launch on an air-gapped machine behaves like any other. Every release runs its
binaries with the network taken away before publishing them - in an empty network
namespace on Linux, under a sandbox profile that denies the network on macOS, and with
every route to a package index blocked on Windows.

Two consequences follow from carrying everything. The downloads are large - roughly 45
to 70 MB depending on the platform, against 20 to 40 MB when the dependencies arrived
over the network instead. And the binaries do not update themselves: upgrade through
Scoop or Homebrew, which is where the version they install is decided anyway.

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

A matching checksum confirms agreement with the release manifest. To verify an asset's
build provenance, use [GitHub CLI](https://cli.github.com/manual/gh_attestation_verify):

```sh
gh attestation verify <asset> --repo nevenincs/vaultspec-core
```

Replace `<asset>` with the downloaded file's path. Older releases may have no build
attestation; a checksum match alone does not verify provenance. If verification fails,
check the command's error before running the asset.

To require a particular signing workflow, add `--signer-workflow`. For the release
binaries:

```sh
gh attestation verify <asset> --repo nevenincs/vaultspec-core --signer-workflow nevenincs/vaultspec-core/.github/workflows/binaries.yml
```

For a wheel or source distribution, use
`nevenincs/vaultspec-core/.github/workflows/publish.yml` instead. `SHA256SUMS` itself
has no attestation because both release workflows update it; verify the individual
assets.

Build attestations do not grant permission to run an executable under your operating
system's security policy. Publisher signing is tracked in
[#405](https://github.com/nevenincs/vaultspec-core/issues/405).

For release maintenance, see
[updating package-manager manifests](README.md#update-package-manager-manifests).
