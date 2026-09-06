# Documentation

[Install Core](../README.md#install) to get started.

<p id="start-here"></p>

## Use Core

- [Run a feature workflow and customize project rules](framework.md).
- [Edit document prose and structure](syntax.md).
- [Check your workspace and repair records](verification.md).
- [Review implementation and test evidence](correctness.md).

<p id="look-these-up-when-you-need-them"></p>

## Reference

- [Look up commands](CLI.md).
- [Set up the MCP server and look up tools](MCP.md).

[Report a problem](https://github.com/nevenincs/vaultspec-core/issues).

## For maintainers

Use conventional commit messages such as `feat:`, `fix:`, and `feat!:`. release-please
maintains a release pull request with the next version and changelog. Merging it creates
a GitHub release and starts publication: the workflow builds and smoke-tests the wheel
and sdist, then publishes to PyPI using OIDC trusted publishing.

The terminal renders and the demo GIF in `assets/` are produced by the renderers in
`_render/`, which run `vaultspec-core` against a throwaway vault. Edit the renderer
rather than the SVG, then run `just docs` to regenerate. That covers `demo.gif` and the
`term-*.svg` files; the logo and the Obsidian screenshot are not generated.

### Update package-manager manifests

From the Core repository, run this command with the tag and aggregated `SHA256SUMS` from
the same release:

```sh
just channels <tag> <path-to-homebrew-tap-checkout> <path-to-SHA256SUMS>
```

The command generates and validates `bucket/vaultspec-core.json` and
`Formula/vaultspec-core.rb` in your `nevenincs/homebrew-tap` checkout. These manifests
install pre-built binaries. Review both files, then commit and push the changes.

Validation runs offline. It checks digest syntax, matching versions, and buildable asset
names. It doesn't download or verify assets or confirm URLs exist.

To change the generated output, edit [package metadata](../dev/packaging/products.py) or
the [Scoop](../dev/packaging/scoop.py) and [Homebrew](../dev/packaging/homebrew.py)
generators. The next release overwrites generated files.
