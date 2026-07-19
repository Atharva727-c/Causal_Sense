# 04 — EDA Pipeline

**Path:** `backend_fastapi/app/services/eda_pipeline/` · **LLM:** EPAM DIAL (Azure-OpenAI proxy)
· **Agent framework:** LangGraph ReAct · **Vector store:** Chroma + BM25 (hybrid)

The EDA pipeline turns an uploaded dataset into a narrated exploratory analysis, then answers
follow-up questions against an accumulating knowledge base. It is **fully offline-capable** —
with no `DIAL_API_KEY` it runs in a deterministic mock mode (mock narration + hashed embeddings).

**Public API** (`eda_pipeline/__init__.py`): `run_initial_eda(session_id, dataset_path, target?,
time_col?)` and `answer_followup(session_id, question)`, both in `pipeline.py`. The router
`app/routers/eda_pipeline.py` calls these in a threadpool (they are blocking).

## Turn 1 — `run_initial_eda`

```
dataset ─► explore_dataset.py (subprocess) ─► executed .ipynb + plots + profile.json
        └► parse_notebook ─► ParsedCell[] (text + base64 PNGs)
        └► build_llm_content ─► multimodal content (text + image blocks, labelled "Cell N")
        └► dial.chat_json(TURN1_SYSTEM, content)  ── vision LLM ──► {facts, detailed,
                                                                     user_response, followups}
        ├► FactsFile.initialize(facts)        ── persist concise facts.md (always in context)
        ├► _index_detailed(detailed)          ── chunk → embed → hybrid vector store
        └► attach_plot_images                 ── resolve [[PLOT:cell]] markers → data-URI PNGs
   returns {ok, response, images, followups, artifacts, mock}
```

Step by step:

1. **Workspace** (`workspace.py`) — `Workspace.for_session(session_id)` namespaces everything
   under `eda_workspace_dir/<safe_session_id>/`: `run/`, `facts.md`, `detailed.tmp.md`,
   `chroma/`, `bm25.json`.
2. **`notebook.run_explorer`** — registers a Jupyter kernel and runs the repo
   `tools/explore_dataset.py` as a **subprocess** with `--execute-notebook` (a 6-step profiling
   checklist), producing an executed `data_exploration.ipynb`, plots, and `profile.json`.
   900-second timeout.
3. **`notebook.parse_notebook`** — parses the notebook into `ParsedCell` objects (index, type,
   source, text output, base64 PNG images, error flag).
4. **`notebook.build_llm_content`** — builds an OpenAI-style multimodal `content` list
   (interleaved text + `image_url` blocks, each labelled "Cell N") and appends the turn-1 output
   contract.
5. **`dial.chat_json(TURN1_SYSTEM, content)`** — one vision-LLM call forced to return a JSON
   object. The model interprets every cell/plot and completes the analysis checklist, returning
   `{facts, detailed, user_response, followups}` (contract in `prompts.py`).
6. **`FactsFile.initialize(facts)`** — persists the concise, always-in-context `facts.md`
   (soft 12k-char budget; oldest sections trimmed at section boundaries).
7. **`_index_detailed`** — writes the transient `detailed.tmp.md`, chunks it, adds the chunks to
   the session vector store, then deletes the tmp file.
8. **`attach_plot_images`** — resolves `[[PLOT:<cell>]]` markers the LLM placed in the user
   response into inline base64 PNG data-URIs (markers for image-less/hallucinated cells are
   silently dropped).

Returns `{ok, session_id, response, images, followups, artifacts{notebook, run_dir, n_cells,
n_images, n_chunks, facts_path}, mock}`.

## Turn N — `answer_followup`

```
question ─► agent.run_react (LangGraph create_react_agent, DIAL chat model)
                │  tools: retrieve_context(query), fetch_cell(cell_index)
                │  facts.md injected via REACT_SYSTEM
                ▼
            answer text + <<FOLLOWUPS>>…<<END>> block
        ├► FactsFile.append_turn        ── accumulate a concise fact
        ├► _index_detailed(Q&A)         ── index the exchange as new chunks (knowledge compounds)
        └► attach_plot_images           ── resolve plot markers
   returns {ok, response, images, followups, mock}
```

