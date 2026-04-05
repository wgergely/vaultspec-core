# Changelog

## [0.1.7](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.6...vaultspec-core-v0.1.7) (2026-04-05)


### Features

* add pre-commit hook management to CLI install and sync ([f51fd0f](https://github.com/wgergely/vaultspec-core/commit/f51fd0f3f57a931d546efa391f9f6e92b3e83c7a)), closes [#29](https://github.com/wgergely/vaultspec-core/issues/29)
* pre-commit hook management via python CLI ([c2927d4](https://github.com/wgergely/vaultspec-core/commit/c2927d4711d3abf8da52c1c75ce4c464c4cffe17))
* robust gitignore management and lifecycle integration ([99a554f](https://github.com/wgergely/vaultspec-core/commit/99a554fd24c093ecaf969156324017a09337e281))
* robust gitignore management and lifecycle integration ([d6077c1](https://github.com/wgergely/vaultspec-core/commit/d6077c1674f32e0c2abb5db07740e250c5f2f8c9))


### Bug Fixes

* address code review findings for gitignore management ([317e04a](https://github.com/wgergely/vaultspec-core/commit/317e04a65a008ad414d6ced86cc424621f333cce))
* address codex and gemini code review findings ([cc8c01c](https://github.com/wgergely/vaultspec-core/commit/cc8c01cebf7ff904101e73f4983fe2165008d13d))
* address PR review feedback for pre-commit hooks ([83db5c9](https://github.com/wgergely/vaultspec-core/commit/83db5c972b8a8f51cfcfe0affed7e09f4fa54a1a))
* use valid CLI commands in scaffolded pre-commit hooks ([9e96b41](https://github.com/wgergely/vaultspec-core/commit/9e96b41e01d9d83028ed0b7f51365d66d7589d72))

## [0.1.6](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.5...vaultspec-core-v0.1.6) (2026-04-03)


### Features

* add announce pattern and Diataxis classification mandate ([4c22b78](https://github.com/wgergely/vaultspec-core/commit/4c22b78046248c66e4751d7586660270af6a9125))
* add vaultspec-cli built-in rule for agent CLI awareness ([44a435b](https://github.com/wgergely/vaultspec-core/commit/44a435b50d57f8c68ae6f2c4b60f4ecd29589d1d))
* add vaultspec-documentation to builtin skill list ([89e6e7d](https://github.com/wgergely/vaultspec-core/commit/89e6e7d721454cbb5b57d08565503fbc1cf7030b))
* provider-centric sync output with per-tool result tracking ([b63004b](https://github.com/wgergely/vaultspec-core/commit/b63004b7776a15ad44d12622c6a9a6f31de0aa43))
* recover vaultspec-documentation skill ([b4a4eba](https://github.com/wgergely/vaultspec-core/commit/b4a4eba3ee1559c0bd4fdc9febd51d24eda7758b))
* recover vaultspec-documentation skill from conversation history ([bcd3ecc](https://github.com/wgergely/vaultspec-core/commit/bcd3eccf5851bbd6884a9c19df95ab5a8ca03f56)), closes [#26](https://github.com/wgergely/vaultspec-core/issues/26)
* sync warns when bundled builtins are newer than deployed ([069e6f4](https://github.com/wgergely/vaultspec-core/commit/069e6f4d9db10f8ef5f615abebb13245ff10ecfd))
* universal --json output across all CLI commands ([726a641](https://github.com/wgergely/vaultspec-core/commit/726a6418caeba5b04ea4ceec9daa6417d133ade9))


### Bug Fixes

* audit findings phases 1-4 - data safety, error visibility, logic fixes, exception hardening ([ce4076d](https://github.com/wgergely/vaultspec-core/commit/ce4076dfaeaa602fa5c2b6d3b321af4417a090e3))
* audit findings phases 6-8 - security, filesystem hardening, UX polish ([d9bd6a1](https://github.com/wgergely/vaultspec-core/commit/d9bd6a1d3efd257bbdfee23fa357b75670a0400d))
* clarify Phase 1 user check vs Phase 2/3 approval gate ([97cf7eb](https://github.com/wgergely/vaultspec-core/commit/97cf7ebcc487e3df19d7a07ad80af18175299995))
* classify .vault/ feature index files as INDEX instead of unknown ([faad468](https://github.com/wgergely/vaultspec-core/commit/faad468a102b10777118c39920665ca49aedd328))
* correct broken reference to editorial-guidelines.md ([8c468a6](https://github.com/wgergely/vaultspec-core/commit/8c468a60b548f334cbb2d3a8c1a003e46e163bdc))
* doctor misreports config as missing, add MCP row ([a948c14](https://github.com/wgergely/vaultspec-core/commit/a948c14452425969548a4cca6add1b63ae9d9825))
* enable Codex rules_dir so rules sync and AGENTS.md references work ([65522fa](https://github.com/wgergely/vaultspec-core/commit/65522fa905a5cea3896e8e7b1d0d04fecb53c70c))
* enable system prompt delivery to Codex via vaultspec-system.builtin.md ([7f0ccf0](https://github.com/wgergely/vaultspec-core/commit/7f0ccf0b3ea049e692ea2812aad71d0f549a0dfa))
* false "partial" diagnosis for providers with skills directories ([a2ef784](https://github.com/wgergely/vaultspec-core/commit/a2ef784fc96d9cbfe5b49cd22f3472e0858ee880))
* features check renders empty warning header for INFO-only results ([018e521](https://github.com/wgergely/vaultspec-core/commit/018e521c54d2ca674ddd9afcc5879f969de00e8f))
* read-only gitignore test handles Linux CI root permissions ([0cd0495](https://github.com/wgergely/vaultspec-core/commit/0cd049555e256027032328b5ba4747bfe81aaa82))
* resolve all 91 audit findings from cli-ambiguous-states rolling audit ([7345d53](https://github.com/wgergely/vaultspec-core/commit/7345d530a7602c37ddb41c01eb403522e80cb0d9))
* unblock 113 erroring tests, update tests for Codex rules_dir changes ([05659e2](https://github.com/wgergely/vaultspec-core/commit/05659e2d6e9de6fa1daaf48cfedd9343751fc228))
* vault list validates doc_type, suggests vault feature list ([fa50639](https://github.com/wgergely/vaultspec-core/commit/fa506390c220ac7c68d0fed9a88dbd19e8911fd2))

## [0.1.5](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.4...vaultspec-core-v0.1.5) (2026-03-30)


### Features

* add --skip mcp flag and MCP repair to sync/upgrade ([31ea1ad](https://github.com/wgergely/vaultspec-core/commit/31ea1ad0edf24a911b641202edd1b0d0f3bc7416)), closes [#17](https://github.com/wgergely/vaultspec-core/issues/17)
* add check_dangling checker for unresolved wiki-links ([eac965d](https://github.com/wgergely/vaultspec-core/commit/eac965d537b97c1b4ff6d10382b4ef2bb7d61717))
* add phantom nodes to vault graph for unresolved wiki-links ([4450b52](https://github.com/wgergely/vaultspec-core/commit/4450b5244d3017d3bf50c31095787a805b785cb6))
* add research, ADRs, and plan for CLI ambiguous states ([#16](https://github.com/wgergely/vaultspec-core/issues/16)) ([d2f4c3c](https://github.com/wgergely/vaultspec-core/commit/d2f4c3c3957a86fba2a998a3eeb5ce36ea45e099))
* add resolver engine and doctor command (phase 3) ([3549f96](https://github.com/wgergely/vaultspec-core/commit/3549f96ef63bb5dbd71a6b699b03423ab6cdbbcc))
* add signal enums, manifest v2.0, and gitignore module (phase 1) ([e7335b3](https://github.com/wgergely/vaultspec-core/commit/e7335b3aa10ccd33e4a53b3bbbcf85d5addbbb13))
* add WorkspaceFactory test condition generator engine ([7ec1a9e](https://github.com/wgergely/vaultspec-core/commit/7ec1a9e5a2afb6b2579260687f45ccece855bf60))
* CLI ambiguous state detection and resolution engine ([#16](https://github.com/wgergely/vaultspec-core/issues/16)) ([fcce2fa](https://github.com/wgergely/vaultspec-core/commit/fcce2fa11eeec1a272e352a38b0a25ab8f8439fe))
* implement resolver executor - preflight now executes repair steps ([9337ea5](https://github.com/wgergely/vaultspec-core/commit/9337ea5cdf20c1fc86dcb86ae3788647bbee2ed6))
* implement signal collectors and diagnose orchestrator (phase 2) ([7345fce](https://github.com/wgergely/vaultspec-core/commit/7345fcef5f2a1fd828c375e493ae4f3db4e9bb39))
* MCP .mcp.json installation controllable via CLI ([1671912](https://github.com/wgergely/vaultspec-core/commit/1671912a0808c1a3e77819a0b5c1ecc2e4257c47))
* phantom nodes, dangling-link checker, graph hardening ([#19](https://github.com/wgergely/vaultspec-core/issues/19)) ([6e42663](https://github.com/wgergely/vaultspec-core/commit/6e426630abcf59db7441f893a253dc9816b772fc))
* wire gitignore, manifest v2.0, and integration tests (phase 4) ([4529145](https://github.com/wgergely/vaultspec-core/commit/452914577a6f19ead90aa77d3feb656a5b41ab4b))
* wire resolver pre-flight into install/sync/uninstall commands ([a5edfe7](https://github.com/wgergely/vaultspec-core/commit/a5edfe72add398e02e09e93f94b3c3d4e542934d))


### Bug Fixes

* address code review findings for phase 1 ([6ae7e8f](https://github.com/wgergely/vaultspec-core/commit/6ae7e8fdd6503497f1b42d7d2e111b21f443f03f))
* address critical and high audit findings ([bb560b1](https://github.com/wgergely/vaultspec-core/commit/bb560b11de65407f39325b0c4c2a4fc82adc0c02))
* address medium audit findings and fill test gaps ([105ea84](https://github.com/wgergely/vaultspec-core/commit/105ea843af3edcae671e365361a5330a83456ea5))
* address phase 3 code review findings ([cb13236](https://github.com/wgergely/vaultspec-core/commit/cb132366a25832c915d66a89d7df6e02bfd0aaba))
* Phase A data safety - rmtree_robust, mcp.json surgical, uninstall ordering ([f78c666](https://github.com/wgergely/vaultspec-core/commit/f78c66687c662681cf768b5016223d6a24837a57))
* Phase B error visibility - SyncResult.errors display, OSError catches ([1190d51](https://github.com/wgergely/vaultspec-core/commit/1190d518577361980194dde10f36268c7b5ce736))
* Phase C flag/logic - upgrade+dry-run precedence, skip core guard, sync isolation ([76d7339](https://github.com/wgergely/vaultspec-core/commit/76d73390e2de00f7de0938b1006ef6a59e827952))
* remove all mock/patch usage, skips, and suppression comments ([39714a2](https://github.com/wgergely/vaultspec-core/commit/39714a27fec20ef727862604762120983c4e3701))
* replace pytest.skip with assert in graph collision test ([844a17d](https://github.com/wgergely/vaultspec-core/commit/844a17d672af1f501a7a06e95ad14ad9208c730d))
* resolve all dangling wiki-links and enable pre-commit hook ([406e6c5](https://github.com/wgergely/vaultspec-core/commit/406e6c568adaba6b82a9e73a8780ae6c622dc4b0))
* scaffold chicken-and-egg bug, harden dev-repo guard, remove dead tests ([7d6468e](https://github.com/wgergely/vaultspec-core/commit/7d6468e7b46d894a21bd9f7056c0b104709f646c))
* scaffold chicken-and-egg bug, harden dev-repo guard, remove dead tests ([#19](https://github.com/wgergely/vaultspec-core/issues/19)) ([68b882a](https://github.com/wgergely/vaultspec-core/commit/68b882a3e51a5bdd8e33eca00396ec01ce797c2c))

## [0.1.4](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.3...vaultspec-core-v0.1.4) (2026-03-23)


### Bug Fixes

* index generator now produces mdformat-compatible output ([bbc39d9](https://github.com/wgergely/vaultspec-core/commit/bbc39d963a59da98f2e55e2ba32a870e40dbe939))
* remove obsolete protocol/agent/a2a/codex vault docs and gitignore .obsidian ([e0de872](https://github.com/wgergely/vaultspec-core/commit/e0de87215134c238647c0229f217b46e5c4980df))
* resolve all remaining vault warnings to achieve full green ([0dff977](https://github.com/wgergely/vaultspec-core/commit/0dff9771d26ebfcee1252fb2b9f330ae67cc07c3))
* skip HTML comments in body-link checker and wiki-link extractor ([1506830](https://github.com/wgergely/vaultspec-core/commit/1506830a0ca993e2d62c5715405cccd432f30113))

## [0.1.3](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.2...vaultspec-core-v0.1.3) (2026-03-23)


### Features

* release pipeline - versioning, PyPI publishing, GitHub Releases ([a8b4712](https://github.com/wgergely/vaultspec-core/commit/a8b47121ca639859f4e5cb2489b89c8df89d9887))


### Bug Fixes

* add workflow_dispatch to publish, fix deprecated action ([6fa1b88](https://github.com/wgergely/vaultspec-core/commit/6fa1b88b6a528cbf81a104cf187d1e44e1f1caa7))

## [0.1.2](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.1...vaultspec-core-v0.1.2) (2026-03-23)


### Bug Fixes

* expose __version__ on package, simplify version discovery ([f8a69e5](https://github.com/wgergely/vaultspec-core/commit/f8a69e51302af9931ad58b653004771472ffd694))

## [0.1.1](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.0...vaultspec-core-v0.1.1) (2026-03-23)


### Features

* A2A phases 3-6 + test quality overhaul ([2d3835c](https://github.com/wgergely/vaultspec-core/commit/2d3835cf233c002cca5584697fda50bac0105b4b))
* a2a-team coordinator + commit-hook compliance ([cbeb998](https://github.com/wgergely/vaultspec-core/commit/cbeb9983bd98850324619d53bbf826b9cb8e0f08))
* add --target to every CLI subcommand and remove vault doctor ([d93f9f9](https://github.com/wgergely/vaultspec-core/commit/d93f9f9a71a717ca7206c5b8f3e19495f0807205))
* add &lt;vaultspec&gt; tag parser for managed content blocks ([624d4dd](https://github.com/wgergely/vaultspec-core/commit/624d4ddfefcae18d7be0441cfa5a8e10c3f72092))
* add CI/CD pipeline, Docker packaging, justfile task runner, and automation contract tests ([4b434d6](https://github.com/wgergely/vaultspec-core/commit/4b434d6e51f7fc9c216addc5fa214cf0a70935ac))
* add feature archive mechanism (moves docs to .vault/_archive/) ([1c19572](https://github.com/wgergely/vaultspec-core/commit/1c1957224a52aadaf82ce03caa18f084ac94355a))
* add install/uninstall commands, replace sync-all with provider-aware sync ([56bbeb0](https://github.com/wgergely/vaultspec-core/commit/56bbeb041f4ef32ad56938a885e6d70da5a6d899))
* add mcp.json config, ToolAnnotations, ToolError, and comprehensive MCP tests ([8f7ec2f](https://github.com/wgergely/vaultspec-core/commit/8f7ec2ff1df44e27c10401db99b42e39b0a76305))
* add ProviderCapability enum, fix provider file locations per grounding research ([bc68277](https://github.com/wgergely/vaultspec-core/commit/bc682770dfd891e37442d19d4f2c5933a36a5439))
* add release pipeline with release-please and uv publish ([ac52bca](https://github.com/wgergely/vaultspec-core/commit/ac52bca017334c377102ca2146a4b4bcce01992d))
* add revert mechanism for builtin resources with snapshot-on-install ([80486a6](https://github.com/wgergely/vaultspec-core/commit/80486a6ed72cabb224e4e75810970375889c4403))
* add Rich tree renderer for dry-run previews with colour-coded status categories ([0d31b9a](https://github.com/wgergely/vaultspec-core/commit/0d31b9a7b6dcbbdc3749fc87575821b9d520ce37))
* add sync provider validation and capability contract tests ([07eee63](https://github.com/wgergely/vaultspec-core/commit/07eee63f5bd536115232d5c23039399646f447f5))
* add vault check engine with fix support in vaultcore ([8a2b7d7](https://github.com/wgergely/vaultspec-core/commit/8a2b7d7ddf5bce4151c2b594c4edbfa928587a03))
* add vault query engine for stats, list, and feature detail operations ([b448cc0](https://github.com/wgergely/vaultspec-core/commit/b448cc09ee64c8fe71ae4c483c70957e42d69d39))
* align provider API surface and fix silent feature gaps ([f7dd6eb](https://github.com/wgergely/vaultspec-core/commit/f7dd6eb5f798fd6999cf0f2dafd37e26562f8f09))
* align RAG dependency stack with CUDA 13.0 frontier mandate ([4dc0d95](https://github.com/wgergely/vaultspec-core/commit/4dc0d95b64b2a2e023dbecc3a0746e5fc783d483))
* complete Codex Phase 4 verification coverage, remove dead Tool.AGENTS enum ([1d8f9e5](https://github.com/wgergely/vaultspec-core/commit/1d8f9e5943a2ebbbe58e64607fc1eed7e8161577))
* eliminate global mutable state and optimize check engine I/O ([f814b3a](https://github.com/wgergely/vaultspec-core/commit/f814b3aad2d5e900ae05d7d1c3678c808790415a))
* enhance unified CLI with early init handling and error recovery ([8eaebcf](https://github.com/wgergely/vaultspec-core/commit/8eaebcfdbb8535b155033953f504eef7e7ed88f9))
* execute roadmap Waves 0-5 — bugs, docs, CLI, ecosystem, tests ([9a94045](https://github.com/wgergely/vaultspec-core/commit/9a9404537962d7942cd3162aa8bc7901e8ba5177))
* formalize modular .docs vault API and implement docs.py CLI ([c3536ac](https://github.com/wgergely/vaultspec-core/commit/c3536ac65c6ce82ff4fb1c712d04a30796973424))
* harden hooks engine — process safety, dedup, re-entrant guard ([a23ec9b](https://github.com/wgergely/vaultspec-core/commit/a23ec9b4fe5c3e90378ff92bae452e96c8ffbfab))
* implement A2A server management foundation and centralize enums ([2952158](https://github.com/wgergely/vaultspec-core/commit/29521581a169e6a6e96c104759e8fb21d3aa6410))
* implement all 7 ACP bridge stubs, split monolithic tests, fix quality issues ([9077e96](https://github.com/wgergely/vaultspec-core/commit/9077e962e48c0b1cc7a988f593265102c94cc200))
* implement local RAG pipeline with LanceDB and nomic-embed-text-v1.5 ([440d2c5](https://github.com/wgergely/vaultspec-core/commit/440d2c50ec3860b09ec45286b45ee458ad6804d2))
* implement rigid vault types and remove numbered list styles ([686bf0c](https://github.com/wgergely/vaultspec-core/commit/686bf0cb88b6dcd2b97fed2b0941d8c3d07409d7))
* implement Synthetic RAG via sophisticated LLM dispatch ([9aafadb](https://github.com/wgergely/vaultspec-core/commit/9aafadbba0ea8b4425beafbe4c28196e25b9766d))
* implement vertical integrity check for feature plans ([c010818](https://github.com/wgergely/vaultspec-core/commit/c010818f32f01f9e3e780ba517150baab3fcab0d))
* improve logging infrastructure with debug-aware formatting ([ecf1276](https://github.com/wgergely/vaultspec-core/commit/ecf12767542599f9a83e62c009a895bcaa940441))
* install --force overrides existing, --dry-run uses Rich tree renderer ([c98b8a3](https://github.com/wgergely/vaultspec-core/commit/c98b8a3c73f2f4cc2a024339cf5efb01ce723dda))
* integrate &lt;vaultspec&gt; tag system into config_gen and agents sync ([57fa834](https://github.com/wgergely/vaultspec-core/commit/57fa8349a8ab7d744963e0a58843e01a42d35dd6))
* make Claude a viable A2A team member — executor hardening, team tools, process spawning ([91086e5](https://github.com/wgergely/vaultspec-core/commit/91086e58d4970b872442e30edd92eb56b98ae29e))
* migrate and formalize project structure with rules, docs, and scripts ([4392dd2](https://github.com/wgergely/vaultspec-core/commit/4392dd2a2a0c5f643a4edc60cc6c4477437d2b2a))
* P0+P1 release readiness — license, packaging, README, CI, marketing audit ([0ed09a8](https://github.com/wgergely/vaultspec-core/commit/0ed09a81abd0a5953a69916a9564f3d55e96bf31))
* P2 + enforce all markdownlint rules across entire project ([c443db1](https://github.com/wgergely/vaultspec-core/commit/c443db1580bc22d209e0659d2934393e4129b989))
* provider-scoped install/uninstall with dry-run and shared dir protection ([5afbe53](https://github.com/wgergely/vaultspec-core/commit/5afbe53d8f0565f41adf48e01b5ea67631151552))
* rename dev format to dev fix and add vault autofix target ([48a96f0](https://github.com/wgergely/vaultspec-core/commit/48a96f0b4bd1ce7faebf924e8ac8b517cda944a8))
* revise config_gen with secondary config, TOML adapter, unified AGENTS.md ([80b5f74](https://github.com/wgergely/vaultspec-core/commit/80b5f74b12eaac92270810522bf301c588064cd4))
* three-path workspace decoupling with git-aware layout detection ([d06b710](https://github.com/wgergely/vaultspec-core/commit/d06b71071304e47293102b55d64b0013377b8124))
* uninstall requires --force safety gate, core uninstall cascades to all ([64b3e2d](https://github.com/wgergely/vaultspec-core/commit/64b3e2dd7210e8523aa360428fde360b382b2356))
* vault add --related/--tags, input guards, resolve engine, template hydration, and framework content updates ([168e161](https://github.com/wgergely/vaultspec-core/commit/168e16180cc420b68212e15839cfcdaff50815d3))
* **vault-doctor-suite:** add research, ADR, and plan for doctor suite ([316f4cc](https://github.com/wgergely/vaultspec-core/commit/316f4cce24286f7bdc1623c73ee682b2e43c627d))
* Wave 6 strategic features + system prompt restructure ([79083d7](https://github.com/wgergely/vaultspec-core/commit/79083d7c6b973b977a6109c0fbfe40c1040d97f4))
* Wave 6 strategic features + system prompt restructure ([b3783fa](https://github.com/wgergely/vaultspec-core/commit/b3783fa0333ddb499f4cc31f245496a0d8766504))
* wire provider features through full stack (max_turns, budget, effort, tools) ([0aa0512](https://github.com/wgergely/vaultspec-core/commit/0aa0512813c8d1eddd668e5a6ae0042ffbb0c45b))
* wire vault command stubs to backend (stats, list, add, feature, doctor) ([21a60de](https://github.com/wgergely/vaultspec-core/commit/21a60deccfb2b5eb1da2dae695daf1fc77d4b63b))


### Bug Fixes

* ACP handshake + Gemini CLI integration for subagent protocol ([700215f](https://github.com/wgergely/vaultspec-core/commit/700215fb9dccc5dd60d3b83ffbcc3ef3c4cb1d25))
* address code review findings for install/uninstall commands ([46d7611](https://github.com/wgergely/vaultspec-core/commit/46d76111218e1b98bf485411885e0e4be4b66982))
* avoid MCP binary locking in dev environment ([#6](https://github.com/wgergely/vaultspec-core/issues/6)) ([18d13bc](https://github.com/wgergely/vaultspec-core/commit/18d13bc8ab31f6e0c69969b0074558910d22e9b6))
* broken CI - test imports, lychee links, and vault schema errors ([d744b0f](https://github.com/wgergely/vaultspec-core/commit/d744b0f3a4545acb90b9dc9a3c7b27abe51d90ad))
* clean up subagent CLI output and resolve Windows pipe error ([b4c30c3](https://github.com/wgergely/vaultspec-core/commit/b4c30c3a860bf2bb3a079ef6d00526b8e8e07f74))
* code review fixes, platform compat, stale tests, and vault doc linting ([ccc7a0d](https://github.com/wgergely/vaultspec-core/commit/ccc7a0dcc662378cd2e018e3654b839314de70fb))
* correct Codex rules — behavioral rules via AGENTS.md, not Starlark ([cc98461](https://github.com/wgergely/vaultspec-core/commit/cc98461c36a36c479940e51559075ab6a8af6c46))
* correct Codex rules from TOML to Starlark, update all docs ([9adc84a](https://github.com/wgergely/vaultspec-core/commit/9adc84a20e685ad9407dfc28a6fe259af8fa8524))
* correct TEST_PROJECT path in RAG unit test conftest ([208093a](https://github.com/wgergely/vaultspec-core/commit/208093ac3fa1782f16bfa6746f3aa5a4da7b8e1b))
* Dockerfile missing .vaultspec/ copy for force-include build ([d0a7830](https://github.com/wgergely/vaultspec-core/commit/d0a7830ec88e7d829dfe054dacbfbf28e5c2b8af))
* drop dev extra from extension.toml install command ([85cdc31](https://github.com/wgergely/vaultspec-core/commit/85cdc31fbf926714646ac2672f974d198bcf51d8))
* dry-run uses backend scaffold functions, uninstall populates TOOL_CONFIGS ([df74d76](https://github.com/wgergely/vaultspec-core/commit/df74d76c48f599d6a5c271c1d378a410fedcfff3))
* enforce terminal sandbox in read-only mode for both ACP providers ([1bea7e1](https://github.com/wgergely/vaultspec-core/commit/1bea7e141a32d83cd1378bce499e0938281048f8))
* force Typer COLOR_SYSTEM=None in CLI tests to prevent ANSI on CI ([8da5a36](https://github.com/wgergely/vaultspec-core/commit/8da5a36824547e28527f78cc7e914d6013c0d987))
* handle stem collisions in graph API and guard vault add uniqueness ([964ec29](https://github.com/wgergely/vaultspec-core/commit/964ec29b2d10bdb25b5f20922757a03c3f0b6f6e))
* harden dev toolchain, add precommit recipe, and align tests with namespaced justfile ([0c01901](https://github.com/wgergely/vaultspec-core/commit/0c0190109a9a5e3d524670498ee4ac140303ede7))
* harden Gemini ACP bridge, implement tool proxying, and fix session resume ([f510a34](https://github.com/wgergely/vaultspec-core/commit/f510a34d947b1178b1cc1309c1f0b53de924a846))
* harden input validation and purge unittest imports from codebase ([d3cd9c2](https://github.com/wgergely/vaultspec-core/commit/d3cd9c2e109888508a0e7ddd70bed040eb11618d))
* isolate session-scoped RAG test fixtures and regenerate lockfile ([c9a78b9](https://github.com/wgergely/vaultspec-core/commit/c9a78b9310f35a60565111fdde2d9518f2033a8e))
* make antigravity a standalone sync target ([08e3bfb](https://github.com/wgergely/vaultspec-core/commit/08e3bfb0e66f4a5bad0b9a7573b5cc970f55d540))
* make pre-commit hooks read-only to prevent stash/restore conflicts ([1578963](https://github.com/wgergely/vaultspec-core/commit/157896344843077dd9df3804e971703daaf97b07))
* make version test release-agnostic ([acea1f6](https://github.com/wgergely/vaultspec-core/commit/acea1f64d16b04bbf3d033910e631348860780af))
* orphan detection checks graph connectivity, not just incoming links ([f8f9861](https://github.com/wgergely/vaultspec-core/commit/f8f9861812044dcca18691eab504454b67686f9c))
* post-review fixes for context isolation, graph I/O, and test state ([ae4ff5d](https://github.com/wgergely/vaultspec-core/commit/ae4ff5d12938ce941e364e52392ad4139705a06e))
* prevent Unicode crash on Windows cp1252 terminals ([22da13a](https://github.com/wgergely/vaultspec-core/commit/22da13a5bffc2bcb8dd1a025f625e04844da3c80))
* regenerate uv.lock on release-please branch ([60a2d65](https://github.com/wgergely/vaultspec-core/commit/60a2d652190ee070bd3d61c0b0e20ae02cafc1fb))
* remove --verbose, fix --target help text, suppress typer completions ([3198905](https://github.com/wgergely/vaultspec-core/commit/319890514e0aad4457ff0a21146cb98237a71a8e))
* remove .agents folder from git tracking and add to .gitignore ([f6785ea](https://github.com/wgergely/vaultspec-core/commit/f6785ea3d41b33daad91fb349fd90e535c7763b3))
* remove accidentally committed pycache files and fix .gitignore ([392af79](https://github.com/wgergely/vaultspec-core/commit/392af793fa7387e9e44196aa899371b92b93202e))
* remove stale type-ignore comments and redundant ty root path ([ae55523](https://github.com/wgergely/vaultspec-core/commit/ae55523c272be55e0ac7f6f4132fc4fdbb5b658b))
* repair CI pipeline — actionlint, lychee, ANSI test output, and add python build ([3652c0b](https://github.com/wgergely/vaultspec-core/commit/3652c0b796ad0cf6f443cae896a307e4cab68c80))
* resolve 3 pre-existing test failures and harden Printer JSON output ([7e5c222](https://github.com/wgergely/vaultspec-core/commit/7e5c222555f57aac09aca15f7abd357f6aeb1383))
* resolve ACP handshake issues and align test suite with real-service models ([201602a](https://github.com/wgergely/vaultspec-core/commit/201602a31d49c176352e00b1a402b2547351b663))
* resolve ANSI codes in CI tests, lychee paths, and cross-platform pre-commit ([9a25d2e](https://github.com/wgergely/vaultspec-core/commit/9a25d2eba473e23a74ad104eb4aa1372c1bffe2e))
* resolve lychee link-check failures ([8dc8150](https://github.com/wgergely/vaultspec-core/commit/8dc8150c140342d732d7a581e62b1370b46a617a))
* robustify Claude ACP bridge and enhance E2E verification ([c046db4](https://github.com/wgergely/vaultspec-core/commit/c046db45c375611d12cada3ccbed840b0684a028))
* ruff violations, correctness bugs, and broken test import ([72217d8](https://github.com/wgergely/vaultspec-core/commit/72217d8e6b0316fe59bfa643aa1a1dbaa159d3ac))
* set NO_COLOR at module level in CLI conftest, relax markdownlint rules ([1ff7d8e](https://github.com/wgergely/vaultspec-core/commit/1ff7d8ee7a36a1c43bc272098a12ed7501f85b8c))
* set NO_COLOR globally in CI, fix broken link, fix pre-commit hooks ([170f1f7](https://github.com/wgergely/vaultspec-core/commit/170f1f77038f02dcb12b5825663d9494004fdf78))
* set NO_COLOR in CI test step and exclude vault audit/research from lychee ([0e67038](https://github.com/wgergely/vaultspec-core/commit/0e67038e08bfb6e615a5511f18b124def3ff09f9))
* shared resource protection and archive exclusion from scans ([ba893f7](https://github.com/wgergely/vaultspec-core/commit/ba893f7d72eaf15b40b75d59bc2e31349d54a5ce))
* sync_to_all_tools respects provider manifest instead of syncing all configured tools ([fa1065b](https://github.com/wgergely/vaultspec-core/commit/fa1065bbf9bb1a594c972c7f5c7557863fb3ebc9))
* use proper system prompt channels and populate agent capabilities ([9826e09](https://github.com/wgergely/vaultspec-core/commit/9826e094715a386289c5ba92fc4abde927c5101a))
* vault curation - workspace bug, stale artifacts, frontmatter compliance ([9b7f87d](https://github.com/wgergely/vaultspec-core/commit/9b7f87d7e3c26516682f17bff0104e1ba1098f5a))
* YAML parser fallback, update stale model names, consolidate provider tests ([a6b78a7](https://github.com/wgergely/vaultspec-core/commit/a6b78a7a08f41096cec519c87b845e51fc2e3f3c))


### Performance

* optimize RAG pipeline with caching, concurrency, and safety fixes ([d92f463](https://github.com/wgergely/vaultspec-core/commit/d92f4637dcda14dc52acc216db93fd19e86d02a0))
