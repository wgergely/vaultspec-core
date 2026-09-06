"""Render the Homebrew formula that installs the release binaries.

The formula is committed to the ACCOUNT channel root,
``nevenincs/homebrew-tap``, rather than to this repository - the same root the
Scoop manifest goes to, for the same reason: a tap resolves to a repository, so
a per-product tap is one `brew tap` per product::

    brew tap nevenincs/tap https://github.com/nevenincs/homebrew-tap
    brew install vaultspec-core

This is a BINARY formula - it places the pre-built PyApp assets attached to
the GitHub Release. That is a deliberate divergence from cadrumo, whose
formula builds a Python virtualenv from a locked sdist cohort: cadrumo has no
binary channel, so its formula has to be the thing that assembles the
product. vaultspec already publishes standalone binaries for every Homebrew
platform, and rebuilding the same product a second way would double the
surface that can break while pinning two different sets of bytes as "the
release". The shared idiom across the family is the generation discipline -
one pointer, generated from the release's own SHA256SUMS, guarded against
backward bumps - not the formula's internal strategy.

A formula has exactly one primary ``url``, so the first executable is the
download and every other executable becomes a ``resource``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dev.packaging import products
from dev.packaging.checksums import require

if TYPE_CHECKING:
    from dev.packaging.products import Product

#: Homebrew's platform predicates, in the nesting order the formula emits.
#: Each entry is (Homebrew OS block, CPU block, Rust target triple).
_PLATFORMS = (
    ("on_macos", "on_arm", products.MACOS_ARM64),
    ("on_macos", "on_intel", products.MACOS_X86_64),
    ("on_linux", "on_intel", products.LINUX_X86_64),
    ("on_linux", "on_arm", products.LINUX_ARM64),
)


def _resource_block(name: str, url: str, digest: str, indent: str) -> list[str]:
    """Return the lines of one nested ``resource`` declaration."""
    return [
        f'{indent}resource "{name}" do',
        f'{indent}  url "{url}"',
        f'{indent}  sha256 "{digest}"',
        f"{indent}end",
    ]


def _cpu_block(
    product: Product,
    cpu: str,
    target: str,
    version: str,
    digests: dict[str, str],
) -> list[str]:
    """Return the lines of one ``on_arm``/``on_intel`` block."""
    primary, *rest = product.executables
    base = product.release_base_url(version)
    asset = product.asset_name(primary, target)
    lines = [
        f"    {cpu} do",
        f'      url "{base}/{asset}"',
        f'      sha256 "{require(digests, asset)}"',
    ]
    for executable in rest:
        extra = product.asset_name(executable, target)
        lines.append("")
        lines.extend(
            _resource_block(
                executable.name,
                f"{base}/{extra}",
                require(digests, extra),
                "      ",
            ),
        )
    lines.append("    end")
    return lines


def _os_blocks(
    product: Product,
    version: str,
    digests: dict[str, str],
    available: tuple[str, ...],
) -> list[str]:
    """Return the ``on_macos``/``on_linux`` blocks for the buildable targets."""
    lines: list[str] = []
    for os_block in ("on_macos", "on_linux"):
        selected = [
            (cpu, target)
            for block, cpu, target in _PLATFORMS
            if block == os_block and target in available
        ]
        if not selected:
            continue
        if lines:
            lines.append("")
        lines.append(f"  {os_block} do")
        for index, (cpu, target) in enumerate(selected):
            if index:
                lines.append("")
            lines.extend(_cpu_block(product, cpu, target, version, digests))
        lines.append("  end")
    return lines


def _install_body(product: Product) -> list[str]:
    """Return the ``install`` method, which renames the triple-suffixed assets."""
    primary, *rest = product.executables
    lines = [
        "  def install",
        # Composed from two ternaries rather than a multi-line `if` assignment:
        # the assets are named by Rust target triple, and this shape states the
        # OS and CPU halves separately without tripping `brew style`'s end
        # alignment rules on an assignment whose right side is a block.
        '    vendor = OS.mac? ? "apple-darwin" : "unknown-linux-gnu"',
        '    arch = Hardware::CPU.arm? ? "aarch64" : "x86_64"',
        '    triple = "#{arch}-#{vendor}"',
        "",
        f'    bin.install "{primary.name}-#{{triple}}" => "{primary.name}"',
    ]
    for executable in rest:
        lines.extend(
            [
                "",
                f'    resource("{executable.name}").stage do',
                f'      bin.install "{executable.name}-#{{triple}}" '
                f'=> "{executable.name}"',
                "    end",
            ],
        )
    lines.append("  end")
    return lines


def _caveats_body(product: Product) -> list[str]:
    """Return a ``caveats`` method carrying the product's channel notes.

    The Homebrew counterpart of the Scoop manifest's ``notes``. Both channels
    render the same strings from the same Product, so a caveat that matters at
    install time - a GPU build that has to come from elsewhere, a binary that
    will not update itself - cannot reach one channel's users and not the
    other's.
    """
    if not product.notes:
        return []
    lines = ["  def caveats", "    <<~EOS"]
    lines.extend(f"      {note}" for note in product.notes)
    lines.extend(["    EOS", "  end"])
    return lines


def render(
    product: Product,
    version: str,
    digests: dict[str, str],
    available: tuple[str, ...] | None = None,
) -> str:
    """Return the formula as the exact bytes committed to ``Formula/``.

    ``available`` names the triples this release actually attached. A target
    the build matrix does not yet cover is omitted from the formula rather
    than emitted with an invented digest, so ``brew install`` reports an
    unsupported platform instead of failing a checksum.

    Defaulting to the product's own supported set - rather than to every
    triple Homebrew serves - means the renderer cannot offer a platform the
    product raises on, even when called without an explicit list.
    """
    if available is None:
        available = tuple(
            target for target in products.HOMEBREW_TARGETS if product.serves(target)
        )
    else:
        available = tuple(target for target in available if product.serves(target))
    primary = product.executables[0]
    lines = [
        f"class {product.formula_class} < Formula",
        f'  desc "{product.description}"',
        f'  homepage "{product.homepage}"',
        f'  version "{version}"',
        f'  license "{product.license}"',
        "",
        # Parity with the Scoop manifest's checkver stanza: both channels let
        # maintainer tooling discover the next release from the tag scheme.
        "  livecheck do",
        "    url :stable",
        f"    regex(/^{product.tag_prefix}(\\d+(?:\\.\\d+)+)$/i)",
        "    strategy :github_latest",
        "  end",
        "",
        *_os_blocks(product, version, digests, available),
        "",
        *_install_body(product),
        *([""] if product.notes else []),
        *_caveats_body(product),
        "",
        "  test do",
        # A cold launch on the installing machine, which is the whole of what
        # the binary now does: it carries its interpreter, the application and
        # every dependency, so this exercises the artifact rather than an
        # index. `brew test` runs it networked, so the offline property is not
        # what is proved here - .github/workflows/binaries.yml proves that
        # before the asset exists. This proves placement and startup.
        "    assert_match version.to_s, "
        f'shell_output("#{{bin}}/{primary.name} --version")',
        "  end",
        "end",
    ]
    return "\n".join(lines) + "\n"