1. Requires an existing session (facts file present). Loads the vector store + facts.
2. **`agent.run_react`** builds a LangGraph `create_react_agent` bound to the DIAL chat model
   (`dial.get_langchain_chat`), with two tools and the facts injected via `REACT_SYSTEM`. The
   recursion limit derives from `eda_react_max_iterations`.
3. `strip_followups` extracts the trailing `<<FOLLOWUPS>>…<<END>>` block.
4. **Knowledge accumulation** — appends a concise fact and indexes the Q&A as new chunks, so
   knowledge compounds across turns.
5. Resolves plot markers and returns.

## Supporting modules

| Module | Responsibility |
|---|---|
| **`dial.py`** | DIAL clients. `available()` = key present. `chat_json` (raw `openai.AzureOpenAI`, multimodal, reasoning-model-safe: uses `max_completion_tokens`, omits temperature; lenient JSON parsing). `get_langchain_chat` (`langchain_openai.AzureChatOpenAI` for the ReAct agent). **Full mock mode** when no key. |
| **`embeddings.py`** | `Embedder` protocol with two backends: `DialEmbedder` (real Azure `text-embedding-3-large`) and `HashEmbedder` (deterministic offline hashed bag-of-words, dim 384). `get_embedder()` auto-selects by key presence. `ChromaEmbeddingFunction` adapts to Chroma. |
| **`vectorstore.py`** | `HybridVectorStore` per session. **Dense** = Chroma (`PersistentClient`, cosine); **sparse** = persisted BM25 (`rank_bm25`, corpus in `bm25.json`). Results fused via **Reciprocal Rank Fusion** (k=60). Metadata (esp. `cell_index`, `section`) enables filtering and cell-jumping. |
| **`chunking.py`** | Parses the LLM's marker-delimited detailed writeup (`[[CELL=n \| SECTION=… \| KIND=…]]`) into metadata-tagged, size-bounded, overlapping chunks (paragraph-aware split; deterministic md5-based ids). |
| **`facts.py`** | `FactsFile` — the concise Markdown knowledge base: `initialize`, `append_turn`, `read`, with a 12k-char trim that keeps the recent tail at section boundaries. |
| **`notebook.py`** | Subprocess execution + notebook parsing + multimodal content building + `get_cell`/`render_cell` for the `fetch_cell` tool. `ParsedCell` model. |
| **`tools.py`** | `make_tools(ws, store)` builds two LangChain `StructuredTool`s for the ReAct agent: `retrieve_context(query)` (top-k hybrid chunks tagged with cell_index) and `fetch_cell(cell_index)` (exact code + output of one notebook cell). |
| **`prompts.py`** | `TURN1_SYSTEM` + `TURN1_OUTPUT_CONTRACT` (strict JSON contract) and `REACT_SYSTEM` (follow-up agent, `{facts}` injected, `<<FOLLOWUPS>>` output format). |
| **`workspace.py`** | `Workspace.for_session` and all sub-path properties; filesystem-safe session ids; Chroma collection naming. |

## `tools/explore_dataset.py`

A standalone profiling script run as a subprocess. Given a dataset path (and sample-row cap), it
builds and executes a Jupyter notebook that profiles the data — dtypes, distributions,
correlations, missingness — emitting plots (PNG) and a `profile.json`, plus the executed
`.ipynb` the pipeline parses. Keeping this out-of-process isolates heavy plotting/compute from
the async web server and gives every run an auditable notebook artifact.

## Design notes

- **The LLM never computes.** Numbers come from executed notebook cells; the vision model
  interprets cells and plots and narrates. This is why the pipeline can't fabricate statistics.
- **Knowledge compounds.** `facts.md` is a small always-in-context summary; the vector store
  holds the long tail. Each follow-up both consumes and extends this store.
- **Hybrid retrieval.** Dense (semantic) + sparse (lexical) fused with RRF handles both
  conceptual and exact-term queries (e.g. a specific column name).
- **Offline-first.** Missing DIAL key → mock narration + `HashEmbedder`; the full turn-1 and
  follow-up flows still run.
