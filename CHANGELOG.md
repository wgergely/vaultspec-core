# Changelog

## [0.1.74](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.73...vaultspec-core-v0.1.74) (2026-09-06)


### Features

* **agents:** render Antigravity subagents to .agents/agents/ ([#491](https://github.com/nevenincs/vaultspec-core/issues/491)) ([163b104](https://github.com/nevenincs/vaultspec-core/commit/163b104d91c88e30ada2eaed0c36810b309ec147)), closes [#488](https://github.com/nevenincs/vaultspec-core/issues/488)
* **harness:** size work by horizon, make the ledger the only execution artifact, and rewrite the corpus ([#422](https://github.com/nevenincs/vaultspec-core/issues/422)) ([f755314](https://github.com/nevenincs/vaultspec-core/commit/f755314cf3b6e9eb0f356093332d7800d5312fab))
* **migrations:** a safety net under every destructive migration ([#473](https://github.com/nevenincs/vaultspec-core/issues/473)) ([b7e0613](https://github.com/nevenincs/vaultspec-core/commit/b7e06137251e2b4a5d4d4b749decfcf70de05666))
* **spec:** declare a managed-block opt-out where a teammate can read it ([ce01c68](https://github.com/nevenincs/vaultspec-core/commit/ce01c684cd9edb9f5d3bb06f37b1531861483ad8))
* **vault:** warn about foreign files in .vaultspec/ and .vault/ ([#484](https://github.com/nevenincs/vaultspec-core/issues/484)) ([149469a](https://github.com/nevenincs/vaultspec-core/commit/149469a81f1228116f1d4f3b71f29af5982e5a65)), closes [#450](https://github.com/nevenincs/vaultspec-core/issues/450)


### Bug Fixes

* **boundary:** move the ADR linkage out of source and into the ADR ([dd910e9](https://github.com/nevenincs/vaultspec-core/commit/dd910e953f059f388c71e26281e922e6f44d02c8))
* **ci:** the main sentinel closed its issue on a pending verdict ([8e87193](https://github.com/nevenincs/vaultspec-core/commit/8e8719348261dd568eb66195d1002de564485b1a))
* **cli:** a printed next action that could not be run as printed ([1e43af3](https://github.com/nevenincs/vaultspec-core/commit/1e43af3b85c1557c6710ae0009370cc186c4c76b))
* **cli:** epic intent show raised a traceback where its sibling reports an error ([f0f6d5c](https://github.com/nevenincs/vaultspec-core/commit/f0f6d5c506f7d74fe462e18ce4162b65337ba2c2))
* **cli:** status --json emits vaultspec.error.v1 on workspace/target failures ([#448](https://github.com/nevenincs/vaultspec-core/issues/448)) ([06bb09c](https://github.com/nevenincs/vaultspec-core/commit/06bb09cafc7ab4a2cece0702a6a1255b18cb69c4))
* **cli:** the precommit row read as a promise that git would run the hooks ([34afb5a](https://github.com/nevenincs/vaultspec-core/commit/34afb5ac558a18624cbde01d3592d10167de3639))
* **cli:** the status hint promised vault checks that spec doctor does not run ([5b3336e](https://github.com/nevenincs/vaultspec-core/commit/5b3336e341865531c2bcb50757ef58fcb6c06bc5))
* coerce non-mapping frontmatter and load sync hooks from the target ([#468](https://github.com/nevenincs/vaultspec-core/issues/468)) ([4aacf6d](https://github.com/nevenincs/vaultspec-core/commit/4aacf6d45f7cd5b6dac6649871f8da33dd5fe141)), closes [#460](https://github.com/nevenincs/vaultspec-core/issues/460) [#461](https://github.com/nevenincs/vaultspec-core/issues/461)
* **core:** refuse a symlinked destination instead of severing it silently ([#438](https://github.com/nevenincs/vaultspec-core/issues/438)) ([3f5c3ea](https://github.com/nevenincs/vaultspec-core/commit/3f5c3eaca5d167330bad6226f73b3d2a6db84ed1)), closes [#413](https://github.com/nevenincs/vaultspec-core/issues/413)
* **core:** stop a read-only destination leaking the atomic-write temporary ([#427](https://github.com/nevenincs/vaultspec-core/issues/427)) ([7bf35b1](https://github.com/nevenincs/vaultspec-core/commit/7bf35b13be3b822a24260a121c61cd08cbfcf85c)), closes [#412](https://github.com/nevenincs/vaultspec-core/issues/412)
* **docs:** name the entry point in the two bare spec-group references ([#434](https://github.com/nevenincs/vaultspec-core/issues/434)) ([b290d2a](https://github.com/nevenincs/vaultspec-core/commit/b290d2a90c722b3f404e586f5ac15a9e2403759f))
* **docs:** reflow the three files that broke main's markdown gate ([#447](https://github.com/nevenincs/vaultspec-core/issues/447)) ([928f734](https://github.com/nevenincs/vaultspec-core/commit/928f734841f204e9d48072ee2c8bcb401d0cdd88))
* **doctor:** a check that could not read the file reported it was fine ([acf9775](https://github.com/nevenincs/vaultspec-core/commit/acf9775316b9a3ae69864bde4fe1ac2c7e4ff5a7))
* **doctor:** an unprotected workspace was reported as information ([6abae4a](https://github.com/nevenincs/vaultspec-core/commit/6abae4afc9eb91b5888ff851b4536549edfa1304))
* **doctor:** precommit reported ok while no hook could run ([68cb6d2](https://github.com/nevenincs/vaultspec-core/commit/68cb6d2c3d7ca6a99949f8f97e9928761105a462))
* **doctor:** report that a check could not run, instead of that it passed ([#435](https://github.com/nevenincs/vaultspec-core/issues/435)) ([19cb11b](https://github.com/nevenincs/vaultspec-core/commit/19cb11b560e07bc8726cac30ea7033fcc0574d82)), closes [#407](https://github.com/nevenincs/vaultspec-core/issues/407)
* **doctor:** stop an undecodable managed file crashing, and weigh the mcp row ([#441](https://github.com/nevenincs/vaultspec-core/issues/441)) ([d166566](https://github.com/nevenincs/vaultspec-core/commit/d166566a5e5c0adf0efb32b8687d8ce22314d4c9))
* **editor:** validate the editor command and close it off from the gateway ([#479](https://github.com/nevenincs/vaultspec-core/issues/479)) ([396969b](https://github.com/nevenincs/vaultspec-core/commit/396969be50cce0f469889b6e58772fe17331535f))
* **executor:** derive the managed flags on repair instead of assuming defaults ([#430](https://github.com/nevenincs/vaultspec-core/issues/430)) ([ad7e5e0](https://github.com/nevenincs/vaultspec-core/commit/ad7e5e0782bc208d0a4f4cc23768d1505d5edf66)), closes [#411](https://github.com/nevenincs/vaultspec-core/issues/411)
* **fold:** never delete a record on a path where the write was skipped ([#471](https://github.com/nevenincs/vaultspec-core/issues/471)) ([388c4e1](https://github.com/nevenincs/vaultspec-core/commit/388c4e1ca588cff1c06573f8e53095d0764701ae)), closes [#452](https://github.com/nevenincs/vaultspec-core/issues/452) [#453](https://github.com/nevenincs/vaultspec-core/issues/453)
* **gitignore:** the block listed sentinels it had already been asked to write ([0d1019e](https://github.com/nevenincs/vaultspec-core/commit/0d1019ee38d7c053a799ffc408f2f94c3f9a35ba))
* **guards:** a link to uv's install page is also an answer ([8dbe52d](https://github.com/nevenincs/vaultspec-core/commit/8dbe52d061c8f724a4ea915ac6c48b17826dbf5d))
* **guards:** a link to uv's install page is also an answer ([1572642](https://github.com/nevenincs/vaultspec-core/commit/1572642383d5777e15179276e1c6a475ea16745a))
* **hooks:** require operator consent before running workspace hooks (GHSA-w5xf-54cr-fxcq) ([#470](https://github.com/nevenincs/vaultspec-core/issues/470)) ([8d275a9](https://github.com/nevenincs/vaultspec-core/commit/8d275a9cefd0d146dae65993e9028ed7d29856d5))
* **install:** protect a workspace that starts with no .gitignore ([a6fc9bd](https://github.com/nevenincs/vaultspec-core/commit/a6fc9bda94bc5792c2b741c0cf21a945a535d847))
* **install:** roll the manifest back when an install does not complete ([#432](https://github.com/nevenincs/vaultspec-core/issues/432)) ([583f056](https://github.com/nevenincs/vaultspec-core/commit/583f0566e2797808d2c1407a56b96476b76032b3)), closes [#416](https://github.com/nevenincs/vaultspec-core/issues/416)
* **install:** surface the sync errors it records, and let them set the code ([#437](https://github.com/nevenincs/vaultspec-core/issues/437)) ([1b4d5c3](https://github.com/nevenincs/vaultspec-core/commit/1b4d5c3cc42f5c49a0537fb5a19df75da904e1b9)), closes [#414](https://github.com/nevenincs/vaultspec-core/issues/414)
* **install:** withhold the sharing policy where there is no repository ([#426](https://github.com/nevenincs/vaultspec-core/issues/426)) ([9fc4c03](https://github.com/nevenincs/vaultspec-core/commit/9fc4c0346f33b08e39b3d6cfe91313b093fe3c18)), closes [#419](https://github.com/nevenincs/vaultspec-core/issues/419)
* **integrity:** refuse a corrupt manifest, restore rollbacks atomically ([#469](https://github.com/nevenincs/vaultspec-core/issues/469)) ([9598efd](https://github.com/nevenincs/vaultspec-core/commit/9598efd9de7568829e58a7a336b66ca763c0f8be))
* **locks:** bound advisory_lock on both layers; propose the cycle fix in an ADR ([#476](https://github.com/nevenincs/vaultspec-core/issues/476)) ([7d31342](https://github.com/nevenincs/vaultspec-core/commit/7d313424fa252df7d1dc952bfc34a33e61998c13)), closes [#457](https://github.com/nevenincs/vaultspec-core/issues/457)
* **manifest:** hold the lock across the read-modify-write cycles that skipped it ([#436](https://github.com/nevenincs/vaultspec-core/issues/436)) ([e738ca2](https://github.com/nevenincs/vaultspec-core/commit/e738ca2e85701e01b18fc223cb7bdc7f20ca07e5)), closes [#418](https://github.com/nevenincs/vaultspec-core/issues/418)
* **mcps:** stop sync adopting the bytes it declined to write ([#428](https://github.com/nevenincs/vaultspec-core/issues/428)) ([1dd0c81](https://github.com/nevenincs/vaultspec-core/commit/1dd0c8194c0c92a9c5ac9ced6a5df951e3e8e337))
* **migrations:** stop reads running the schema registry ([#451](https://github.com/nevenincs/vaultspec-core/issues/451)) ([99e9d4f](https://github.com/nevenincs/vaultspec-core/commit/99e9d4fb8fdd91f1f7b3213b12797173309eb6c9))
* **migrations:** treat a versionless manifest as legacy, not as uninstalled ([#429](https://github.com/nevenincs/vaultspec-core/issues/429)) ([8adcb86](https://github.com/nevenincs/vaultspec-core/commit/8adcb86abdaf7d3ac12be00d7bfffabacfcc08c0))
* retire the dead gemini/network markers; keep GEMINI.md while antigravity owns it ([#494](https://github.com/nevenincs/vaultspec-core/issues/494)) ([fe93c1d](https://github.com/nevenincs/vaultspec-core/commit/fe93c1dbaafa9cfbe8b604ed31c744fe5664cf52))
* **sync,mcp:** stop sync discarding a failure code; make create's refusal legible ([#489](https://github.com/nevenincs/vaultspec-core/issues/489)) ([3f4d1d4](https://github.com/nevenincs/vaultspec-core/commit/3f4d1d4a44d2512827cba0fc84038f939a538837))
* **sync:** an unreadable ignore file was recorded as a permanent opt-out ([0ed9a50](https://github.com/nevenincs/vaultspec-core/commit/0ed9a50ddd0f5415d5124d582580836ca6bfe1b3))
* **sync:** the managed blocks are repository-level, not per-provider ([0974871](https://github.com/nevenincs/vaultspec-core/commit/0974871a1c32db2580e2081d506750c8810170da))
* **tests,vaultcore:** gate credential markers by default; reject Windows device names ([#483](https://github.com/nevenincs/vaultspec-core/issues/483)) ([8c84db5](https://github.com/nevenincs/vaultspec-core/commit/8c84db538736df2ba21b64643cf5375558a3d432)), closes [#466](https://github.com/nevenincs/vaultspec-core/issues/466) [#462](https://github.com/nevenincs/vaultspec-core/issues/462)
* **uninstall:** prune the sentinels it orphaned and reconcile gitattributes ([#433](https://github.com/nevenincs/vaultspec-core/issues/433)) ([414afd7](https://github.com/nevenincs/vaultspec-core/commit/414afd72cf4ee9abd446b0e62aafc89d0995372a)), closes [#409](https://github.com/nevenincs/vaultspec-core/issues/409)
* **upgrade:** hold the manifest lock across the upgrade's own write cycle ([#440](https://github.com/nevenincs/vaultspec-core/issues/440)) ([9301040](https://github.com/nevenincs/vaultspec-core/commit/9301040758eb623a697f9b09fc6d2de75cef082c)), closes [#418](https://github.com/nevenincs/vaultspec-core/issues/418)
* **upgrade:** restore a deleted .vault/ instead of shrinking the block to match ([#431](https://github.com/nevenincs/vaultspec-core/issues/431)) ([6c8a6e5](https://github.com/nevenincs/vaultspec-core/commit/6c8a6e56cc295ef788c04dd45a333674c79a5c72)), closes [#415](https://github.com/nevenincs/vaultspec-core/issues/415)
* **vault:** admit document dates as dates, and make scaffold containment a chokepoint ([#477](https://github.com/nevenincs/vaultspec-core/issues/477)) ([eea2079](https://github.com/nevenincs/vaultspec-core/commit/eea2079dd66b0fea44acf9b069595d2f8dfe74a4))
* **vault:** format the audit document that broke main's markdown gate ([#445](https://github.com/nevenincs/vaultspec-core/issues/445)) ([6a84b8b](https://github.com/nevenincs/vaultspec-core/commit/6a84b8b920574330d6ad176de08c0ef4296c1d4f))
* **vault:** re-derive the last three --fix writers under the document lock ([#486](https://github.com/nevenincs/vaultspec-core/issues/486)) ([c921822](https://github.com/nevenincs/vaultspec-core/commit/c9218221a346e647d2bd24c6141d68745cad7f19)), closes [#475](https://github.com/nevenincs/vaultspec-core/issues/475) [#472](https://github.com/nevenincs/vaultspec-core/issues/472)
* **vault:** reject unsupported tags before creating documents ([0c505fb](https://github.com/nevenincs/vaultspec-core/commit/0c505fba4e8d17957ccbc26d5c6c6085c3c04d16)), closes [#442](https://github.com/nevenincs/vaultspec-core/issues/442)
* **vault:** serialize --fix and repair writers on the per-document lock ([#474](https://github.com/nevenincs/vaultspec-core/issues/474)) ([76185e0](https://github.com/nevenincs/vaultspec-core/commit/76185e0199904cc67025396cf16d5e0756e2711c)), closes [#454](https://github.com/nevenincs/vaultspec-core/issues/454)
* **workspace:** preserving unknown keys must not preserve the migrated shape ([9f22f3a](https://github.com/nevenincs/vaultspec-core/commit/9f22f3ae70ba21608f43e95104f8db3fe51f9cd0))

## [0.1.73](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.72...vaultspec-core-v0.1.73) (2026-08-30)


### Features

* **ci:** acquire at the declared glibc floor, not only above it ([#395](https://github.com/nevenincs/vaultspec-core/issues/395)) ([8c84e70](https://github.com/nevenincs/vaultspec-core/commit/8c84e70a0b058ef693d1e449c0054a6f555113e7))

## [0.1.72](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.71...vaultspec-core-v0.1.72) (2026-08-30)


### Features

* **ci:** acquire the aarch64 Linux binary, and derive that coverage ([#392](https://github.com/nevenincs/vaultspec-core/issues/392)) ([6b7c864](https://github.com/nevenincs/vaultspec-core/commit/6b7c8641ac3bcd17ec30a08e3349a428ad178f35))

## [0.1.71](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.70...vaultspec-core-v0.1.71) (2026-08-30)


### Features

* **binaries:** build linux-aarch64 on a hosted ARM64 runner ([#387](https://github.com/nevenincs/vaultspec-core/issues/387)) ([2240f7e](https://github.com/nevenincs/vaultspec-core/commit/2240f7ea287e6a0519f3c2e3ded4e2c42e955a7d))

## [0.1.70](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.69...vaultspec-core-v0.1.70) (2026-08-30)


### Bug Fixes

* **acquisition:** wait on the binary bootstrapping, not on a PyPI endpoint ([#389](https://github.com/nevenincs/vaultspec-core/issues/389)) ([50c7ca1](https://github.com/nevenincs/vaultspec-core/commit/50c7ca1581df536030ec358779218232e2c3a371))
* **acquisition:** wait on the index the installer reads, not the JSON API ([#385](https://github.com/nevenincs/vaultspec-core/issues/385)) ([a8d1d72](https://github.com/nevenincs/vaultspec-core/commit/a8d1d72c231006dbad23f47dd735b8f4bb027aaf))

## [0.1.69](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.68...vaultspec-core-v0.1.69) (2026-08-30)


### Bug Fixes

* **acquisition:** give the Windows leg a profile the binary can actually use ([#383](https://github.com/nevenincs/vaultspec-core/issues/383)) ([7e9fd87](https://github.com/nevenincs/vaultspec-core/commit/7e9fd87e6ffbdc167c22f9284fc7391705389228))

## [0.1.68](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.67...vaultspec-core-v0.1.68) (2026-08-30)


### Bug Fixes

* **acquisition:** wait for PyPI, which the binary needs in order to start ([#380](https://github.com/nevenincs/vaultspec-core/issues/380)) ([b65763a](https://github.com/nevenincs/vaultspec-core/commit/b65763a40f0b80e01593e731936a885c337c51c6))
* **channels:** one channel root per product, and a guard that watches it ([#373](https://github.com/nevenincs/vaultspec-core/issues/373)) ([e420699](https://github.com/nevenincs/vaultspec-core/commit/e420699108f7c71d3a4e21563b1a5e584cdb5b00))

## [0.1.67](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.66...vaultspec-core-v0.1.67) (2026-08-30)


### Features

* **acquisition:** execute the Windows binary, closing the last platform ([#376](https://github.com/nevenincs/vaultspec-core/issues/376)) ([a55eea7](https://github.com/nevenincs/vaultspec-core/commit/a55eea7c60b84d4d865db821f188ed4904db7360))


### Bug Fixes

* **binaries:** drop the Intel leg, derive the preflight selectors, host the guard ([#372](https://github.com/nevenincs/vaultspec-core/issues/372)) ([3cd128d](https://github.com/nevenincs/vaultspec-core/commit/3cd128d8de3683ea73b6ecdff20054b0c12e70c2))
* **binaries:** require every declared target, not any asset at all ([#377](https://github.com/nevenincs/vaultspec-core/issues/377)) ([778788c](https://github.com/nevenincs/vaultspec-core/commit/778788cbe54caf1e11e2b74d8420c527ad102cbc))
* **release-please:** dispatch binaries from main, not from the tag ([#378](https://github.com/nevenincs/vaultspec-core/issues/378)) ([e1b578a](https://github.com/nevenincs/vaultspec-core/commit/e1b578a34d5b7f7011cc366ecf97b115cf5ac13e))

## [0.1.66](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.65...vaultspec-core-v0.1.66) (2026-08-30)


### Features

* **acquisition:** execute the macOS binary, which nothing currently does ([#374](https://github.com/nevenincs/vaultspec-core/issues/374)) ([30b8dc5](https://github.com/nevenincs/vaultspec-core/commit/30b8dc55953e757aba21564f5c77fd9b21fb9ea8))

## [0.1.65](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.64...vaultspec-core-v0.1.65) (2026-08-30)


### Bug Fixes

* **binaries:** dispatch the acquisition check, which cannot see a release ([#371](https://github.com/nevenincs/vaultspec-core/issues/371)) ([bb69ac5](https://github.com/nevenincs/vaultspec-core/commit/bb69ac503b0e63a20261ec5f394ef728858c1a4c))
* **binaries:** stop executing a bootstrapper before its package exists ([#369](https://github.com/nevenincs/vaultspec-core/issues/369)) ([f10697c](https://github.com/nevenincs/vaultspec-core/commit/f10697c48930eee8aeceefb678009f6f5cb590e1))
* **publish:** the job that uploads a release asset needs contents: write ([#368](https://github.com/nevenincs/vaultspec-core/issues/368)) ([c6b04d7](https://github.com/nevenincs/vaultspec-core/commit/c6b04d73b25180c6dacf17811a0bf5968c02b78e))

## [0.1.64](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.63...vaultspec-core-v0.1.64) (2026-08-30)


### Features

* **ci:** check what users acquire, not only what the tree builds ([#367](https://github.com/nevenincs/vaultspec-core/issues/367)) ([c18a8f5](https://github.com/nevenincs/vaultspec-core/commit/c18a8f56ddef72bfaf9cc816ef45497c24eb67de))


### Bug Fixes

* **binaries:** execute every artifact before it is uploaded ([#365](https://github.com/nevenincs/vaultspec-core/issues/365)) ([c9e844f](https://github.com/nevenincs/vaultspec-core/commit/c9e844f20ae78438a3490f742183f92ed4991a3c))

## [0.1.63](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.62...vaultspec-core-v0.1.63) (2026-08-30)


### Bug Fixes

* **binaries:** derive the expected targets from the matrix that builds them ([#364](https://github.com/nevenincs/vaultspec-core/issues/364)) ([5b3cb2e](https://github.com/nevenincs/vaultspec-core/commit/5b3cb2e85e857c65751efecb953e96afdf96731a))
* **binaries:** expect the targets the matrix builds, not one it cannot ([#361](https://github.com/nevenincs/vaultspec-core/issues/361)) ([41e9a77](https://github.com/nevenincs/vaultspec-core/commit/41e9a7752a94789af35e87afe2bd2f1d0c54b9a0))

## [0.1.62](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.61...vaultspec-core-v0.1.62) (2026-08-30)


### Features

* **binaries:** refuse to let an artifact-less release serve as latest ([#355](https://github.com/nevenincs/vaultspec-core/issues/355)) ([bfd6010](https://github.com/nevenincs/vaultspec-core/commit/bfd6010ebec5a8eb8178e567fa7e3aa10ebf7248))
* **publish:** trigger on tag, attach the distribution, and share the manifest ([#357](https://github.com/nevenincs/vaultspec-core/issues/357)) ([d652163](https://github.com/nevenincs/vaultspec-core/commit/d652163d282f4071e9335dd81617370cc0497d00))
* **release:** publish channel pointers to the org distribution repo ([#351](https://github.com/nevenincs/vaultspec-core/issues/351)) ([e705132](https://github.com/nevenincs/vaultspec-core/commit/e70513222e93efc841de37085cad5418b0944a25))


### Bug Fixes

* **binaries:** attach the binaries that built instead of discarding them ([#354](https://github.com/nevenincs/vaultspec-core/issues/354)) ([bc38b67](https://github.com/nevenincs/vaultspec-core/commit/bc38b6786531d02da7b7fc02547fceb31e822903))
* **binaries:** build on the tag, not only on a dispatch nobody remembers ([#360](https://github.com/nevenincs/vaultspec-core/issues/360)) ([6d77a0d](https://github.com/nevenincs/vaultspec-core/commit/6d77a0d50949f74955abf86e4e27e3eac035c342))
* **binaries:** declare the linux-aarch64 gap instead of failing every release ([#356](https://github.com/nevenincs/vaultspec-core/issues/356)) ([f7fb1fa](https://github.com/nevenincs/vaultspec-core/commit/f7fb1fa6bcb128e7e11886a16042a5d743be7971))
* **binaries:** return the containerised leg's workspace to the runner's user ([#359](https://github.com/nevenincs/vaultspec-core/issues/359)) ([a0e8566](https://github.com/nevenincs/vaultspec-core/commit/a0e8566a893eb2ea4009eb06365b5b065619584d))

## [0.1.61](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.60...vaultspec-core-v0.1.61) (2026-08-29)


### Features

* **ci:** assert main's tip actually received a CI verdict ([#346](https://github.com/nevenincs/vaultspec-core/issues/346)) ([be0afbb](https://github.com/nevenincs/vaultspec-core/commit/be0afbb966eef0957f6020fd6e743f3e87a9359d))
* **delivery:** generate scoop and homebrew pointers, add the linux-arm64 leg ([#344](https://github.com/nevenincs/vaultspec-core/issues/344)) ([bb2a6df](https://github.com/nevenincs/vaultspec-core/commit/bb2a6df0fed3d68550e3e653b3b20ff7a0474db5))


### Bug Fixes

* **binaries:** make the published binaries verifiable and loadable where promised ([#343](https://github.com/nevenincs/vaultspec-core/issues/343)) ([c2493cb](https://github.com/nevenincs/vaultspec-core/commit/c2493cbe5b55e3309d874c895deeaa2ebc4b392f))
* **ci:** stop cancelling the gate run on main ([#347](https://github.com/nevenincs/vaultspec-core/issues/347)) ([5627985](https://github.com/nevenincs/vaultspec-core/commit/5627985817f4784430322cd3b0a399ac71faac04))
* **core:** treat EACCES from the Windows lock as contention, not a fault ([#349](https://github.com/nevenincs/vaultspec-core/issues/349)) ([68e8f6b](https://github.com/nevenincs/vaultspec-core/commit/68e8f6b379beeed6f139b63333039b1a17edff6f))

## [0.1.60](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.59...vaultspec-core-v0.1.60) (2026-08-27)


### Features

* report semantic-search capability without coupling core to rag ([#331](https://github.com/nevenincs/vaultspec-core/issues/331)) ([80b272e](https://github.com/nevenincs/vaultspec-core/commit/80b272ecce0555cd781b919d66bbaf90c94cac7c))


### Bug Fixes

* allow Python 3.14 ([8a07c7f](https://github.com/nevenincs/vaultspec-core/commit/8a07c7fc47c511ac3fbff2e5931def1719b989a4))
* **ci:** publish from hosted runners so releases do not wait on a laptop ([c92a1eb](https://github.com/nevenincs/vaultspec-core/commit/c92a1eb914b0f0a8eac8b5ef1bc644dd32168f69))
* **ci:** publish from the macOS runner, not a label no runner carries ([e17faf7](https://github.com/nevenincs/vaultspec-core/commit/e17faf78f51677ef7cb428b1f78cbd72dc6e77f4))
* **mcp:** surface the catalog refusal and guard the refusal contract ([#332](https://github.com/nevenincs/vaultspec-core/issues/332)) ([48dd9a5](https://github.com/nevenincs/vaultspec-core/commit/48dd9a5970111ba9077732001285bbb40973547f))

## [0.1.59](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.58...vaultspec-core-v0.1.59) (2026-08-25)


### Bug Fixes

* **check:** judge plan grounding by what the plan declares ([9b4381b](https://github.com/nevenincs/vaultspec-core/commit/9b4381b8ead3595a9840932be00bc5d7504356a6))
* **check:** let Wave blocks satisfy a plan's Steps section ([32b3fb1](https://github.com/nevenincs/vaultspec-core/commit/32b3fb126fd41f467efef7ec35a8afc07027f21f))
* **ci:** stop the bootstrap job queueing against a label no runner carries ([2f637d0](https://github.com/nevenincs/vaultspec-core/commit/2f637d05bbcac0d3066f4c53677ba88105379c4a))
* **core:** ride out the Windows scanner race on atomic document replace ([4731633](https://github.com/nevenincs/vaultspec-core/commit/47316336fd42b124e8e06d2b91588cf2529e0605))
* **mcps:** resolve Claude Code user scope through CLAUDE_CONFIG_DIR ([b40a67d](https://github.com/nevenincs/vaultspec-core/commit/b40a67d46d00aefc573c5d7a67ed5e296818689b))


### Performance

* bound the MCP and CLI return envelopes, and fix the repair regression ([#322](https://github.com/nevenincs/vaultspec-core/issues/322)) ([cdb0a71](https://github.com/nevenincs/vaultspec-core/commit/cdb0a71b3b7ad0a9bbd2a3c778dc68d31f5bb1d4))

## [0.1.58](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.57...vaultspec-core-v0.1.58) (2026-08-23)


### Features

* **exec:** compress execution records to a mechanical log and consolidate them per plan ([#323](https://github.com/nevenincs/vaultspec-core/issues/323)) ([cf3913a](https://github.com/nevenincs/vaultspec-core/commit/cf3913afee16ada9a9acdc22f76988e524827c84))


### Bug Fixes

* **ci:** set the board target date through the API, not the gh CLI ([#325](https://github.com/nevenincs/vaultspec-core/issues/325)) ([65e3981](https://github.com/nevenincs/vaultspec-core/commit/65e3981ae245da4beef276e1f80cc6618b32dcf9))
* **plan:** close both write-guard follow-ups from [#313](https://github.com/nevenincs/vaultspec-core/issues/313) ([#318](https://github.com/nevenincs/vaultspec-core/issues/318)) ([06b30a2](https://github.com/nevenincs/vaultspec-core/commit/06b30a29e3c60c903013b1f4b18c8e869d92ce5f))
* **plan:** exclude HTML comments from parsing and make mutations atomic ([#314](https://github.com/nevenincs/vaultspec-core/issues/314)) ([bc03f9e](https://github.com/nevenincs/vaultspec-core/commit/bc03f9e0fa0f56f32a439c6c184f6ac5249f9e11))
* **tests:** decode CLI captures as UTF-8 and report child exit status ([#324](https://github.com/nevenincs/vaultspec-core/issues/324)) ([52598da](https://github.com/nevenincs/vaultspec-core/commit/52598da7076bf2c0d11dce737fd3ba22d6cca712))

## [0.1.57](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.56...vaultspec-core-v0.1.57) (2026-08-13)


### Features

* **core:** support the machine-global process registry home ([#309](https://github.com/nevenincs/vaultspec-core/issues/309)) ([86e7111](https://github.com/nevenincs/vaultspec-core/commit/86e7111e458386e5a0e97300a374e36b5afc6b69))


### Bug Fixes

* autofix body wiki-links ([#307](https://github.com/nevenincs/vaultspec-core/issues/307)) ([a28c2a6](https://github.com/nevenincs/vaultspec-core/commit/a28c2a66c760536fbd9b6a687432addccdda59bd))
* **plan:** prevent destructive structural rewrites ([#310](https://github.com/nevenincs/vaultspec-core/issues/310)) ([b401c69](https://github.com/nevenincs/vaultspec-core/commit/b401c696e8157c6977e9d4d916717c746832f289))
* **plan:** serialize concurrent mutation verbs ([#312](https://github.com/nevenincs/vaultspec-core/issues/312)) ([ac551d7](https://github.com/nevenincs/vaultspec-core/commit/ac551d7236a331cbcf96ec68e644e5916e3c33f8))
* **vault:** preserve body hash integrity across rewrites ([#308](https://github.com/nevenincs/vaultspec-core/issues/308)) ([7d6678c](https://github.com/nevenincs/vaultspec-core/commit/7d6678ca369023a0bd2a0d5360c7e4b6b1b730fe))

## [0.1.56](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.55...vaultspec-core-v0.1.56) (2026-08-01)


### Features

* **mcp:** add read-only launch mode ([#302](https://github.com/nevenincs/vaultspec-core/issues/302)) ([afe5489](https://github.com/nevenincs/vaultspec-core/commit/afe5489481ceed22f5310148e98f78766bafe432))

## [0.1.55](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.54...vaultspec-core-v0.1.55) (2026-07-31)


### Bug Fixes

* **tests:** canonicalize workspace roots so provider scaffolding survives 8.3 paths ([75b8a38](https://github.com/nevenincs/vaultspec-core/commit/75b8a383bb72847f64d59dbaf111a397db0f1ee0))
* **tests:** green the release-acceptance gate on runners without the CLIs ([#287](https://github.com/nevenincs/vaultspec-core/issues/287)) ([1645988](https://github.com/nevenincs/vaultspec-core/commit/164598893eea9554093f468feec0586ff4103e81))
* **types:** guard the Windows-only branches and check every target platform ([481acef](https://github.com/nevenincs/vaultspec-core/commit/481acef2800c313f424a61e43ac30bf872ffeec6))
* **vault:** stamp provenance, plan rollup, and parser integrity ([#298](https://github.com/nevenincs/vaultspec-core/issues/298)) ([351a51d](https://github.com/nevenincs/vaultspec-core/commit/351a51d7396d86dd0f297ab3d16bd86b317292e6))

## [0.1.54](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.53...vaultspec-core-v0.1.54) (2026-07-28)


### Features

* **dev:** platform-agnostic development harness and quality-gate parity ([#279](https://github.com/nevenincs/vaultspec-core/issues/279)) ([2945621](https://github.com/nevenincs/vaultspec-core/commit/2945621988dcc2e6ea6f30b869a5c7bc3b4d2c63))
* let a workspace decline managed pre-commit scaffolding ([e38faca](https://github.com/nevenincs/vaultspec-core/commit/e38faca47b44ed5a9b69edc085bf4a9584b898d5))
* let a workspace decline managed pre-commit scaffolding ([#285](https://github.com/nevenincs/vaultspec-core/issues/285)) ([c58cc21](https://github.com/nevenincs/vaultspec-core/commit/c58cc21423e97abdbbc790cf127a489912dc58e1))
* **packaging:** ship the py.typed marker so consumers can read the inline types ([ce252de](https://github.com/nevenincs/vaultspec-core/commit/ce252de59fa60d1c0adcd0365fb1686bbaafe628)), closes [#278](https://github.com/nevenincs/vaultspec-core/issues/278)
* **packaging:** ship the py.typed marker so consumers can read the inline types ([f825fd9](https://github.com/nevenincs/vaultspec-core/commit/f825fd9c4e7cdf9f23987f83eecfc3eb37ff4b0d)), closes [#278](https://github.com/nevenincs/vaultspec-core/issues/278)


### Bug Fixes

* **ci:** pin the interpreter and bound requires-python ([#283](https://github.com/nevenincs/vaultspec-core/issues/283)) ([b32ce86](https://github.com/nevenincs/vaultspec-core/commit/b32ce8650fec413202545ce0d62469d1c9925da2))
* **ci:** pin the interpreter and bound requires-python ([#283](https://github.com/nevenincs/vaultspec-core/issues/283)) ([6dbdcaa](https://github.com/nevenincs/vaultspec-core/commit/6dbdcaa12b9e2703c4e671704fa04ec66dcc480b))
* **sync:** honour pre-commit hook removal instead of resurrecting it ([#286](https://github.com/nevenincs/vaultspec-core/issues/286)) ([9dd9956](https://github.com/nevenincs/vaultspec-core/commit/9dd9956167e202814db573cdf3a6d336d862b8a4)), closes [#284](https://github.com/nevenincs/vaultspec-core/issues/284)
* **types:** annotate _target.py plan-document helpers (round 1 part 2/2) ([ccd4b28](https://github.com/nevenincs/vaultspec-core/commit/ccd4b28c27d82e159d3812515b2937d3ced073bf))
* **types:** annotate _target.py plan-document helpers (round 1 part 2/2) ([823a8fa](https://github.com/nevenincs/vaultspec-core/commit/823a8fab8179fa3234b18d2e982bb7e6cb52a3c2))
* **types:** annotate precommit.py's YAML-driven dict/list cascades ([6931b4a](https://github.com/nevenincs/vaultspec-core/commit/6931b4af1bb213a602201400a518d731a6bef843))
* **types:** annotate precommit.py's YAML-driven dict/list cascades ([8b9e548](https://github.com/nevenincs/vaultspec-core/commit/8b9e548071fcb76bb2cc185f144ef5785437efe0))
* **types:** annotate spec_cmd_doctor signal-mapping and rows collections ([b3442ad](https://github.com/nevenincs/vaultspec-core/commit/b3442addc6d60d5048b417bcf70df4c852dc3699))
* **types:** annotate spec_cmd_doctor signal-mapping and rows collections ([8e31293](https://github.com/nevenincs/vaultspec-core/commit/8e312931a4f49502f92c92fe3347fab21c2b3189))
* **types:** annotate spec_cmd_shared helpers and export the sibling-module surface ([834eec8](https://github.com/nevenincs/vaultspec-core/commit/834eec85fc705e132c8a3725c2afd24d73330099))
* **types:** annotate spec_cmd_shared helpers and export the sibling-module surface ([ffa0161](https://github.com/nevenincs/vaultspec-core/commit/ffa01614a3a3116fb4ed57687fe173ae3c142ce3))
* **types:** annotate vault_cmd._validate_created_doc doc_path parameter ([89ded03](https://github.com/nevenincs/vaultspec-core/commit/89ded035adb423ebd3fb3527757113ad75c1b6fc))
* **types:** annotate vault_cmd._validate_created_doc doc_path parameter ([0d2b512](https://github.com/nevenincs/vaultspec-core/commit/0d2b51243a11e67b3d5bc56a11b4c9d6a92eb64e))
* **types:** basedpyright strict burndown round 1 (part 1/2) ([aed414f](https://github.com/nevenincs/vaultspec-core/commit/aed414f7fbf1009fd58e525425dc314069035658))
* **types:** basedpyright strict burndown round 1 (part 1/2) ([43d8f74](https://github.com/nevenincs/vaultspec-core/commit/43d8f74f2714ab7c64b0989e63511b914e395728))
* **types:** keep the new precommit-standdown fixture off the strict gate ([6dd9d3d](https://github.com/nevenincs/vaultspec-core/commit/6dd9d3d20317e196dfb12af5d31ccf72d4c26081))

## [0.1.53](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.52...vaultspec-core-v0.1.53) (2026-07-27)


### Bug Fixes

* **vault:** body-schema attestation decision and single-ingress document listings ([#274](https://github.com/nevenincs/vaultspec-core/issues/274)) ([d57337d](https://github.com/nevenincs/vaultspec-core/commit/d57337dacbf2a0e8f584c8ef132ecaae63ecb9ef))

## [0.1.52](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.51...vaultspec-core-v0.1.52) (2026-07-27)


### Features

* allow topic-infixed ADR records ([#271](https://github.com/nevenincs/vaultspec-core/issues/271)) ([7009f37](https://github.com/nevenincs/vaultspec-core/commit/7009f377297452745dbbfe9e455d18494751cea6))


### Bug Fixes

* **plan:** preserve sanitized link rules across mutations ([9343c0c](https://github.com/nevenincs/vaultspec-core/commit/9343c0c22763806ad17ec1ebc610ea6acf6a03d6))
* **plan:** preserve sanitized link rules across mutations ([313e11f](https://github.com/nevenincs/vaultspec-core/commit/313e11fec07a2b0e9f1050e47b4290784916471f))
* prevent scoped markdown repair migration spills ([f4159dc](https://github.com/nevenincs/vaultspec-core/commit/f4159dc1d10325973978bc56ac69f50791206158))
* scope markdown repairs before migrations ([68be351](https://github.com/nevenincs/vaultspec-core/commit/68be351c42a1c53b041c3c786094e00c7d6c6394))


### Performance

* **vault:** scale large-corpus reads to the second domain ([#273](https://github.com/nevenincs/vaultspec-core/issues/273)) ([b2acc30](https://github.com/nevenincs/vaultspec-core/commit/b2acc30c2e1083fe871db02770a2b037773fb9d5))

## [0.1.51](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.50...vaultspec-core-v0.1.51) (2026-07-24)


### Tests

* **cli:** guard that every indexed command has a prose section ([#264](https://github.com/nevenincs/vaultspec-core/issues/264)) ([5a72cee](https://github.com/nevenincs/vaultspec-core/commit/5a72ceeba8549ec33cc68201c5b9a7265beb2ea8))

## [0.1.50](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.49...vaultspec-core-v0.1.50) (2026-07-23)


### Bug Fixes

* **config:** resolve editor paths with platform-aware tokenization ([#255](https://github.com/nevenincs/vaultspec-core/issues/255)) ([a1ee996](https://github.com/nevenincs/vaultspec-core/commit/a1ee99643fd28102dc021ec775e1d2442e9dafc3))

## [0.1.49](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.48...vaultspec-core-v0.1.49) (2026-07-23)


### Features

* **prek:** content-aware hook boundary with assisted prek.toml migration ([43a9a56](https://github.com/nevenincs/vaultspec-core/commit/43a9a564694a6da5720d09ebafb22088e24f1b5b))
* **release:** add PyApp build configuration for standalone binaries ([3f6c0d1](https://github.com/nevenincs/vaultspec-core/commit/3f6c0d1f5123246e445aa283cc3abc1ee6dcfec3))
* **release:** add self-hosted binary-build workflow with release upload ([c5fe2fd](https://github.com/nevenincs/vaultspec-core/commit/c5fe2fd360d8722e53a02b12b727abff61e897cf))
* **scoop:** add core bucket manifest with post-release bump ([3385421](https://github.com/nevenincs/vaultspec-core/commit/33854211c0716381be293330875d82d645ff3264))
* **vault:** add exec-mapping and body-sections check validators ([e1418df](https://github.com/nevenincs/vaultspec-core/commit/e1418dfd6c3f30c08b1969d8f94d9e1263794e63)), closes [#233](https://github.com/nevenincs/vaultspec-core/issues/233) [#234](https://github.com/nevenincs/vaultspec-core/issues/234)


### Bug Fixes

* **cli:** own positional metavar grammar across the Typer 0.27 change ([7fc2f3b](https://github.com/nevenincs/vaultspec-core/commit/7fc2f3bd385161022e5d43dd64368297634ee202))
* **install:** non-destructive adoption and provider-lock ignore coverage ([c653c14](https://github.com/nevenincs/vaultspec-core/commit/c653c14a7c25116070c0d33cf2affb60f4daac73)), closes [#229](https://github.com/nevenincs/vaultspec-core/issues/229) [#230](https://github.com/nevenincs/vaultspec-core/issues/230)
* recognize unrefreshable prek sync state ([88e18e0](https://github.com/nevenincs/vaultspec-core/commit/88e18e0f9ce383e935adf3a0867af78082fd3fa3))
* **scoop:** make manifest push resilient to an advanced main ([9783fad](https://github.com/nevenincs/vaultspec-core/commit/9783fadd095b2d7b07b0a22d16b35e2f6d6ccbba))
* **sync:** idempotent .pre-commit-config.yaml assembly ([2aa4a88](https://github.com/nevenincs/vaultspec-core/commit/2aa4a88a0218829bb225ec6a6e4bb758cb2c297d)), closes [#241](https://github.com/nevenincs/vaultspec-core/issues/241)
* **sync:** self-gating spec-check hook so warnings do not deadlock commits ([6e41e06](https://github.com/nevenincs/vaultspec-core/commit/6e41e066627753c6371674640d1b35200f896468)), closes [#236](https://github.com/nevenincs/vaultspec-core/issues/236)
* **test:** make outdated_vaultspec_rules deterministic to unflake doctor warning gate ([b804438](https://github.com/nevenincs/vaultspec-core/commit/b804438bdc4e1a741fd5fd5b4a94b08bd15b3b8f)), closes [#243](https://github.com/nevenincs/vaultspec-core/issues/243)
* **vault:** recognize the stash/restore two-date mtime signature ([aa55570](https://github.com/nevenincs/vaultspec-core/commit/aa55570a74fb61b148c7aa8b69bd7d1443e361f9)), closes [#235](https://github.com/nevenincs/vaultspec-core/issues/235)

## [0.1.48](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.47...vaultspec-core-v0.1.48) (2026-07-17)


### Features

* **install:** managed launch artifacts converge automatically on upgrade and sync ([#227](https://github.com/nevenincs/vaultspec-core/issues/227)) ([34fc142](https://github.com/nevenincs/vaultspec-core/commit/34fc14205d11fad927f3ca062fba0b9ff0cf955d))

## [0.1.47](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.46...vaultspec-core-v0.1.47) (2026-07-17)


### Features

* **mcp:** watchdog parity - hybrid anchors, kill switch, telemetry, POSIX backstop ([#223](https://github.com/nevenincs/vaultspec-core/issues/223)) ([c66fb47](https://github.com/nevenincs/vaultspec-core/commit/c66fb4745586591cc5d973a539acd09679d1bb74)), closes [#220](https://github.com/nevenincs/vaultspec-core/issues/220)
* **vault:** opt-in code-boundary source scanner (vault check code-boundary) ([#218](https://github.com/nevenincs/vaultspec-core/issues/218)) ([50a67fa](https://github.com/nevenincs/vaultspec-core/commit/50a67fa05ccfcb38d4acf809d1442b2a5703eed7))
* **vault:** topic-infix scaffolding for audit, reference, and research (--topic) ([#217](https://github.com/nevenincs/vaultspec-core/issues/217)) ([55eb8a3](https://github.com/nevenincs/vaultspec-core/commit/55eb8a33bab681e684ebacd3094fc03316ad82a2))


### Bug Fixes

* **boundary:** triage code-stands-alone violations in source docstrings and README renders ([#219](https://github.com/nevenincs/vaultspec-core/issues/219)) ([2537f19](https://github.com/nevenincs/vaultspec-core/commit/2537f19f7de7d1c45bfac0389c9f20e7b6f4f3d8))
* **mcp:** MCP launch is side-effect-free static execution (--no-sync) ([#224](https://github.com/nevenincs/vaultspec-core/issues/224)) ([822511b](https://github.com/nevenincs/vaultspec-core/commit/822511b1739dacfc6e48733a88aed1be48167246))
* **mcp:** Windows client-PID watchdog - stdio server exits when its client dies ([#221](https://github.com/nevenincs/vaultspec-core/issues/221)) ([6461594](https://github.com/nevenincs/vaultspec-core/commit/64615940183ae6f6a9809de2ab261207055b314d)), closes [#220](https://github.com/nevenincs/vaultspec-core/issues/220)
* **sync:** managed gitignore covers mcp-ownership.json; honest stale-file warnings ([#216](https://github.com/nevenincs/vaultspec-core/issues/216)) ([5081371](https://github.com/nevenincs/vaultspec-core/commit/50813711be8ecfa1f842a566c849d0fc6e664e75))

## [0.1.46](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.45...vaultspec-core-v0.1.46) (2026-07-16)


### Miscellaneous

* **firmware:** release code-stands-alone boundary firmware ([fe29ea0](https://github.com/nevenincs/vaultspec-core/commit/fe29ea076c823492ce257cc2d382f280a1817971))

## [0.1.45](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.44...vaultspec-core-v0.1.45) (2026-07-16)


### Bug Fixes

* **core:** harden atomic file replacement ([#210](https://github.com/nevenincs/vaultspec-core/issues/210)) ([083ff4f](https://github.com/nevenincs/vaultspec-core/commit/083ff4ff8c2531f1d2ff4ce3a5789020721080d8))

## [0.1.44](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.43...vaultspec-core-v0.1.44) (2026-07-15)


### Features

* add provider-native MCP enrollment ([#208](https://github.com/nevenincs/vaultspec-core/issues/208)) ([a972e94](https://github.com/nevenincs/vaultspec-core/commit/a972e9480ff81b82f0cb72dc94fc9e3db0592dfd))

## [0.1.43](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.42...vaultspec-core-v0.1.43) (2026-07-14)


### Bug Fixes

* **vault:** match block indent and dedupe aliases in link add ([#206](https://github.com/nevenincs/vaultspec-core/issues/206)) ([08d2252](https://github.com/nevenincs/vaultspec-core/commit/08d22528d9e3593e3083e22bb882b3b48d8ae5e5))

## [0.1.42](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.41...vaultspec-core-v0.1.42) (2026-07-14)


### Bug Fixes

* **vault:** honor CommonMark fence-close rules in placeholder check ([8030dbb](https://github.com/nevenincs/vaultspec-core/commit/8030dbb7abcb6d27f6d24e6b512a1a9a65e39812))

## [0.1.41](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.40...vaultspec-core-v0.1.41) (2026-07-14)


### Features

* **diagnosis:** public observed_mcp_mode accessor for companion packages ([c71b484](https://github.com/nevenincs/vaultspec-core/commit/c71b484bcb0595d8c060c2441cf7bce3e95e1552))
* **diagnosis:** public observed_mcp_mode accessor for companion packages ([c55cc2a](https://github.com/nevenincs/vaultspec-core/commit/c55cc2a9891ca5c9c47d1aac1171f7ddf298471f))

## [0.1.40](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.39...vaultspec-core-v0.1.40) (2026-07-14)


### Bug Fixes

* **vault:** accept reference and audit documents as ADR grounding ([f1eaa38](https://github.com/nevenincs/vaultspec-core/commit/f1eaa389eb9949ed134d42c8e38173e0d8cde310))
* **vault:** accept reference and audit documents as ADR grounding ([aba28af](https://github.com/nevenincs/vaultspec-core/commit/aba28af6ec85322ee71dfabcdab97a9274fb88e9))

## [0.1.39](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.38...vaultspec-core-v0.1.39) (2026-07-14)


### Bug Fixes

* **core:** parameterize dependency-leak advisory by package (install-parity W02.P07.S40) ([bc66800](https://github.com/nevenincs/vaultspec-core/commit/bc6680085a2ba414f4dc3378fe95852b335d153a))
* **core:** per-package MCP render mode + package-named leak advisory (install-parity W02.P07) ([b5249f3](https://github.com/nevenincs/vaultspec-core/commit/b5249f370f57c128818e437ae4d87742a611617c))
* **core:** resolve MCP render mode per declaring package (install-parity W02.P07.S39) ([93f208f](https://github.com/nevenincs/vaultspec-core/commit/93f208f0a4bcb90a5d3f6cd315b682686d947b93))

## [0.1.38](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.37...vaultspec-core-v0.1.38) (2026-07-14)


### Features

* **builtins:** amend-first ADR doctrine - one governing record per decision ([dc27844](https://github.com/nevenincs/vaultspec-core/commit/dc27844d971076ba6c83cf146c0515dede456a0d))
* **builtins:** teach curate to enforce the single-home-fact boundary ([d74188f](https://github.com/nevenincs/vaultspec-core/commit/d74188fa1db50cbfe08b5d5814ce1c3749979a0b))
* **cli:** document dev provisioning mode in install --mode help (install-parity W01.P02.S10) ([e0232f9](https://github.com/nevenincs/vaultspec-core/commit/e0232f907bf03f0230e55d6a6b8558ab32975ae0))
* **core:** add collect_mode_mismatch_state and wire into diagnose (install-mode P04.S20) ([cf5def2](https://github.com/nevenincs/vaultspec-core/commit/cf5def21d907bdbba709735699d8b8deacea02a6))
* **core:** add committed workspace mode declaration (install-mode P01.S02) ([867f36b](https://github.com/nevenincs/vaultspec-core/commit/867f36bf347a4c0d96c710f574d283218c780d45))
* **core:** add install --mode flag and resolve/persist provisioning mode (install-mode P02.S06) ([d9b8d83](https://github.com/nevenincs/vaultspec-core/commit/d9b8d83de1b623d9254946e64a73456b092e3168))
* **core:** add InstallMode enum (install-mode P01.S01) ([732c95e](https://github.com/nevenincs/vaultspec-core/commit/732c95eeaab334fb2cfa4cb7d6f9ab4f5730e5f9))
* **core:** add InstallMode.DEV dev-scoped placement member (install-parity W01.P01.S01) ([9e0aa36](https://github.com/nevenincs/vaultspec-core/commit/9e0aa36046c376719c019002bccb3bce5a8c4600))
* **core:** add ModeMismatchSignal enum (install-mode P04.S18) ([358b7d2](https://github.com/nevenincs/vaultspec-core/commit/358b7d21c091e53d5c307a76ad6969824559060f))
* **core:** add PackageDeclaration and bump workspace schema to 2.0 (install-parity W01.P01.S03) ([b517fa4](https://github.com/nevenincs/vaultspec-core/commit/b517fa424aa5d2ba9a0042b9063e61bdfe0f3dcd))
* **core:** add per-package read/write helpers preserving siblings (install-parity W01.P01.S06) ([56395a9](https://github.com/nevenincs/vaultspec-core/commit/56395a97b4ede3661fdec028aa3d75408c6c2bd9))
* **core:** add render_mode aliasing helper collapsing DEV onto DEPENDENCY (install-parity W01.P01.S02) ([359a605](https://github.com/nevenincs/vaultspec-core/commit/359a6054ff10586774d64569e27537f137ef39f6))
* **core:** add resolve_install_mode Q5 precedence chain and pyproject dependency probe (install-mode P02.S07) ([15eb133](https://github.com/nevenincs/vaultspec-core/commit/15eb1337ad4c233439de01d953fd4ebb1e9b9536))
* **core:** echo resolved mode and floor in manifest (install-mode P01.S03) ([dad70a2](https://github.com/nevenincs/vaultspec-core/commit/dad70a20be7970fa6add0a247d161d2e68899e87))
* **core:** enforce minimum_vaultspec_version floor constraint (install-mode P04.S22) ([43e23bd](https://github.com/nevenincs/vaultspec-core/commit/43e23bd292f5feda815b33e9531a5fd645d3a2a8))
* **core:** infer and persist mode on install --upgrade (install-mode P05.S26) ([127d8f1](https://github.com/nevenincs/vaultspec-core/commit/127d8f19ac0b722faca91ba5285e70ae8ccbc54a))
* **core:** install-parity W01 - DEV mode, per-package workspace declaration, parity renderers ([2bb9a9a](https://github.com/nevenincs/vaultspec-core/commit/2bb9a9a8692d35d079f16b9b70fc48be1b3ef58c))
* **core:** key precommit scaffold render mode to core's own entry (install-parity W01.P03.S16) ([c089e8e](https://github.com/nevenincs/vaultspec-core/commit/c089e8e6f1c8bd93e741e0ee938fd9594e8ea281))
* **core:** make builtin MCP definition mode-neutral via placeholder tokens (install-mode P03.S12) ([381a125](https://github.com/nevenincs/vaultspec-core/commit/381a1256d894af87ad8b24513720313f1771713c))
* **core:** make canonical hook prefix and entries functions of install mode (install-mode P03.S14) ([30d4307](https://github.com/nevenincs/vaultspec-core/commit/30d4307c9f027b117045e27733ef43492eb940bd))
* **core:** mode-aware provisioning - tool-first install (install-mode) ([b668e27](https://github.com/nevenincs/vaultspec-core/commit/b668e2769ce31dbadd53a4a985003d6e96877082))
* **core:** package-aware resolve_install_mode with DEV precedence (install-parity W01.P02.S09) ([17bdf48](https://github.com/nevenincs/vaultspec-core/commit/17bdf48c05909538e0f64a068cf9548ed638ad02))
* **core:** parameterize the MCP launch by package and module (install-parity W01.P03.S28) ([d89e7f9](https://github.com/nevenincs/vaultspec-core/commit/d89e7f9bb305f3c925b775994166b5606350d9b6))
* **core:** parse v2 packages map with legacy v1 read-fold (install-parity W01.P01.S04) ([c8f1a4f](https://github.com/nevenincs/vaultspec-core/commit/c8f1a4ff1d8173bc65aa7af74fcb039747bcaf4c))
* **core:** placement-aware dependency detection taxonomy (install-parity W01.P02.S08) ([292d688](https://github.com/nevenincs/vaultspec-core/commit/292d68843c09cc664db13c12401fad0d4e0970e6))
* **core:** render doctor install-mode and floor rows per declared package (install-parity W01.P03.S18) ([19ad807](https://github.com/nevenincs/vaultspec-core/commit/19ad807194a99492782adc8de2cb6f209f30e670))
* **core:** render MCP launch through the generalized helper (install-parity W01.P03.S15) ([c2f6023](https://github.com/nevenincs/vaultspec-core/commit/c2f6023941843d23a4d941b73c7a8a6521f10ce2))
* **core:** render pre-commit hooks for the resolved install mode (install-mode P03.S15) ([494e8ad](https://github.com/nevenincs/vaultspec-core/commit/494e8adfcdf73ca078bc040067a743df7e26119e))
* **core:** render the MCP definition for the resolved install mode (install-mode P03.S13) ([e09c5f7](https://github.com/nevenincs/vaultspec-core/commit/e09c5f777223e4185be0883368b0877417d7a3ec))
* **core:** resolve install mode via Q5 precedence with loud conflict refusal (install-mode P02.S08) ([d3c82a4](https://github.com/nevenincs/vaultspec-core/commit/d3c82a4b42a6d6c7497697af17e963e8547f2482))
* **core:** resolve mode mismatch and mode-aware precommit advisory (install-mode P04.S21) ([fe42635](https://github.com/nevenincs/vaultspec-core/commit/fe42635276c4a7eb3b177773d8a2500a15fe800d))
* **core:** resolve_render_mode reads a package's own entry (install-parity W01.P03.S14) ([8b1b0ef](https://github.com/nevenincs/vaultspec-core/commit/8b1b0ef1c11355df586670324be5755c786f5627))
* **core:** route upgrade-mode helpers through the per-package API (install-parity W01.P03.S19) ([b3b0c78](https://github.com/nevenincs/vaultspec-core/commit/b3b0c78a9375c832d9f28ea12b472cf8c10f77f3))
* **core:** serialize canonical v2 packages map preserving siblings (install-parity W01.P01.S05) ([83dd6a1](https://github.com/nevenincs/vaultspec-core/commit/83dd6a145e46f23fcd609ea1c7cc8bc2d3cebe1d))
* **core:** thread mode_mismatch field through diagnose (install-mode P04.S19) ([9b56f0f](https://github.com/nevenincs/vaultspec-core/commit/9b56f0f797f9be80b3819668360e2379183eb56d))
* **core:** warn-only dependency-leak advisory at provision time (install-parity W01.P02.S11) ([8cc87db](https://github.com/nevenincs/vaultspec-core/commit/8cc87dbae6fcb596c5918cdf709b5fdb07a7eba8))


### Bug Fixes

* **builtins:** mandate single-home facts across the document boundary ([78f2e42](https://github.com/nevenincs/vaultspec-core/commit/78f2e4258356916398602fc0d4837f41d2f3abae))
* **builtins:** raise the research-artifact density and sourcing bar ([837b640](https://github.com/nevenincs/vaultspec-core/commit/837b640d4049e55e950db40de22d4f7b479b468f))
* **builtins:** word many-ADRs-to-one-plan cardinality into the plan surfaces ([4266e8c](https://github.com/nevenincs/vaultspec-core/commit/4266e8ce6ea5e0af15e20ac175beb96fae998cbe))
* **core:** add unit coverage for install-mode refusal path (install-mode P02 review) ([f6ffde8](https://github.com/nevenincs/vaultspec-core/commit/f6ffde8c1fe45bbd664a581ea82f1727b263d3e7))
* **core:** fire dependency-leak advisory only at moment of choice (install-parity W01.P02 review) ([a715e85](https://github.com/nevenincs/vaultspec-core/commit/a715e8565fd46b51b678433484c2403be9dad326))
* **core:** force managed MCP entry on mode-flip upgrade (install-mode follow-up) ([a44e8b6](https://github.com/nevenincs/vaultspec-core/commit/a44e8b6c564d6f6b2f23c47e275a0c9b1d7f39f6))
* **core:** force managed MCP entry on mode-flip upgrade; declare repo version floor ([d2a0f45](https://github.com/nevenincs/vaultspec-core/commit/d2a0f459be59b065a73af0e05d660f6b9afd2e28))
* **core:** per-package mode-mismatch and floor collectors, dev renders clean (install-parity W01.P03.S17) ([58d7b73](https://github.com/nevenincs/vaultspec-core/commit/58d7b73b04d597b4ac02080222d366e7639c9157))
* **core:** render MCP registry for resolved mode in doctor drift check (install-mode P03 review) ([8e72b6e](https://github.com/nevenincs/vaultspec-core/commit/8e72b6ec1f99dc4959b4eaac6e75444188f03cc2))
* **core:** route preflight resolve() refusals through clean error handler (install-mode P04 review) ([ff75f3a](https://github.com/nevenincs/vaultspec-core/commit/ff75f3a3f923ef46541de0cb58952543ca9a0df0))
* **core:** surface mode-mismatch and floor signals on doctor via shared evaluator (install-mode P04 review) ([d4c8f63](https://github.com/nevenincs/vaultspec-core/commit/d4c8f634834104f558b3e6c6867b0908f9d57747))
* **core:** validate persisted declaration fail-fast in resolve_install_mode (install-mode P02 review) ([c721a77](https://github.com/nevenincs/vaultspec-core/commit/c721a77496d5b43940d790e76622b4f9982e1e40))

## [0.1.37](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.36...vaultspec-core-v0.1.37) (2026-07-10)


### Features

* **mcp:** add discover/invoke gateway tools over the verb catalog ([fcdb460](https://github.com/nevenincs/vaultspec-core/commit/fcdb460bbb7af0a93ea564ce2fbb027bf080576f))
* **mcp:** add gateway command catalog parsed from CLI reference markers ([87c1176](https://github.com/nevenincs/vaultspec-core/commit/87c1176e22806714ddd18a72b3bff758373baaf6))
* **mcp:** add shared per-item batch result envelope ([1f8217c](https://github.com/nevenincs/vaultspec-core/commit/1f8217ce618a1fee708f8ab3aa2c443bdbdb21e0))
* **mcp:** extend find and add status/check/plan tools over shared cores ([4ae33cd](https://github.com/nevenincs/vaultspec-core/commit/4ae33cd2486f6d4ac122b66e4d70dbedeb43e706))
* **mcp:** extract plan-write integrity guards into shared core ([69dad8b](https://github.com/nevenincs/vaultspec-core/commit/69dad8b5b873fb547829674d76910efb8822e6a6))
* **mcp:** rebuild create batch-native and add the edit tool ([5fe7430](https://github.com/nevenincs/vaultspec-core/commit/5fe743086dc0b81dc282c18181fc860f130afd3a))
* **mcp:** wire the gateway into the nine-tool surface with positionals ([d0bebf7](https://github.com/nevenincs/vaultspec-core/commit/d0bebf71fb2a2533d467c0241d283c56de006a7f))
* **statistic:** add CallRecord model and ExitStatus enum (P01.S02, P01.S03) ([5e0f4ba](https://github.com/nevenincs/vaultspec-core/commit/5e0f4bad3b202d8eec05f39118f828a95bd2fd3c))
* **statistic:** add ClaudeSource transcript adapter (P04 S11, S13) ([66165ab](https://github.com/nevenincs/vaultspec-core/commit/66165abbd5eeceba2299f64c9f126171a3a23f9c))
* **statistic:** add CodexSource rollout adapter (P04 S12, S14) ([8da2990](https://github.com/nevenincs/vaultspec-core/commit/8da29905a1faddbce9374687d086eef0e67ec1cb))
* **statistic:** add python -m statistic pipeline entrypoint (P05 S23) ([06211df](https://github.com/nevenincs/vaultspec-core/commit/06211df87604923353f083ad27ed23448ea37f6d))
* **statistic:** add seven metric families and report renderers (P05 S15-S22) ([434f6ba](https://github.com/nevenincs/vaultspec-core/commit/434f6ba22dad61e7fc9b4942d9f30deb6f283205))
* **statistic:** add stage-one command tokenizer (P03.S08) ([9e2f8ad](https://github.com/nevenincs/vaultspec-core/commit/9e2f8adb5487ff69a120158300423f5949ff14a7))
* **statistic:** add stage-two argv extractor (P03.S09) ([63b1ba4](https://github.com/nevenincs/vaultspec-core/commit/63b1ba4b1ef3440b87e958d5fcd7e94d284cfde2))
* **statistic:** add TranscriptSource protocol (P01.S04) ([ac7befe](https://github.com/nevenincs/vaultspec-core/commit/ac7befe6efc475942b3209e673ecb9d9d5d16240))
* **statistic:** parse declared-capability denominator from cli.md ([f4d4426](https://github.com/nevenincs/vaultspec-core/commit/f4d4426650e7de8631d193570dda71e3ac7c334d))
* **statistic:** scaffold dev-only analytics package tree (P01.S01) ([7dcecf1](https://github.com/nevenincs/vaultspec-core/commit/7dcecf1a6fb1af66e6f975764d6eb6f875a8bb4d))


### Bug Fixes

* **cli:** un-truncate the check markdown help for the discover payload ([4cdadc7](https://github.com/nevenincs/vaultspec-core/commit/4cdadc7c223c54ef060d27e1cd1a78e26a47bc10))
* **mcp:** pass stdin=DEVNULL so invoke does not inherit the server's JSON-RPC stdin ([f9727a0](https://github.com/nevenincs/vaultspec-core/commit/f9727a0f4a63993a783bd2d6963d1913b0205af2))
* **mcp:** reject dash-leading positionals in the invoke gateway ([7e544a4](https://github.com/nevenincs/vaultspec-core/commit/7e544a48a78f1d29fb47991b0c7847c64c121601))
* **mcp:** run handler body inside copied context for real request isolation ([7a2a5c1](https://github.com/nevenincs/vaultspec-core/commit/7a2a5c1a2af500e38dca60dcb4a7f732236155eb))
* normalize README markdown formatting ([f3a578a](https://github.com/nevenincs/vaultspec-core/commit/f3a578acbbf092603ff6b3bdc30746907d6ce584))
* **statistic:** divide loop token cost across expanded records; drop dead guard ([7ad37c1](https://github.com/nevenincs/vaultspec-core/commit/7ad37c13cc0accb887387fdddde58846b712507f))
* **statistic:** quote-aware connector split with no-silent-drop fallback ([1bfee11](https://github.com/nevenincs/vaultspec-core/commit/1bfee11730a8f2d82f453b69d37fdb58db55eeb2))
* **statistic:** redact home prefix from records.jsonl cwd and project ([e5058f0](https://github.com/nevenincs/vaultspec-core/commit/e5058f0bb1684b6f36d5831d66b4baee521de75d))
* **statistic:** substitute for-loop items literally; run real corpus (P05 S24) ([346849e](https://github.com/nevenincs/vaultspec-core/commit/346849e9966d8bf859d33eea91f75d9800688e50))
* **vaultcore:** reject embedded dots in feature/tag normalization ([bdae446](https://github.com/nevenincs/vaultspec-core/commit/bdae44638d773b3b452f84c3f92fe7eb67759c5d))

## [0.1.36](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.35...vaultspec-core-v0.1.36) (2026-06-28)


### Features

* **curator:** ADR architecture reconciliation + canonical status taxonomy ([e9e3f8d](https://github.com/nevenincs/vaultspec-core/commit/e9e3f8d62cf53700a6ab28124ec8be68481f8daa))
* **curator:** reframe curator as ADR architecture reconciliation + status taxonomy ([cc9b967](https://github.com/nevenincs/vaultspec-core/commit/cc9b967ad1d1eb8da8384335a382742b4d6131da))


### Bug Fixes

* **curator:** remediate code-review findings + add Verify audit ([4cd16fe](https://github.com/nevenincs/vaultspec-core/commit/4cd16fea0fe48e8fb5ad78f35f00a7d71f782774))
* **diagnosis:** route doctor parity through the canonical sync comparator ([5f72904](https://github.com/nevenincs/vaultspec-core/commit/5f729043f4889d72fbca7c509c2568f371f3404e))
* **diagnosis:** single comparator for install/sync/doctor parity ([fb7902c](https://github.com/nevenincs/vaultspec-core/commit/fb7902c029e4c54ed647a74044ef364d2a270e02))

## [0.1.35](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.34...vaultspec-core-v0.1.35) (2026-06-27)


### Features

* **builtins:** enrol rag-led hybrid discovery into the firmware ([ff647fe](https://github.com/nevenincs/vaultspec-core/commit/ff647fe310dae4c8b360ae7cb41a912b71a7b860))
* **builtins:** enrol rag-led hybrid discovery into the firmware ([475d40c](https://github.com/nevenincs/vaultspec-core/commit/475d40ce21953a99a10880a85baacac581826384))
* **rename:** add vault feature rename CLI command ([1b2dda1](https://github.com/nevenincs/vaultspec-core/commit/1b2dda1dc0371fda9e9570c19c99eb9a752ae6f1))
* **rename:** implement rename_feature backend with reverse-journal rollback ([eea3565](https://github.com/nevenincs/vaultspec-core/commit/eea35657146c162730435131446e6e18459a93bb))
* **rename:** uniform vault feature rename verb ([3b6b2c6](https://github.com/nevenincs/vaultspec-core/commit/3b6b2c63568088aa4e25a054f53a4a4871018512))
* **vault:** add read-only feature-rename-integrity check ([cb26096](https://github.com/nevenincs/vaultspec-core/commit/cb26096e021b56239cfd5944ec0312d8fb32f26a))
* **vault:** discover BOM docs and surface non-UTF-8 docs ([2538100](https://github.com/nevenincs/vaultspec-core/commit/253810076021592765c032b487c566a3f6702c4e))


### Bug Fixes

* **rename:** exclude archived docs from rename; tighten docs and dry-run ([4da78a9](https://github.com/nevenincs/vaultspec-core/commit/4da78a979e859c64f5288d8787213eec4da42974))
* **rename:** harden against out-of-bounds, symlink, and injection vectors ([e955be7](https://github.com/nevenincs/vaultspec-core/commit/e955be75442df725013b489d4f8d86265114c144))
* **rename:** preserve line endings and encodings byte-for-byte ([488c620](https://github.com/nevenincs/vaultspec-core/commit/488c620a0458b283c5f1d47954aa469137560b94))
* **rename:** resolve rename-convergence review findings ([25a6a78](https://github.com/nevenincs/vaultspec-core/commit/25a6a7832dba38e99eab81219e45e952a3250907))
* **vault:** refresh modified-stamp on classic-Mac CR-only documents ([f55ab0b](https://github.com/nevenincs/vaultspec-core/commit/f55ab0bf17f1a612bb545302bd944933f2cf5247))

## [0.1.34](https://github.com/nevenincs/vaultspec-core/compare/vaultspec-core-v0.1.33...vaultspec-core-v0.1.34) (2026-06-25)


### Features

* **cli:** bog-standard plain-Click help, uniform hints, no table-like output ([0cb6031](https://github.com/nevenincs/vaultspec-core/commit/0cb6031c2438d3e83212a2a3b6c6ad153ae30025))
* **firmware:** make codify user-triggered, mandate rag-grounded discovery ([055eb80](https://github.com/nevenincs/vaultspec-core/commit/055eb8072eb8ccc44f89313800b7288c54410fda))
* **hooks:** author agent-runtime hooks once, render per provider ([c26c03a](https://github.com/nevenincs/vaultspec-core/commit/c26c03aea51828787398d87650661d7f80d1e15e))
* model registries + Gemini/agy verification + provider hooks ([e655363](https://github.com/nevenincs/vaultspec-core/commit/e655363ed55fcaeae86c7c0f378b681e524c81da))
* **models:** refresh provider model registries and wire tier-based selection ([c40a90d](https://github.com/nevenincs/vaultspec-core/commit/c40a90d0fbf211489188c943db7c550e9d2abc28))
* **providers:** add Antigravity (agy) MCP config emission and pin Gemini drift test ([749623b](https://github.com/nevenincs/vaultspec-core/commit/749623b021b5b599411b48ecb9d2f4257fd44b2d))
* **providers:** embed rules inline in GEMINI.md so agy receives them ([db05fce](https://github.com/nevenincs/vaultspec-core/commit/db05fceeb033dcf4cfa897d7a1557892825c6311))
* **vault:** add placeholder/markdown checks and remove codify phase ([c552c8f](https://github.com/nevenincs/vaultspec-core/commit/c552c8fe0a3adf4da628829ba64028166882b6dd))


### Bug Fixes

* **cli:** adapt to typer 0.26 vendored click and drop deprecated loop policy ([50a5f22](https://github.com/nevenincs/vaultspec-core/commit/50a5f221d3ef1c16ff5f2351a31fbaa8a9803797))
* **cli:** gate sync next-action footers on hint suppression ([9bb776c](https://github.com/nevenincs/vaultspec-core/commit/9bb776ccebdcc7183c552665889f2f3620479f35))
* **hooks:** track hook ownership in a sidecar, not inside the native file ([e1fa036](https://github.com/nevenincs/vaultspec-core/commit/e1fa036346635f49b197c00e887dce2d67b37d69))
* **mcp:** render vaultspec-mcp help as plain Click, not a Rich panel ([87d0140](https://github.com/nevenincs/vaultspec-core/commit/87d0140d3b1f25a565e52968a4f4463a553b8537))

## [0.1.33](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.32...vaultspec-core-v0.1.33) (2026-06-18)


### Features

* **vault:** add rename verb for document file-rename with incoming-link rewrite ([#172](https://github.com/wgergely/vaultspec-core/issues/172)) ([c1f2bca](https://github.com/wgergely/vaultspec-core/commit/c1f2bca1c1619c65d11aab37d6b314cda22fa8af))

## [0.1.32](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.31...vaultspec-core-v0.1.32) (2026-06-16)


### Features

* **vault:** add set-body/set-frontmatter/edit verbs with blob-hash concurrency and conformance validation ([#168](https://github.com/wgergely/vaultspec-core/issues/168)) ([d375710](https://github.com/wgergely/vaultspec-core/commit/d3757108850cf41fcb657062e805ad9c1340b9d3))

## [0.1.31](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.30...vaultspec-core-v0.1.31) (2026-06-13)


### Features

* **cli:** plain-text output contract and status-discovery hardening ([7d71a7f](https://github.com/wgergely/vaultspec-core/commit/7d71a7f76a0e7a0a343054f43a6b061cf8ba8239))

## [0.1.30](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.29...vaultspec-core-v0.1.30) (2026-06-13)


### Features

* **vault:** ref-scoped graph, commit-linkage trailers, phase-summary scaffold, doctor + plan-mutator fixes ([c209baf](https://github.com/wgergely/vaultspec-core/commit/c209baf3cefe2b9c57be0bd3f5b3e85750292567))
* **vault:** ref-scoped graph, commit-linkage trailers, phase-summary scaffold, doctor and plan-mutator fixes ([dc984ff](https://github.com/wgergely/vaultspec-core/commit/dc984ffdcd0e5bedd1664fb2dbe48e1c6ef15f12)), closes [#153](https://github.com/wgergely/vaultspec-core/issues/153) [#157](https://github.com/wgergely/vaultspec-core/issues/157) [#158](https://github.com/wgergely/vaultspec-core/issues/158) [#159](https://github.com/wgergely/vaultspec-core/issues/159) [#160](https://github.com/wgergely/vaultspec-core/issues/160)

## [0.1.29](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.28...vaultspec-core-v0.1.29) (2026-06-12)


### Features

* **vault-orientation:** research, ADR, and L3 plan; fix plan-mutator crash without workspace context ([5948d04](https://github.com/wgergely/vaultspec-core/commit/5948d044f45475c25d5fd02f175a36e41ae20aa7))
* **vault-orientation:** W01.P01.S01 - add modified field and lenient date helpers to DocumentMetadata ([746d3de](https://github.com/wgergely/vaultspec-core/commit/746d3de80bee390579ef9154a529faa0e2251c85))
* **vault-orientation:** W01.P01.S02 - surface the modified stamp through typed metadata parsing ([b320b96](https://github.com/wgergely/vaultspec-core/commit/b320b960262eebf52f6b2a093f278be95e212fe3))
* **vault-orientation:** W01.P01.S03 - stamp modified equal to date at scaffold time ([f017a8c](https://github.com/wgergely/vaultspec-core/commit/f017a8c8d29bce590576fc0dd7d0b02dcd13265e))
* **vault-orientation:** W01.P02.S05 - add modified schema row to the research template ([f1bce28](https://github.com/wgergely/vaultspec-core/commit/f1bce28ecbcfddc149d071747e8f1a15b0f9a8f6))
* **vault-orientation:** W01.P02.S06 - add modified schema row to the reference template ([2dd0cac](https://github.com/wgergely/vaultspec-core/commit/2dd0cace63410f3e42a7284b2b59720962d69daf))
* **vault-orientation:** W01.P02.S07 - add modified schema row to the adr template ([b8d0f6f](https://github.com/wgergely/vaultspec-core/commit/b8d0f6ff1c8894652cae7587962ab938b9889d82))
* **vault-orientation:** W01.P02.S08 - add modified schema row to the plan template ([122e57a](https://github.com/wgergely/vaultspec-core/commit/122e57ae079ed8d1001802fe4c81cc2a6a900c9a))
* **vault-orientation:** W01.P02.S09 - add modified schema row to the exec-step template ([1df5ac6](https://github.com/wgergely/vaultspec-core/commit/1df5ac6dfcf27fa92c322738645b67cb261ce002))
* **vault-orientation:** W01.P02.S10 - add modified schema row to the exec-summary template ([59a3703](https://github.com/wgergely/vaultspec-core/commit/59a3703ae045149b379f2d68a39a3db179a9c69b))
* **vault-orientation:** W01.P02.S11 - add modified schema row to the audit template ([6613799](https://github.com/wgergely/vaultspec-core/commit/6613799597ade8e5bea1d3990a3bfe4079006c0f))
* **vault-orientation:** W01.P02.S12 - add modified schema row to the code-review template ([0082bdd](https://github.com/wgergely/vaultspec-core/commit/0082bdd76755afb3bba4484dd9e4c98a24c381d8))
* **vault-orientation:** W01.P02.S13 - add modified schema row to the index template ([9e2f91c](https://github.com/wgergely/vaultspec-core/commit/9e2f91ced1896d23f3248f93f22c27770c2484af))
* **vault-orientation:** W01.P03.S14 - refresh modified stamp on plan serialization writes ([4d4fafa](https://github.com/wgergely/vaultspec-core/commit/4d4fafa67ddd77bcb7180da74e5a0ab8fcfc9d00))
* **vault-orientation:** W01.P03.S15 - refresh both ADR stamps on supersession ([2324317](https://github.com/wgergely/vaultspec-core/commit/23243177f585457fcdd70d5b075049c2d5955c73))
* **vault-orientation:** W01.P03.S16 - refresh source audit stamp on rule promotion ([09e48c5](https://github.com/wgergely/vaultspec-core/commit/09e48c55a584123ea4c89e164be38500c461b235))
* **vault-orientation:** W01.P03.S17 - refresh target stamp on link mutations ([6499c6d](https://github.com/wgergely/vaultspec-core/commit/6499c6ded9f8fe633a84f1ee2f8c733cffdfe07a))
* **vault-orientation:** W01.P03.S18 - refresh stamps on repair-pipeline rewrites ([6f1e1e9](https://github.com/wgergely/vaultspec-core/commit/6f1e1e925434ac445c5b52652d8cd97eafbd5026))
* **vault-orientation:** W01.P03.S19 - add mutator stamp-refresh integration tests ([e676707](https://github.com/wgergely/vaultspec-core/commit/e6767078172af3bd354d27ec807b68d70878072b))
* **vault-orientation:** W01.P04.S20 - add modified-stamp checker ([1a5cc30](https://github.com/wgergely/vaultspec-core/commit/1a5cc3037aedddfd10e17b5fd744e23cddcd66d4))
* **vault-orientation:** W01.P04.S21 - register modified-stamp checker ([23eb111](https://github.com/wgergely/vaultspec-core/commit/23eb1110aafe28d7bae5c06760ec83227ddfc08c))
* **vault-orientation:** W01.P04.S22 - add modified-stamp checker tests ([0089219](https://github.com/wgergely/vaultspec-core/commit/00892197e64b5dce762d6e6cccbccaa06b933429))
* **vault-orientation:** W01.P04.S23 - add modified-stamp backfill migration ([2d7fa0d](https://github.com/wgergely/vaultspec-core/commit/2d7fa0deee0bfdb3f1a94f837a5f12608a8e6c40))
* **vault-orientation:** W01.P04.S24 - add backfill migration tests; reconcile checker with repair pipeline ([c75d08f](https://github.com/wgergely/vaultspec-core/commit/c75d08fe5b0a938f30431e4b080c700dd40a7b1e))
* **vault-orientation:** W02.P05.S25 - batched all-plans status collector sharing one exec-record index ([67aebf8](https://github.com/wgergely/vaultspec-core/commit/67aebf8ae8817bb77f5325e326274552725527c7))
* **vault-orientation:** W02.P05.S26 - orientation rollup and grounding-trace data layer ([246ea5e](https://github.com/wgergely/vaultspec-core/commit/246ea5e1c51aca84378789e6c3f38016597d1fc1))
* **vault-orientation:** W02.P05.S27 - orientation core tests over a real tmp_path vault ([df4f777](https://github.com/wgergely/vaultspec-core/commit/df4f7771fd5369569973a13bd9d7b18d6b6bef60))
* **vault-orientation:** W02.P06.S28 - add vault status verb with rollup and trace modes ([1caaf60](https://github.com/wgergely/vaultspec-core/commit/1caaf60de75470fc020ced2fb715373586237345))
* **vault-orientation:** W02.P06.S29 - add vault status cli tests for both modes, hints, and json schema ([014249b](https://github.com/wgergely/vaultspec-core/commit/014249b6dd1844742039fed382696a17ef94340e))
* **vault-orientation:** W03.P07.S30 - document modified frontmatter stamp ([b09e02a](https://github.com/wgergely/vaultspec-core/commit/b09e02a21218a25f3d33767c7cabbc4611170eee))
* **vault-orientation:** W03.P07.S31 - add vault status command row and orientation mandate ([ff7813c](https://github.com/wgergely/vaultspec-core/commit/ff7813ca21a865f5df8851c394c8df44564fca1c))
* **vault-orientation:** W03.P07.S32 - add zeroth-move orientation paragraph ([5e8e3f6](https://github.com/wgergely/vaultspec-core/commit/5e8e3f6b8eaaf87381e95d902abe05cc4524b09a))
* **vault-orientation:** W03.P07.S33 - add modified to curator allowed keys with repair note ([5f5b3db](https://github.com/wgergely/vaultspec-core/commit/5f5b3db4de6ab50b59f05c9f3cf83f7c62141df0))
* **vault-orientation:** W03.P08.S34 - vault status reference prose ([196cc07](https://github.com/wgergely/vaultspec-core/commit/196cc07b90a33b011f8cfb40f01d18ae79cc2293))
* **vault-orientation:** W03.P08.S35 - orientation and stamp in framework manual ([18b158c](https://github.com/wgergely/vaultspec-core/commit/18b158cfe56f7abfa1b7905644a56da15d590bd2))

## [0.1.28](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.27...vaultspec-core-v0.1.28) (2026-06-10)


### Features

* **cli-reference-automation:** add Typer-surface CLI-reference generator (P02.S05) ([8748cf7](https://github.com/wgergely/vaultspec-core/commit/8748cf77238be03cce700bc731de5cbb3cec8db7))
* **graph-backend:** add derived relatedness edge module (P02.S11) ([9f15f9e](https://github.com/wgergely/vaultspec-core/commit/9f15f9e5253fdc5fccb26a455757e0e7a18e0383))
* **graph-backend:** add ego-graph local scoping by node and depth (P02.S13) ([af444b0](https://github.com/wgergely/vaultspec-core/commit/af444b0347e4b835a827604aebfbd06e405afdae))
* **graph-backend:** add fingerprint graph cache module (P04.S28) ([a7ae650](https://github.com/wgergely/vaultspec-core/commit/a7ae65064124f955a863ad84c3f292eedcfdb4f8))
* **graph-backend:** add node, depth, derived toggles to vault graph (P02.S15) ([3bd0d8a](https://github.com/wgergely/vaultspec-core/commit/3bd0d8a92faa458c8830000e97cb9c05a3ebc6a2))
* **graph-backend:** add pagerank and in-degree node-size hints (P02.S12) ([ca5d3d1](https://github.com/wgergely/vaultspec-core/commit/ca5d3d1efa4161e0868cff419cbe0aaa9b0e2c74))
* **graph-backend:** attach kind, multiplicity, weight to explicit edges (P02.S10) ([0bf4947](https://github.com/wgergely/vaultspec-core/commit/0bf4947b0dd301204d47bb9d059f78b73ced38c8))
* **graph-backend:** bump graph JSON envelope to vaultspec.vault.graph.v2 (P01.S04) ([60a1e9a](https://github.com/wgergely/vaultspec-core/commit/60a1e9a6744d8c8eb084b65a897a90fd2f62961b))
* **graph-backend:** create vault link command group with list verb (P03.S21) ([9e69e8a](https://github.com/wgergely/vaultspec-core/commit/9e69e8a4348c9c2d79b0142c8192f146f5880984))
* **graph-backend:** emit derived edges and node hints in v2 payload (P02.S14) ([41a1b61](https://github.com/wgergely/vaultspec-core/commit/41a1b619c5ab0900cd4236bbf102134a18859bfc))
* **graph-backend:** implement vault link add with dangling refusal and dry-run (P03.S22) ([c123203](https://github.com/wgergely/vaultspec-core/commit/c1232032985cc4199c261c1e009a484ef872e5e2))
* **graph-backend:** implement vault link remove with no-op detection and dry-run (P03.S23) ([a25e019](https://github.com/wgergely/vaultspec-core/commit/a25e0199d67b07e755a20600d5280d77891c3948))
* **graph-backend:** invalidate graph cache from mutating verbs (P04.S30) ([f5fd041](https://github.com/wgergely/vaultspec-core/commit/f5fd0414d7fad3c2ffd52d23813c6d55c590650c))
* **graph-backend:** preserve link multiplicity via Counter (P02.S08) ([327abaa](https://github.com/wgergely/vaultspec-core/commit/327abaa6202c7a2e128d9b11f3391f98ec2b2895))
* **graph-backend:** register vault link group and regenerate CLI reference (P03.S24) ([7c258bd](https://github.com/wgergely/vaultspec-core/commit/7c258bdcd3234023763c0e8695a05ef476afd19b))
* **graph-backend:** thread per-target link counts through graph build (P02.S09) ([d5ceb4f](https://github.com/wgergely/vaultspec-core/commit/d5ceb4f41ec1b246341726c3a90e85cc301da1b2))
* **graph-backend:** wire graph cache load into construction (P04.S29) ([b7afca4](https://github.com/wgergely/vaultspec-core/commit/b7afca4a58c7aba4ff1b67d91b51eb0967ed5afe))


### Bug Fixes

* **cli-reference-automation:** distinct error for reversed region markers (GENREVIEW-001) ([d5c7016](https://github.com/wgergely/vaultspec-core/commit/d5c70166eaf9afa25a216616bcf4c67c5deadceb))
* **cli-reference-automation:** guard duplicated region markers (GENREVIEW-002) ([17a8d9c](https://github.com/wgergely/vaultspec-core/commit/17a8d9c6d57c5bdfd8046efc94af8200f96de71d))
* **cli-reference-automation:** lift template-name map to module scope (P01.S02) ([df23714](https://github.com/wgergely/vaultspec-core/commit/df237143c768e3de08267ad28d96c266212825cb))
* **cli-reference-automation:** make docs/CLI.md inventory generator-owned (GENREVIEW-003) ([327dcfc](https://github.com/wgergely/vaultspec-core/commit/327dcfc9328d4584b8a32f1957e22078e605cf82))
* **cli-reference-automation:** make spec reference group visible (P02.S05) ([9e8d53a](https://github.com/wgergely/vaultspec-core/commit/9e8d53a1f5c98858bc328290f557bc982963baae))
* **cli-reference-automation:** mark ref-audit.md legacy fallback for removal (P01.S01) ([dd11e7f](https://github.com/wgergely/vaultspec-core/commit/dd11e7f5d7dc3209018ad122527766901f9baf5c))
* **firmware:** legacy template-name fallback for stale workspaces (P09.S126) ([38da3f4](https://github.com/wgergely/vaultspec-core/commit/38da3f49ade421442da8a0ad487d28e08377940f))
* **graph-backend:** eliminate duplicate metrics pass in to_dict (P01.S03) ([364097d](https://github.com/wgergely/vaultspec-core/commit/364097d114fd02dd5069ef08719a74c1ccafd988))
* **graph-backend:** harden cache save and benchmark slack (P04 review M3, L3) ([d3bc283](https://github.com/wgergely/vaultspec-core/commit/d3bc2832ce9a6583d91705bf50b279862de15f4b))
* **graph-backend:** invalidate cache from remaining vault-mutating verbs (P04 review M1) ([35dc759](https://github.com/wgergely/vaultspec-core/commit/35dc759bd2acba651aab0f5ec2dceb9703c93934))
* **graph-backend:** normalise inline related: lists in surgery helper (P03 review C1) ([14de9ee](https://github.com/wgergely/vaultspec-core/commit/14de9eecc0be5756bd0bcc82b49fefefe14e20b2))
* **graph-backend:** pass explicit edges= key to node_link_data (P01.S01) ([e859d2a](https://github.com/wgergely/vaultspec-core/commit/e859d2ad1bb899d61132b3e2dd8bebf4c01384d1))
* **graph-backend:** sort _stem_index keys for cross-platform determinism ([8c7335c](https://github.com/wgergely/vaultspec-core/commit/8c7335c9f1e58a97a3dbb3d79d01141f6376039d))


### Performance

* **graph-backend:** scope derived-edge computation to the queried node set (P02 review HIGH-2) ([376a189](https://github.com/wgergely/vaultspec-core/commit/376a189178149e43ee4a3137d05cb4f3a70beea3))

## [0.1.27](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.26...vaultspec-core-v0.1.27) (2026-06-06)


### Bug Fixes

* support rules in project/ subdirectory in spec doctor ([#153](https://github.com/wgergely/vaultspec-core/issues/153)) ([66e7ac8](https://github.com/wgergely/vaultspec-core/commit/66e7ac80ab8b48a0a91d1c3d8a430a508a9684c2))

## [0.1.26](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.25...vaultspec-core-v0.1.26) (2026-06-05)


### Bug Fixes

* resolve plan serializer unexpected retirements and prune obsolete codex agents (fixes [#149](https://github.com/wgergely/vaultspec-core/issues/149), [#150](https://github.com/wgergely/vaultspec-core/issues/150)) ([e591380](https://github.com/wgergely/vaultspec-core/commit/e591380ca6b3633369b2becdde4cfa21a99fa048))

## [0.1.25](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.24...vaultspec-core-v0.1.25) (2026-06-02)


### Miscellaneous

* release 0.1.25 ([#147](https://github.com/wgergely/vaultspec-core/issues/147)) ([b0a0e98](https://github.com/wgergely/vaultspec-core/commit/b0a0e98e0d831bb5ce269e895fa4053ffdad9a46))

## [0.1.24](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.23...vaultspec-core-v0.1.24) (2026-06-02)


### Bug Fixes

* **codex:** dedupe agents tables in .codex/config.toml ([#140](https://github.com/wgergely/vaultspec-core/issues/140)) ([#141](https://github.com/wgergely/vaultspec-core/issues/141)) ([7ee3881](https://github.com/wgergely/vaultspec-core/commit/7ee38816a903f92c3fe0879f82f91c1eba456b47))
* **codex:** emit valid TOML for agent prompts containing ''' ([#143](https://github.com/wgergely/vaultspec-core/issues/143)) ([#144](https://github.com/wgergely/vaultspec-core/issues/144)) ([38c4b77](https://github.com/wgergely/vaultspec-core/commit/38c4b7771300717b9b1a0714d934cdcf3fd2fb45))
* **deps:** bump pyjwt 2.12.1 -&gt; 2.13.0 to clear advisories ([#142](https://github.com/wgergely/vaultspec-core/issues/142)) ([52747b6](https://github.com/wgergely/vaultspec-core/commit/52747b6f028e23e5c2a5155d7255d6386e44fe27))

## [0.1.23](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.22...vaultspec-core-v0.1.23) (2026-06-02)


### Performance

* **vaultcore:** parse frontmatter with libyaml CSafeLoader ([#137](https://github.com/wgergely/vaultspec-core/issues/137)) ([#138](https://github.com/wgergely/vaultspec-core/issues/138)) ([163db22](https://github.com/wgergely/vaultspec-core/commit/163db2226c45d7c8c986d4e551fb4c2ff5407873))

## [0.1.22](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.21...vaultspec-core-v0.1.22) (2026-06-02)


### Bug Fixes

* **sync:** backfill provider structural dirs + accurate dry-run preview ([#133](https://github.com/wgergely/vaultspec-core/issues/133), [#134](https://github.com/wgergely/vaultspec-core/issues/134)) ([#135](https://github.com/wgergely/vaultspec-core/issues/135)) ([6794df9](https://github.com/wgergely/vaultspec-core/commit/6794df913efef4b1c4cf4ffda5179c2cc3b3ae18))

## [0.1.21](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.20...vaultspec-core-v0.1.21) (2026-06-02)


### Bug Fixes

* **cli:** align exec filename validator with scaffolder and add mcp adopt ([#123](https://github.com/wgergely/vaultspec-core/issues/123), [#120](https://github.com/wgergely/vaultspec-core/issues/120)) ([#129](https://github.com/wgergely/vaultspec-core/issues/129)) ([ac96f3b](https://github.com/wgergely/vaultspec-core/commit/ac96f3b8e2e31d3703573f919637d222b11ef688))
* critical bugs - plan corruption ([#125](https://github.com/wgergely/vaultspec-core/issues/125)), doctor commit-block ([#122](https://github.com/wgergely/vaultspec-core/issues/122)), Windows cp1252 ([#111](https://github.com/wgergely/vaultspec-core/issues/111)) ([#126](https://github.com/wgergely/vaultspec-core/issues/126)) ([5b22a25](https://github.com/wgergely/vaultspec-core/commit/5b22a255a10100a95ce3922897a1593de73d910f))
* **migrations:** resolve manifest/migration version rough edges ([#119](https://github.com/wgergely/vaultspec-core/issues/119), [#121](https://github.com/wgergely/vaultspec-core/issues/121), [#124](https://github.com/wgergely/vaultspec-core/issues/124)) ([#132](https://github.com/wgergely/vaultspec-core/issues/132)) ([5bcb809](https://github.com/wgergely/vaultspec-core/commit/5bcb809a0e42b8690c2f178bca16d7fd39bf4523))

## [0.1.20](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.19...vaultspec-core-v0.1.20) (2026-05-26)


### Features

* **cli:** add --json to vault plan query for sibling parity (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([1d1a619](https://github.com/wgergely/vaultspec-core/commit/1d1a619000324f0a7004cf8526e8427aca6d9ea0))
* **cli:** add --json to vault plan tier show for read-command parity (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([f533d8e](https://github.com/wgergely/vaultspec-core/commit/f533d8ee14e8d92186f5612d6a2e9dd75d703467))
* **cli:** add --tier flag to vault add plan; close longest-lived audit friction (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([482205e](https://github.com/wgergely/vaultspec-core/commit/482205e7bc9b822641f0a1f7f2a4a246dd26c7e2))
* **cli:** add canonical outcome vocabulary for sync-shaped surfaces (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([c4a94aa](https://github.com/wgergely/vaultspec-core/commit/c4a94aae6a6d37f5b97ff52952555ba365de8ed1))
* **cli:** complete CLI CRUD simplification and next-step hints engine ([afe3616](https://github.com/wgergely/vaultspec-core/commit/afe36162060f438ec6e785d1f2df37b44f0ec461))
* **cli:** envelope the migrations --json output (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([2585506](https://github.com/wgergely/vaultspec-core/commit/25855061df0e75e12cebcb6cfebd5e823c85d869))
* **cli:** envelope the vault --json commands (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([6e8df18](https://github.com/wgergely/vaultspec-core/commit/6e8df18c8544c3db4dd7ecc3e914e5c08c269bdd))
* **cli:** envelope the vault plan --json commands (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([1331c3b](https://github.com/wgergely/vaultspec-core/commit/1331c3be2b5e108f58ec40f48afb79215bdcc307))
* **cli:** route install --upgrade through the canonical outcome renderer (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([30595b0](https://github.com/wgergely/vaultspec-core/commit/30595b0ae58a9b85ab3b5ab23f646d5d77c74818))
* **cli:** route migrations run through the canonical outcome renderer (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([50d8d50](https://github.com/wgergely/vaultspec-core/commit/50d8d50ce105272b452f533dc8423b40cb7e1b93))
* **cli:** route spec sync commands through the canonical outcome renderer (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([9e5b459](https://github.com/wgergely/vaultspec-core/commit/9e5b4591c404c7017cce34fe60923d8c370cc874))
* **cli:** route the main sync command through a grouped outcome renderer (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([88c811e](https://github.com/wgergely/vaultspec-core/commit/88c811e15afd01dd909712c1179d42bda9e7aa7f))
* **cli:** skip HTML-comment placeholders in hydration warning (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([673a5fb](https://github.com/wgergely/vaultspec-core/commit/673a5fb3aee2d5ee41c2b25452e1d1dcc43e20fd))
* **cli:** state the spec-layer sharing policy on install and upgrade (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([04d2ad3](https://github.com/wgergely/vaultspec-core/commit/04d2ad3c16ddbc1a601320dc148741f312e01521))
* **cli:** tier promote refuses TODO placeholders, requires real flags (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([e2d22d7](https://github.com/wgergely/vaultspec-core/commit/e2d22d7abec4dbc91f2fbb89a2962b3d8590ad59))
* **cli:** wrap sync-family --json in the canonical envelope (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([d6dae81](https://github.com/wgergely/vaultspec-core/commit/d6dae81251a61090a7e69a28165b95ab0005e620))
* **cli:** wrap the vault check family --json in the canonical envelope (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([1ccf649](https://github.com/wgergely/vaultspec-core/commit/1ccf649192296f744c83065ef0c2b53bbba8296f))
* **gitignore:** make the spec layer team-shared by default (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([c10c778](https://github.com/wgergely/vaultspec-core/commit/c10c778aa1b28d7a8de7cd1beea011bb2de77be3))
* **migrations:** rewrite stale gitignore blocks to the shared policy (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([6eac911](https://github.com/wgergely/vaultspec-core/commit/6eac9119d81145680cd7e9d537ebd61d38634e6c))


### Bug Fixes

* **ci:** fall back when uv audit cannot decode OSV response ([1262aee](https://github.com/wgergely/vaultspec-core/commit/1262aee0c9ca41c0bccaa1a9147e8f7b700488fc))
* **ci:** make the dependency audit resilient to uv's OSV decoder bug (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([5e1ff91](https://github.com/wgergely/vaultspec-core/commit/5e1ff919df0ac934525599d68fcdc987d76121ae))
* **ci:** reconcile cli simplification checks ([5e740b9](https://github.com/wgergely/vaultspec-core/commit/5e740b97f46e9dcd5ed84d1186462e9716c17c85))
* **ci:** repair markdown formatting + close W01.P03.S07 emit-time validator (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([0946b22](https://github.com/wgergely/vaultspec-core/commit/0946b22b4a96e5fa8f2e16e59477097c3f5a1f16))
* **ci:** resolve Dependency Audit failures (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([bb24a07](https://github.com/wgergely/vaultspec-core/commit/bb24a070be3c33632921c08230b64acc2c774540))
* **ci:** use unconditional --ignore for disputed pyjwt advisory (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([6036e48](https://github.com/wgergely/vaultspec-core/commit/6036e48d99801ed9d52b3f510db42dd2592719d8))
* **cli:** accept bare names in spec revert and honor --json (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([8fc0b6f](https://github.com/wgergely/vaultspec-core/commit/8fc0b6f45ae715ac0df017dc8f12d64fb8645f1d))
* **cli:** emit JSON error envelopes under --json (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([4f6f66c](https://github.com/wgergely/vaultspec-core/commit/4f6f66caa23634ca9024a0b9bb5b6b59b6c0dca8))
* **cli:** fail cleanly when the editor cannot launch (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([4b1169f](https://github.com/wgergely/vaultspec-core/commit/4b1169f6d4f41840520887c3516fd4e3a5bfa96c))
* **cli:** harden the sync "0 files" guard against the unchanged/skipped split (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([017358b](https://github.com/wgergely/vaultspec-core/commit/017358b01c477c566b56f9d3569b544459ad672f))
* **cli:** hide the developer-only --dev flag from --help (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([27539e8](https://github.com/wgergely/vaultspec-core/commit/27539e871b730b364168143aba24147d187de599))
* **cli:** honor --json on errors across the spec and vault commands (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([b55d72d](https://github.com/wgergely/vaultspec-core/commit/b55d72d0c031435cf1afce860ba963313ab13b5c))
* **cli:** keep vault add --json stdout free of advisory text (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([6d0293e](https://github.com/wgergely/vaultspec-core/commit/6d0293ef3aa9cf40400849102856875bae9de69e))
* **cli:** make check --fix guidance honest in the text output (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([415435a](https://github.com/wgergely/vaultspec-core/commit/415435ade81c018fde861a1f460316a824968154))
* **cli:** make sync --dry-run --json emit the canonical envelope (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([f57d790](https://github.com/wgergely/vaultspec-core/commit/f57d790e1e9a5060ab1ff9b0181a999b6fbaff27))
* **cli:** make vault graph a plain command, not a subcommand-less group (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([6bd190f](https://github.com/wgergely/vaultspec-core/commit/6bd190f949105c62a90c47795b773eecd7530cf9))
* **cli:** quiet the scoped-sync notice and stamp the upgrade version (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([114dade](https://github.com/wgergely/vaultspec-core/commit/114dadeebf9be6c122df51235d8bf7baeceb8f39))
* **cli:** repair system/mcps sync output broken by S05 routing (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([4aad490](https://github.com/wgergely/vaultspec-core/commit/4aad49095551a4ebffc7e89e42247ab8d3bb9819))
* **cli:** repair the install --upgrade --dry-run crash and stub preview (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([783e74f](https://github.com/wgergely/vaultspec-core/commit/783e74fddbf173053901b899f825b56715a0c014))
* **cli:** stop the resolver warning about state install --upgrade fixes (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([35eee4c](https://github.com/wgergely/vaultspec-core/commit/35eee4ce518dcbf58c471a34993dfba48fd68aca))
* reconcile gitignore, tier-promote bug, audit contract test (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([a461a9c](https://github.com/wgergely/vaultspec-core/commit/a461a9c1f6ca3d2755e306262b95a4ee48d124f4))
* **vault:** escape diagnostic text so [[wiki-links]] render intact (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([c0d8bd9](https://github.com/wgergely/vaultspec-core/commit/c0d8bd9c2bc08dc73fdec4eec2c3eb53e16ff091))
* **vault:** keep related: valid YAML when repair removes all entries (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([822e375](https://github.com/wgergely/vaultspec-core/commit/822e37563fbc1ccf68f3b72059f9ac31a14b9884))
* **vault:** refuse to archive on an empty feature tag (refs [#113](https://github.com/wgergely/vaultspec-core/issues/113)) ([0e57f0b](https://github.com/wgergely/vaultspec-core/commit/0e57f0bf51ef464570293dd84eef48f27fba0308))

## [0.1.19](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.18...vaultspec-core-v0.1.19) (2026-05-14)


### Features

* **plan:** repair duplicate steps and support alpha suffix insertion ([7ad950a](https://github.com/wgergely/vaultspec-core/commit/7ad950ab2fcd21ddf8338aa9c35d9f3295cd6257))


### Bug Fixes

* **doctor:** suppress false provider drift diagnostics ([32a8144](https://github.com/wgergely/vaultspec-core/commit/32a8144cc6a59a2ad9ecaddf4bb8fceb8b277820))
* **migrations:** remove generated index duplicates ([e3e1a7d](https://github.com/wgergely/vaultspec-core/commit/e3e1a7d3d929c37fe97bd47629a0536931e801a6))
* **precommit:** make all-files hooks respect release-please changelog ([6bd8f96](https://github.com/wgergely/vaultspec-core/commit/6bd8f969a6afbb18b0a1691b1410fde92aab160f))

## [0.1.18](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.17...vaultspec-core-v0.1.18) (2026-05-06)


### Features

* **#95:** versioned migration registry; auto-migrate on upgrade and graph load ([#96](https://github.com/wgergely/vaultspec-core/issues/96)) ([2549554](https://github.com/wgergely/vaultspec-core/commit/2549554cf4bd6c886119da0310682166eecf2b88))

## [0.1.17](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.16...vaultspec-core-v0.1.17) (2026-05-05)


### Features

* **#91:** migrate feature indexes into .vault/index/ subfolder ([#92](https://github.com/wgergely/vaultspec-core/issues/92)) ([a71e979](https://github.com/wgergely/vaultspec-core/commit/a71e97977aef00a3709987ffbf4c8e217f066a39))
* **plan-hardening:** row-per-Step plan convention + vault plan CLI ([#102](https://github.com/wgergely/vaultspec-core/issues/102)) ([7298100](https://github.com/wgergely/vaultspec-core/commit/7298100d22324195db99436bc2aa705b96007335))


### Bug Fixes

* **#93:** drop spec-check false positive on source repo ([#94](https://github.com/wgergely/vaultspec-core/issues/94)) ([f1eae92](https://github.com/wgergely/vaultspec-core/commit/f1eae92bd253ecaa639ae12e2dfa68722fc1d8ec))
* **#98,#99:** repair two pre-existing test failures on source repo ([#100](https://github.com/wgergely/vaultspec-core/issues/100)) ([903b525](https://github.com/wgergely/vaultspec-core/commit/903b525bb987851a24900f805fb88afd8902d397))

## [0.1.16](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.15...vaultspec-core-v0.1.16) (2026-04-27)


### Bug Fixes

* **#88:** drop env-var bypass, gate dev-mode on explicit --dev flag ([#89](https://github.com/wgergely/vaultspec-core/issues/89)) ([2277331](https://github.com/wgergely/vaultspec-core/commit/2277331774361507cc5a9859bf8ae2fc97b6bf0b))

## [0.1.15](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.14...vaultspec-core-v0.1.15) (2026-04-27)


### Bug Fixes

* **#85:** lazy YAML representer + uv-native audit gate ([#86](https://github.com/wgergely/vaultspec-core/issues/86)) ([d03f47e](https://github.com/wgergely/vaultspec-core/commit/d03f47ec3caad94805a24af23ebd8ac0d735ab40))

## [0.1.14](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.13...vaultspec-core-v0.1.14) (2026-04-21)


### Bug Fixes

* **#80:** Gemini round-8 follow-up on merged PR [#83](https://github.com/wgergely/vaultspec-core/issues/83) ([a14ff9f](https://github.com/wgergely/vaultspec-core/commit/a14ff9f61f7443ebc446462db4727cc88f802e7f)), closes [#80](https://github.com/wgergely/vaultspec-core/issues/80)
* **#80:** install-layer hygiene + audit-driven hardening ([#83](https://github.com/wgergely/vaultspec-core/issues/83)) ([ab13b6e](https://github.com/wgergely/vaultspec-core/commit/ab13b6e232b093664208d454ba7a39e8e1441e3b)), closes [#80](https://github.com/wgergely/vaultspec-core/issues/80)
* **ci:** exclude gemini/claude live-CLI tests from unit run ([9cc21db](https://github.com/wgergely/vaultspec-core/commit/9cc21db7589d2bca0eb91d2255b71da79cfdbd24))

## [0.1.13](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.12...vaultspec-core-v0.1.13) (2026-04-12)


### Bug Fixes

* **#76:** correct Gemini tool identifiers + add live drift + load tests ([#78](https://github.com/wgergely/vaultspec-core/issues/78)) ([c329276](https://github.com/wgergely/vaultspec-core/commit/c329276fada06ca6b5288119c0d0a8d2d253b552)), closes [#76](https://github.com/wgergely/vaultspec-core/issues/76)

## [0.1.12](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.11...vaultspec-core-v0.1.12) (2026-04-12)


### Bug Fixes

* **#76:** per-provider agent renderer for Gemini ([#77](https://github.com/wgergely/vaultspec-core/issues/77)) ([d75dafa](https://github.com/wgergely/vaultspec-core/commit/d75dafa53bd6e5ac265cccca68391925221811c8))
* use gh api for publish dispatch instead of gh workflow run ([87d6f90](https://github.com/wgergely/vaultspec-core/commit/87d6f904ca4843b743b4fe58ee8b30e712b78639))

## [0.1.11](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.10...vaultspec-core-v0.1.11) (2026-04-12)


### Bug Fixes

* **testing:** address codex review on synthetic.py inputs ([360a46c](https://github.com/wgergely/vaultspec-core/commit/360a46c2907ff7f524c171a68370e53f2bc4852a))
* **testing:** address gemini-code-assist review on synthetic.py ([e7a9788](https://github.com/wgergely/vaultspec-core/commit/e7a9788adb3ac8bd8ea7556bf2e9a86417f2762d))

## [0.1.10](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.9...vaultspec-core-v0.1.10) (2026-04-12)


### Features

* reconciling mcp_sync — prune orphaned managed entries ([166ba69](https://github.com/wgergely/vaultspec-core/commit/166ba69727c8b0d5f1f452c381caa4772a1fec63))
* reconciling mcp_sync — prune orphaned managed entries ([9d913bb](https://github.com/wgergely/vaultspec-core/commit/9d913bb8f01db3a3865eb79bdb48b0a5f911ac13))


### Bug Fixes

* **ci:** auto-dispatch publish from release-please on release creation ([46d0cb3](https://github.com/wgergely/vaultspec-core/commit/46d0cb3967ad00ff3b397c396514e02a4bbf3c7a)), closes [#65](https://github.com/wgergely/vaultspec-core/issues/65)
* **mcps:** preserve user top-level keys when pruning empties .mcp.json ([4a4f773](https://github.com/wgergely/vaultspec-core/commit/4a4f77356519461a9f533771e484234d7af281fd))
* **mcps:** security hardening — parse-failure prune gate + legacy migration audit log ([4317d54](https://github.com/wgergely/vaultspec-core/commit/4317d5432a799d5b00494b92a70cc177fe964b81))
* trigger PyPI publish automatically on release-please releases ([ba1c4dd](https://github.com/wgergely/vaultspec-core/commit/ba1c4dd6710cd77d8091a43266fd9200d5cbe886))

## [0.1.9](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.8...vaultspec-core-v0.1.9) (2026-04-11)


### Features

* vaultspec-projectmanager skill + agent ([#63](https://github.com/wgergely/vaultspec-core/issues/63)) ([dcc0a4f](https://github.com/wgergely/vaultspec-core/commit/dcc0a4fb981ad00282f363df56999d6ccce59e6d))


### Bug Fixes

* add 'mcps' to resource_labels in sync all ([b537234](https://github.com/wgergely/vaultspec-core/commit/b537234c724d44495de8bff19c9b8207cc010f47))
* address Gemini review - blocking Windows lock, RMW scope, deadlock safety ([4aa5081](https://github.com/wgergely/vaultspec-core/commit/4aa5081aa5cd3c138f15f0f9eb96b4e1f56c807c))
* advisory file locking for .mcp.json and scaffold operations ([04bb71a](https://github.com/wgergely/vaultspec-core/commit/04bb71a6707597c8013ce451a807b928b000249f))
* advisory file locking for scaffold read-modify-write operations ([c777977](https://github.com/wgergely/vaultspec-core/commit/c7779777a5fbb66f714e843d63221f1653edd482)), closes [#49](https://github.com/wgergely/vaultspec-core/issues/49)
* allow .vault/data/ in vault check structure ([#59](https://github.com/wgergely/vaultspec-core/issues/59)) ([5647150](https://github.com/wgergely/vaultspec-core/commit/56471500e0b0bdf55b53edc420254626539af24a))
* include .vaultspec/rules in sdist so PyPI publish succeeds ([#62](https://github.com/wgergely/vaultspec-core/issues/62)) ([de9a3a7](https://github.com/wgergely/vaultspec-core/commit/de9a3a736424c46f4bdba2a21916b830208f0041)), closes [#60](https://github.com/wgergely/vaultspec-core/issues/60)
* refine .gitignore to preserve .vault/ tracked content ([0bdfdff](https://github.com/wgergely/vaultspec-core/commit/0bdfdff1e6cf2d9cf00bc9ab116a3bdd516ae1b5))
* skip advisory lock when parent directory does not exist ([a1faf8e](https://github.com/wgergely/vaultspec-core/commit/a1faf8ec4162832113b7322dde5b7f9e00dd0602))

## [0.1.8](https://github.com/wgergely/vaultspec-core/compare/vaultspec-core-v0.1.7...vaultspec-core-v0.1.8) (2026-04-11)


### Features

* add check-providers CLI command and doctor precommit row ([0505953](https://github.com/wgergely/vaultspec-core/commit/05059536b1d9f571376c3f02c49238cebf43f4f7)), closes [#47](https://github.com/wgergely/vaultspec-core/issues/47)
* add MCP server registry with install/sync/uninstall lifecycle ([73eb7a3](https://github.com/wgergely/vaultspec-core/commit/73eb7a31bc3fbc90de2c07c8716a7390d9d9c05a)), closes [#43](https://github.com/wgergely/vaultspec-core/issues/43)
* add precommit_managed manifest flag and opt-out mechanism ([fc6b385](https://github.com/wgergely/vaultspec-core/commit/fc6b38551e64947aa33ceeb65f9f1715feed6ba1))
* **gitattributes:** scaffold .gitattributes in install/sync/doctor ([389114c](https://github.com/wgergely/vaultspec-core/commit/389114c72d5ba05873845bee692e292b08e9f851))
* **gitattributes:** scaffold and manage .gitattributes via install/sync/doctor ([46d212a](https://github.com/wgergely/vaultspec-core/commit/46d212a5d6f982d23bd5a90a6bd43a42145b720f)), closes [#35](https://github.com/wgergely/vaultspec-core/issues/35)
* MCP server registry — built-in MCP definitions with install/sync/uninstall lifecycle ([02df71a](https://github.com/wgergely/vaultspec-core/commit/02df71a92c516638377e99789b8eb02427c8dbe6))
* standardize CLI force/warning/dry-run across all facades ([8ea2f62](https://github.com/wgergely/vaultspec-core/commit/8ea2f62a7a982e7969dc39545d1909119208de76))
* standardize pre-commit hook scaffolding across consumer projects ([4c616d4](https://github.com/wgergely/vaultspec-core/commit/4c616d4a2239fabcf3d4c52ba846fecccba7da6b))
* standardize pre-commit hook scaffolding across consumer projects ([ec8bcb4](https://github.com/wgergely/vaultspec-core/commit/ec8bcb4c5f22e8a85156bb4d0e08c800457e4283)), closes [#36](https://github.com/wgergely/vaultspec-core/issues/36)


### Bug Fixes

* address code review - foreign content check and cwd fallback warning ([04bd46a](https://github.com/wgergely/vaultspec-core/commit/04bd46a596e0cf4bbc4ee8db15bb3fdc75a599d9))
* address code review findings for doctor namespace move ([2785754](https://github.com/wgergely/vaultspec-core/commit/278575414bb378b92de043aed61477f1e7bca737))
* address code review findings for MCP registry ([64ae9ae](https://github.com/wgergely/vaultspec-core/commit/64ae9aedeef360aa353b5bda42fcc069432db8d6))
* address code review findings from external review ([3be56a4](https://github.com/wgergely/vaultspec-core/commit/3be56a4a6676ef82ccb85afc95260b7ec7a44ed0))
* address code review findings from external review ([d3cb7d1](https://github.com/wgergely/vaultspec-core/commit/d3cb7d1c94b3394e003c01d1e374333290253a90))
* construct default help menu manually to avoid shell PATH issues ([c9fdb5a](https://github.com/wgergely/vaultspec-core/commit/c9fdb5a4feed3b81d7368d1ee8fb2332c97b9996))
* docstring corrections and missing ADR2 test coverage ([bac4302](https://github.com/wgergely/vaultspec-core/commit/bac43027c22515bab88d1696a76aaff4dbe1bed0))
* **doctor:** exclude synthesized builtin files from stale detection ([a6d315a](https://github.com/wgergely/vaultspec-core/commit/a6d315a53cd54a54975421b7feb27b71306cd68b))
* **doctor:** exclude synthesized builtin files from stale detection ([4edb6e1](https://github.com/wgergely/vaultspec-core/commit/4edb6e1ca747795ef1f1ffe8b843cf9babef6876)), closes [#34](https://github.com/wgergely/vaultspec-core/issues/34)
* ecosystem CI health - doctor/sync, hooks, contract tests ([c753ce9](https://github.com/wgergely/vaultspec-core/commit/c753ce97ccfee90059c0bf7b8bfe2e8415aa8a32))
* exclude .vault/ from managed gitignore block ([a5f8a53](https://github.com/wgergely/vaultspec-core/commit/a5f8a53e6b27fc851498289b1c229e51e9e69fb5))
* exclude .vault/ from managed gitignore block ([f292532](https://github.com/wgergely/vaultspec-core/commit/f29253220fe9df1d316458f53b1aa0ceda314f3e)), closes [#50](https://github.com/wgergely/vaultspec-core/issues/50)
* **gitattributes:** remove redundant scoped imports, add integration tests ([78f27e6](https://github.com/wgergely/vaultspec-core/commit/78f27e6a2d4f2ea4b0f2f579356903b866367e84))
* **git:** enforce eol=lf for markdown files to fix mdformat errors on Windows ([10ebd58](https://github.com/wgergely/vaultspec-core/commit/10ebd58a6e25a7856a0dc9af59433a08abb88f9c))
* harden MCP name validation across add and remove paths ([669292e](https://github.com/wgergely/vaultspec-core/commit/669292ebd0cf65dc832a677cec9c44ebb12bb8c7))
* include mcps label in sync output when MCP pass is active ([4df0208](https://github.com/wgergely/vaultspec-core/commit/4df02080d7a037ddc5f0ded026cfd95c96554c8b))
* input validation, shadowing, and remove priority in MCP registry ([e052d15](https://github.com/wgergely/vaultspec-core/commit/e052d158178df7726d7d3e858cc7dfb465555b44))
* **justfile:** convert all recipes to powershell syntax to fix pathing and comply with project instructions ([6c505ea](https://github.com/wgergely/vaultspec-core/commit/6c505ea95260d0f73e55237a25d9a45d59fc9614))
* **justfile:** use official cross-platform shell configuration for pwsh ([21dcd81](https://github.com/wgergely/vaultspec-core/commit/21dcd81dee04ae70db5fed64f408df073a5ee06f))
* rename generated '## Available Skills' header to '## Vaultspec Skills' ([9fc84e6](https://github.com/wgergely/vaultspec-core/commit/9fc84e600cfa08f269067081351792ef303af2e2))
* rename generated '## Rules' header to '## Vaultspec Rules' ([c7f08d6](https://github.com/wgergely/vaultspec-core/commit/c7f08d64c6737a4e3fdf521e86b243bcf33adc3b))
* rename generated '## Rules' header to '## Vaultspec Rules' ([2a5e349](https://github.com/wgergely/vaultspec-core/commit/2a5e349858195a53537bc8893b556f5f5b25881a)), closes [#44](https://github.com/wgergely/vaultspec-core/issues/44)
* resolve doctor/sync false positives, stale contract tests, and hook engine cwd crash ([850d219](https://github.com/wgergely/vaultspec-core/commit/850d21998955d14b4a85da48c8bacb5715495e05)), closes [#37](https://github.com/wgergely/vaultspec-core/issues/37)
* run MCP uninstall before directory removal in uninstall_run ([188c2c7](https://github.com/wgergely/vaultspec-core/commit/188c2c790633ceafe79edfb54378cf98dcb6f149))
* update ConfigSignal enum member test for REGISTRY_DRIFT ([e92fc77](https://github.com/wgergely/vaultspec-core/commit/e92fc773d333e62548cad608a09dd1e7b365564d))


### Performance

* hoist managed hook ID set to module-level constant ([c787c78](https://github.com/wgergely/vaultspec-core/commit/c787c78f0823e59b84a8f5692e289eacc6397cda))

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
