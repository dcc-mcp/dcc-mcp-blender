# Changelog

## [0.1.9](https://github.com/dcc-mcp/dcc-mcp-blender/compare/v0.1.8...v0.1.9) (2026-06-07)


### Bug Fixes

* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([#74](https://github.com/dcc-mcp/dcc-mcp-blender/issues/74)) ([7f95128](https://github.com/dcc-mcp/dcc-mcp-blender/commit/7f95128d9668f0600ef45e260b13719c8e67bc81))
* **ci:** remove github.token fallback from release-please token ([739845f](https://github.com/dcc-mcp/dcc-mcp-blender/commit/739845f5ffa9c69d90cc604c0bed1f31c7decb6a))

## [0.1.8](https://github.com/dcc-mcp/dcc-mcp-blender/compare/v0.1.7...v0.1.8) (2026-06-06)


### Features

* add blender-render-farm skill with Deadline and Flamenco support ([b9c136c](https://github.com/dcc-mcp/dcc-mcp-blender/commit/b9c136cfb6587f4080b9b199f1a72d66bad096de))

## [0.1.7](https://github.com/dcc-mcp/dcc-mcp-blender/compare/v0.1.6...v0.1.7) (2026-06-05)


### Features

* **blender:** bump dcc-mcp-core floor to &gt;=0.18.2 (PIP-571) ([a82ca5f](https://github.com/dcc-mcp/dcc-mcp-blender/commit/a82ca5f32446ea3a3af5d13dbe02fa87b12954e7))
* migrate repo references from loonghao to dcc-mcp org ([71dadfe](https://github.com/dcc-mcp/dcc-mcp-blender/commit/71dadfe0d3ea34daadefbebb3970261a0a4d8493))


### Bug Fixes

* add release-please version marker to packaging entry for auto-sync ([38c7b1a](https://github.com/dcc-mcp/dcc-mcp-blender/commit/38c7b1a0530f320feafb80835071052b068f6b76))
* apply ruff format to packaging/addon_entry/__init__.py ([4f1ab1b](https://github.com/dcc-mcp/dcc-mcp-blender/commit/4f1ab1b0b76110f5551fa7bd65e63cabdfc83e36))
* GUI add-on Extension install readiness + docs + metadata uplift (GH [#59](https://github.com/dcc-mcp/dcc-mcp-blender/issues/59)-[#62](https://github.com/dcc-mcp/dcc-mcp-blender/issues/62)) ([f58de0f](https://github.com/dcc-mcp/dcc-mcp-blender/commit/f58de0fd8944c32c69c0063c9bd1318520356c00))
* sync bl_info version to 0.1.6 to match release-please bump ([0e759d5](https://github.com/dcc-mcp/dcc-mcp-blender/commit/0e759d54bdca63512a024a16ee5026b8e2665f77))
* update test version assertions to match 0.1.6 release-please bump ([960ee0f](https://github.com/dcc-mcp/dcc-mcp-blender/commit/960ee0fceed03da5cef57669ad9d88b58f8ef1aa))
* use dynamic version in addon packaging tests instead of hardcoded value ([be42e94](https://github.com/dcc-mcp/dcc-mcp-blender/commit/be42e94cec531c47731cbf949505141ed8fb4e86))

## [0.1.6](https://github.com/loonghao/dcc-mcp-blender/compare/v0.1.5...v0.1.6) (2026-06-01)


### Features

* add latest dcc-mcp-core integrations and agent install skill ([3bfd7fb](https://github.com/loonghao/dcc-mcp-blender/commit/3bfd7fb75c1705be5079851a0624e65f9aecd2fc))
* update core integrations alignment with core-0.17.47 ([2fc658c](https://github.com/loonghao/dcc-mcp-blender/commit/2fc658c58bd836438ec7eea34f79518ed40faadc))


### Bug Fixes

* align bl_info version to 0.1.5 in addon entry and tests ([67dd390](https://github.com/loonghao/dcc-mcp-blender/commit/67dd3909a5a6dd5647274cc068431c2953dcc6d6))

## [0.1.5](https://github.com/loonghao/dcc-mcp-blender/compare/v0.1.4...v0.1.5) (2026-05-26)


### Features

* add blender asset validation pipeline tools ([#55](https://github.com/loonghao/dcc-mcp-blender/issues/55)) ([8ccce34](https://github.com/loonghao/dcc-mcp-blender/commit/8ccce34f1ca0c20a343a2d3094d46ea2324d2f08))
* add blender dev diagnostic tools ([883d932](https://github.com/loonghao/dcc-mcp-blender/commit/883d93262cf44730f88e58efc67f314a56acc935))
* add blender interchange export tools ([ed7e43c](https://github.com/loonghao/dcc-mcp-blender/commit/ed7e43cf05413280fa0eb670cc4209b7c6d3fda6))
* add blender light rig environment tools ([c7ed744](https://github.com/loonghao/dcc-mcp-blender/commit/c7ed7449b1d1b52bc72b0b646d60a133e59e53f6))
* add blender material library bake tools ([#56](https://github.com/loonghao/dcc-mcp-blender/issues/56)) ([340f09a](https://github.com/loonghao/dcc-mcp-blender/commit/340f09a6ad4a90f06d3c53daf9e26fecc712afef))
* add blender mesh and scene operations ([ea48a18](https://github.com/loonghao/dcc-mcp-blender/commit/ea48a184bd5a9c40c7d2619047b88b2cf5ff16b8))
* add blender rigging and pose operations ([a8bb237](https://github.com/loonghao/dcc-mcp-blender/commit/a8bb237685b72a044693bf1b23c0d0bf92c5f854))
* add blender uv operations skill ([1481eb7](https://github.com/loonghao/dcc-mcp-blender/commit/1481eb75f4835eb8dfcf31eab047140e69eef03e))
* expand blender node graph tools ([d463d28](https://github.com/loonghao/dcc-mcp-blender/commit/d463d2810cc5dc68f3e04930ac69ef005ee1febe))
* expand blender simulation physics tools ([56994e8](https://github.com/loonghao/dcc-mcp-blender/commit/56994e8f84b0ea19315e03acd823fa46c71d648b))


### Bug Fixes

* align blender dispatcher with core pump ([81b382a](https://github.com/loonghao/dcc-mcp-blender/commit/81b382aaedf343f65829c2b73843e14a2dcdd26b))
* repair blender addon startup ([008c078](https://github.com/loonghao/dcc-mcp-blender/commit/008c078edaff1dd7d39de9022673ecd2dc66629b))


### Code Refactoring

* simplify blender dispatcher with core interfaces ([f86d663](https://github.com/loonghao/dcc-mcp-blender/commit/f86d663b689163332a30039a2662419194c6aadb))


### Documentation

* add blender skills index ([812aac4](https://github.com/loonghao/dcc-mcp-blender/commit/812aac4fe597f60ba9ada187f30fe2034d812815))

## [0.1.4](https://github.com/loonghao/dcc-mcp-blender/compare/v0.1.3...v0.1.4) (2026-05-24)


### Features

* expand blender mcp skills ([f7c2f4e](https://github.com/loonghao/dcc-mcp-blender/commit/f7c2f4e20206f2ebf190eea2c052c0d61d01a357))

## [0.1.3](https://github.com/loonghao/dcc-mcp-blender/compare/v0.1.2...v0.1.3) (2026-05-18)


### Features

* add _env module and dispatcher module for Blender MCP server ([b1f7597](https://github.com/loonghao/dcc-mcp-blender/commit/b1f7597508d609a0d5d713c61c23d2633f27628a))
* add blender-dev-build-link-core-win (align with Maya) ([05a3dcb](https://github.com/loonghao/dcc-mcp-blender/commit/05a3dcb0643dcf2644d5a977128a602b0ddc6d53))
* add justfile and tools for local Blender development ([5bac68d](https://github.com/loonghao/dcc-mcp-blender/commit/5bac68dac54b04680797a3d02b337b2f38839cac))
* align addon packaging with core 0.17.5 ([091a19c](https://github.com/loonghao/dcc-mcp-blender/commit/091a19c8ef9eb2f867769bf2920c68b8293eb189))
* align with dcc-mcp-core 0.17.2 API (add diagnostics/execution options) ([d1d7a49](https://github.com/loonghao/dcc-mcp-blender/commit/d1d7a49904e2d62a99d7540c8db8d4f8ef6c6a23))
* expand Blender host skills and release flow ([ccc6b77](https://github.com/loonghao/dcc-mcp-blender/commit/ccc6b7785e91929e7ce9f22eaf75b7a9d3385992))


### Bug Fixes

* add blender callable dispatcher ([ce5fe91](https://github.com/loonghao/dcc-mcp-blender/commit/ce5fe916a46bbd28c7eaf9284fa911ab93263ec1))
* export obj without ui context ([30c478c](https://github.com/loonghao/dcc-mcp-blender/commit/30c478c1188ef3b7a4fb4cd701307b6e452b7673))
* migrate blender skills metadata schema ([4d41b71](https://github.com/loonghao/dcc-mcp-blender/commit/4d41b716a0106c2efc39c4fbdb2cb5d94f99ff84))
* resolve active object in headless blender ([ba644e6](https://github.com/loonghao/dcc-mcp-blender/commit/ba644e6e2d4a43bb5f00002d039b0b57ed06ba30))


### Code Refactoring

* inherit DccServerBase from dcc-mcp-core, upgrade to &gt;=0.12.29 ([#10](https://github.com/loonghao/dcc-mcp-blender/issues/10)) ([4a453c5](https://github.com/loonghao/dcc-mcp-blender/commit/4a453c5929c89a1dfe2fcf7d57ef2c1f75b4f81c))

## [0.1.2](https://github.com/loonghao/dcc-mcp-blender/compare/dcc-mcp-blender-v0.1.1...dcc-mcp-blender-v0.1.2) (2026-04-15)


### Features

* upgrade to dcc-mcp-core v0.12.24 — progressive loading, multi-instance gateway, more Blender E2E versions ([#6](https://github.com/loonghao/dcc-mcp-blender/issues/6)) ([68dda54](https://github.com/loonghao/dcc-mcp-blender/commit/68dda54941e1bd388171e80bf263dd41051f6536))


### Bug Fixes

* **ci:** add E2E tests and fix Windows/macOS CI issues ([#3](https://github.com/loonghao/dcc-mcp-blender/issues/3)) ([1326b9b](https://github.com/loonghao/dcc-mcp-blender/commit/1326b9b79d3200a82f3483b175b549b1f57415ff))
* **ci:** add shell: bash for release zip step + add Python 3.7 support ([#4](https://github.com/loonghao/dcc-mcp-blender/issues/4)) ([1ec1377](https://github.com/loonghao/dcc-mcp-blender/commit/1ec137733619fe4260fb1044ffc13377fe624151))
* **ci:** resolve all CI failures on main ([ec69825](https://github.com/loonghao/dcc-mcp-blender/commit/ec69825117bee7249002c25de43add664aba7b50))

## [0.1.1](https://github.com/loonghao/dcc-mcp-blender/compare/dcc-mcp-blender-v0.1.0...dcc-mcp-blender-v0.1.1) (2026-04-12)


### Features

* initial project setup for dcc-mcp-blender ([7c68634](https://github.com/loonghao/dcc-mcp-blender/commit/7c686340d2de7878800b2c9d9ac8ba0f699d6e96))


### Tests

* add comprehensive unit tests and E2E test suite (133 tests) ([#1](https://github.com/loonghao/dcc-mcp-blender/issues/1)) ([298bd7b](https://github.com/loonghao/dcc-mcp-blender/commit/298bd7bb0af4098e3d2b4a51a51df5207c2e433a))
