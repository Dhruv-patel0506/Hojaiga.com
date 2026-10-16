"""rag.adapters -- thin, defensive bridges from the project's existing stores into the RAG. Each takes the live objects/rows the existing module already produces; none imports a heavy
module at import time, and none raises into the caller (a missing source yields a zero count and a reason)."""
