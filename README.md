# knowledge-capture (`kcap`)

Crawl a documentation website, auto-detect its layout, and emit clean Markdown
optimized for AI ingestion.

Given a single seed URL — for example
`https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html` — `kcap`:

1. Detects the doc-site pattern (built-in profiles for AWS docs, MkDocs,
   Docusaurus, Sphinx/Read the Docs, GitBook; heuristic + optional LLM fallback
   otherwise).
2. Discovers all in-scope pages (sitemap.xml when available, BFS otherwise).
3. Fetches them concurrently (HTTP first, Playwright fallback when JS is
   needed), respecting `robots.txt` and a per-host rate limit.
4. Extracts the main content, strips chrome (nav/footer/feedback widgets),
   converts to Markdown with code-fence language detection and table
   preservation.
5. Writes per-page `.md` files, a single concatenated `bundle.md`, an
   `llms.txt` index, an `index.md` table of contents, and a machine-readable
   `manifest.json`.

## Installation

Requires Python 3.11+.

### Linux/macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,browser,llm]"
playwright install chromium
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,browser,llm]"
playwright install chromium
```

## Usage

```bash
kcap crawl https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html -o ./out

kcap inspect https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html
```

### `kcap crawl` flags

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `-o, --output` | `./out` | Output directory |
| `--scope` | `prefix` | `prefix`, `domain`, or `custom` |
| `--include REGEX` | (none) | URL must match (repeatable) |
| `--exclude REGEX` | (none) | Drop URLs matching (repeatable) |
| `--fetcher` | `auto` | `auto` / `http` / `browser` |
| `--max-pages` | `1000` | Hard cap |
| `--max-depth` | `10` | BFS depth cap |
| `-c, --concurrency` | `8` | Parallel workers |
| `--rate` | `4.0` | Per-host requests/sec |
| `--use-llm` | off | LLM fallback for tricky sites (needs `OPENAI_API_KEY`) |
| `--no-cache` | off | Bypass the on-disk HTTP cache |
| `--obey-robots / --ignore-robots` | obey | Toggle `robots.txt` |
| `-v, -vv` | warning | Logging verbosity |

## Output structure

```
out/
├── index.md
├── bundle.md
├── llms.txt
├── manifest.json
└── docs.aws.amazon.com/
    └── AWSEC2/latest/UserGuide/
        ├── concepts.md
        └── Instances.md
```

Each per-page Markdown file starts with a YAML front matter block:

```yaml
---
title: What is Amazon EC2?
source_url: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html
breadcrumbs: [AWS, EC2, User Guide, Concepts]
site: docs.aws.amazon.com
captured_at: '2026-04-26T16:43:00+00:00'
content_hash: 9c2e...
fetcher: http
---
```

## Architecture

```
seed URL
  -> robots.txt check
  -> SiteProfile detection (known profiles -> sitemap -> heuristic -> [LLM])
  -> URL discovery (sitemap or nav crawl)
  -> HybridFetcher (httpx -> Playwright fallback)
  -> extractor (selectors + trafilatura fallback)
  -> converter (markdownify + code-fence langs)
  -> postprocess (frontmatter, link rewriting, dedupe, heading normalization)
  -> writer (per-page md, bundle.md, llms.txt, manifest.json, index.md)
```

See [`.cursor/plans/`](.cursor/plans/) for the full implementation plan.

## Development

```bash
.venv/bin/pytest

.venv/bin/ruff check src tests
.venv/bin/ruff format src tests

.venv/bin/mypy src
```

Tests use offline HTML fixtures under `tests/fixtures/` and run without network access.

## License

MIT.
