# Project Constraints: Public Package Repositories Only

> [!IMPORTANT]
> **Airlock & Artifact Registry Bypassed**  
> Do **NOT** use `google-artifactregistry-auth` or Airlock for this project.
> We must **only** use the public PyPI package repositories.

## How to execute `uv` commands in this workspace

For the test harness, we have defined the public PyPI registry directly inside `tools/test_harness/pyproject.toml` under `[tool.uv]`. This local configuration automatically overrides the system-wide Airlock staging registry.

Therefore, when working inside the `tools/test_harness/` directory, you can run standard, clean `uv` commands without any environment variable prefix or `--no-config` flag:

### Installation / Syncing Dependencies
```bash
uv sync
```

### Running Scripts or Modules
```bash
uv run src/run_concurrent_benchmark.py --manifest ... --cdp ...
```

### Adding New Packages
```bash
uv add <package>
```

## Diagram Conventions

> [!IMPORTANT]
> **Use Graphviz (DOT), Never Mermaid**  
> For all architecture, sequence, and flow diagrams in this workspace, always use **Graphviz (DOT)** syntax. Do **NOT** use Mermaid diagrams.

### Diagram Compilation & Embed Workflow
To avoid local macOS compilation blocks (e.g. Santa blocking `fc-cache` or `gdk-pixbuf` binaries), use this pipeline to render DOT diagrams to PNGs via your Cloudtop VM:

1. **Save DOT Source**: Save your diagram code to a local `.dot` file in the same directory as the target document (e.g., `tools/test_harness/architecture.dot`).
2. **Compile Remotely**: Stream the DOT input file to the remote `dot` compiler on your Cloudtop VM over SSH:
   ```bash
   ssh cloudtop-thomas "dot -Tpng" < path/to/diagram.dot > path/to/diagram.png
   ```
3. **Embed & Link**: In your Markdown document, embed the rendered PNG relative path and provide a hyperlink back to the DOT source file:
   ```markdown
   ![Diagram Title](diagram.png)
   *(View source in [Graphviz DOT Source](diagram.dot))*
   ```

