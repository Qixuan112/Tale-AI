## Code Review: PR #81 — RAG Knowledge Base System

I've reviewed the full diff across 20+ files. Below are the findings ranked by severity.

---

### 🔴 Critical

**1. `rebuild_index()` silently loses all chunk metadata on rebuild**

`core/rag/knowledge_manager.py` calls `store.rebuild_from_chunks(embeddings)` but `store.clear()` already set `store._chunks = []`. `rebuild_from_chunks()` only restores the FAISS index — it never restores `self._chunks`. After rebuild, the store has vectors but zero chunk text/metadata. `_save()` writes an empty `mapping.json`, and all subsequent `search()` calls return empty results.

**Fix:** Either pass `all_chunk_records` to `rebuild_from_chunks`, or set `store._chunks = all_chunk_records` before calling it.

---

**2. RAG context message leaks on API failure**

`core/llm/chatllm.py`: The RAG system message is inserted into `self.messages` before the API call. If the API call fails (exception handler), only the user message is popped — the RAG message remains in `self.messages`. Since the cleanup code only runs on the success path, leaked RAG messages accumulate on each consecutive failure, consuming context space.

**Fix:** Reset `self._rag_injected` and remove the injected RAG message in the `except` block alongside the user message rollback.

---

**3. `upload_document()` crashes when embedder is None**

`core/rag/knowledge_manager.py`: `upload_document()` calls `self._embedder.embed(chunk_texts)` without checking if `self._embedder is None`. If `initialize()` failed to create the embedder (e.g., no API key), `self._embedder` is None and this raises `AttributeError`. `retrieve()` guards against this but `upload_document()` does not.

**Fix:** Add `if not self._embedder: raise ValueError("Embedder not initialized")` before using it.

---

**4. FAISS index dimension mismatch silently corrupts data on config reload**

`core/rag/vector_store.py`: `_load()` restores the persisted FAISS index without validating that its dimension matches the current `_dimension` parameter. If the embedding model changes between runs, `_load()` silently loads the old index. A subsequent `add()` or `search()` crashes with a FAISS C++ dimensionality assertion.

**Fix:** Validate `self._index.d` against `self._dimension` after `_load()`. Re-create the index on mismatch.

---

**5. RAG cleanup uses fragile content-substring matching**

`core/llm/chatllm.py`: After the API call, cleanup filters `self.messages` by checking if content contains `"## 知识库参考信息"`. If any user or assistant message happens to contain this substring, it is silently deleted from history. If the format string in `knowledge_manager.retrieve()` changes, the cleanup silently stops working.

**Fix:** Track the injected message by its index or a dedicated metadata key, not by content matching.

---

### 🟠 High

**6. FAISS native memory leak on repeated `initialize()` calls**

`core/rag/knowledge_manager.py`: `self._stores.clear()` drops all references to `FaissVectorStore` instances without cleanup. Each `FaissVectorStore` holds a `faiss.IndexFlatIP` which allocates native heap memory outside Python's GC. On each config reload, old native memory leaks.

**Fix:** Explicitly reset the FaissVectorStore instances before clearing.

---

**7. Bare `except Exception: pass` hides all RAG errors in chatllm.py**

`core/llm/chatllm.py`: RAG initialization failure and per-turn retrieval errors are silently caught with `except Exception: pass`. No log message is emitted. Makes production debugging impossible.

**Fix:** At minimum, `logger.warning(...)` in both exception handlers.

---

**8. `config_loader._data_dir` accessed via private attribute in webui**

`webui/app.py`: `Path(config_loader._data_dir)` accesses `ConfigLoader._data_dir`, a private attribute. If `_data_dir` is ever renamed or removed, the upload endpoint silently breaks.

**Fix:** Add a `@property` for `data_dir` to ConfigLoader.

---

**9. `KnowledgeBaseConfig.embed_model` parsed but never consumed**

`core/config/loader.py`: The per-knowledge-base `embed_model` field is parsed and stored, but `create_embedder()` only reads the top-level `openai_embedding_model`. Different models per KB silently get the same model.

**Fix:** Either remove `embed_model` from KnowledgeBaseConfig, or pass it through to the embedder.

---

### 🟡 Medium

**10. `datetime.now()` produces timezone-naive timestamps**

`core/rag/knowledge_manager.py`: `uploaded_at=datetime.now().isoformat()` stores a naive timestamp with no timezone offset. Comparison with timezone-aware datetimes raises `TypeError`.

**Fix:** Use `datetime.now(timezone.utc).isoformat()`.

---

**11. Duplicate dataclass definitions**

Both `core/config/model.py` and `core/rag/models.py` define `RAGConfig` and `KnowledgeBaseConfig`. Any future field addition to one will silently break the other.

**Fix:** Define once and import the other.

---

**12. `inject_order` config field parsed but never used**

`core/config/loader.py`: The `inject_order` field is parsed into `RAGConfig.inject_order`, but `chatllm.py` determines injection position dynamically by counting system messages. The config field has no effect.

**Fix:** Either use `inject_order` or remove it from the schema.

---

**13. `OpenAIEmbedder` dimension sniffed from model name**

`core/rag/embedder.py`: `self._dim = 512 if "small" in model else 1536` uses a string heuristic. Custom/aliased model names that don't contain "small" will silently get dimension 1536, causing FAISS dimension mismatch.

**Fix:** Make `dimension` a configurable parameter, or determine from API response metadata.

---

### Summary

| Severity | Count | Key Issues |
|----------|-------|------------|
| 🔴 Critical | 5 | Data loss on rebuild, context leak on failure, null pointer crash, dimension mismatch crash, fragile cleanup |
| 🟠 High | 4 | Memory leak, silent error swallowing, private API access, dead config |
| 🟡 Medium | 4 | Naive timestamps, duplicate models, dead config, fragile dimension heuristic |

The most impactful finding is **#1**: `rebuild_index()` appears to rebuild but actually discards all chunk metadata — every vector becomes unreachable after the operation. Combined with **#4** (dimension mismatch on reload), these make persistence across restarts unreliable.

I recommend addressing the critical and high findings before merging.
