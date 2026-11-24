# Third-party notices

This project integrates GPT Researcher as a dependency; it does not claim authorship of its planning, retrieval, context compression, or report generation engine.

- Dependency: `gpt-researcher==0.14.7`
- Upstream: https://github.com/assafelovic/gpt-researcher
- The installed 0.14.7 distribution includes an Apache License 2.0 LICENSE file, reproduced in `docs/licenses/gpt-researcher-0.14.7.txt`. Its package metadata says MIT, which conflicts with the bundled license. This project documents that inconsistency and retains the actual license text rather than repeating the metadata claim.
- The application code is distributed under Apache License 2.0; dependencies retain their own licenses. The lockfile records dependency versions. No dependency binaries are included in the source archive.

The custom work here consists of recruitment task modeling, domain prompts, the FastAPI service, progress streaming, task and source persistence, the frontend, tests and evaluation tooling.
