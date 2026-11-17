"""Offline contracts for the 25-archetype curriculum coordinator."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

for _path in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from core_organs.harvest import curriculum as C
from core_organs.harvest import web_search_failover as W


class _CoverageRag:
    """Tiny fake that isolates coverage accounting from storage/network I/O."""
    class _Graph:
        def stats(self, app_key):
            return {"nodes": 1 if app_key == "notepad" else 0, "edges": 0, "observations": 0}

    class _Proc:
        def stats(self, app_key):
            return {"chunks": 2 if app_key == "docs_only" else 0, "procedures": 0}

    class _Recovery:
        def stats(self, _app_key):
            return {"playbooks": 0}

    class _Fast:
        def count(self, _app_key):
            return 0

    class _Lex:
        def n_commands(self, _app_key):
            return 0

    graph, proc, rec, fast, lex = _Graph(), _Proc(), _Recovery(), _Fast(), _Lex()


class _FeedProc:
    def __init__(self):
        self.documents = []
        self.procedures = []

    def ingest_document(self, *args, **kwargs):
        self.documents.append((args, kwargs))
        return SimpleNamespace(inserted=1, updated=0)

    def ingest_procedure(self, *args, **kwargs):
        self.procedures.append((args, kwargs))
        return SimpleNamespace(inserted=1, updated=0)


class _FeedRag:
    def __init__(self):
        self.proc = _FeedProc()


class _DigestRag:
    def __init__(self):
        self.proc = _FeedProc()


def main() -> int:
    rows = C.plan({"notepad", "calculator", "visual_studio_code", "blender", "google_chrome"})
    ids = [row["archetype"] for row in rows]
    by_id = {row["archetype"]: row for row in rows}
    evidence = C.evidence_bearing_apps({"notepad", "docs_only", "registry_only"}, _CoverageRag())
    named_rows = {row["target"]: row for row in C.rows_for_apps(
        ["Discord", "File Explorer", "Visual Studio Code", "WhatsApp"], known_apps=()
    )}
    feed_rag = _FeedRag()
    fed = W.feed_rag(feed_rag, "slack", "Slack", [], "https://docs.slack.com/help", "Slack Help", "Use channels to organize team conversations.")
    digest_rag = _DigestRag()
    digested = C.ingest_official_digest(digest_rag, {"target": "Premiere Pro", "app_key": "premiere_pro"})
    digest_args, digest_kwargs = digest_rag.proc.documents[0]
    checks = {
        "one_target_for_each_universal_pattern": len(rows) == 25 and len(set(ids)) == 25,
        "known_apps_count_only_for_their_own_pattern": by_id["text_editor"]["represented_by"] == ["notepad"] and by_id["calculator"]["represented_by"] == ["calculator"],
        "unrepresented_patterns_are_prioritised": by_id["cad_engineering"]["priority"] > by_id["text_editor"]["priority"],
        "plan_never_marks_web_knowledge_executable": all("two distinct runs" in row["promotion_rule"] for row in rows),
        "official_seed_urls_are_data_not_action_rules": by_id["terminal"]["source_urls"] == ["https://learn.microsoft.com/en-us/windows/terminal/install"] and by_id["terminal"]["acquisition_order"][0] == "curriculum_seed" and C.OFFICIAL_SOURCE_SEEDS["Logic Pro"] == ["https://support.apple.com/guide/logicpro/welcome/mac"] and C.OFFICIAL_SOURCE_SEEDS["Zoom Chat"][0].startswith("https://support.zoom.com/"),
        "named_common_apps_keep_their_pattern_and_official_seed": named_rows["Discord"]["archetype"] == "chat_messenger" and named_rows["File Explorer"]["archetype"] == "file_manager" and named_rows["Visual Studio Code"]["archetype"] == "code_ide" and named_rows["WhatsApp"]["app_key"] == "whatsapp_desktop" and named_rows["WhatsApp"]["source_urls"][0].startswith("https://faq.whatsapp.com/"),
        "official_sources_have_stronger_teaching_trust": W.source_trust("https://learn.microsoft.com/en-us/windows/") == "official_doc" and W.source_trust("https://www.wikihow.com/Use-Notepad") == "web",
        "source_admission_rejects_unreviewed_search_results": W.teaching_source_allowed("https://learn.microsoft.com/en-us/windows/") and W.teaching_source_allowed("https://www.wikihow.com/Use-Notepad") and not W.teaching_source_allowed("https://justcreative.com/download-adobe-illustrator/"),
        "recovery_material_cannot_seed_a_generic_procedure": W.is_recovery_reference("Fix File Explorer if it won't open", "Resetting Windows may help") and not W.is_recovery_reference("VS Code editor overview", "Open a folder and edit code."),
        "official_reference_without_numbered_steps_is_teaching_evidence": W.document_about_app("<title>Slack help centre</title><h1>Use Slack channels</h1><p>Learn about Slack.</p>", "Slack")
        and "Use Slack channels" in W.document_text("<nav>skip</nav><h1>Use Slack channels</h1><p>Learn about Slack.</p>"),
        "registry_only_apps_do_not_claim_curriculum_coverage": evidence == {"notepad", "docs_only"},
        "reference_document_feeds_tutor_not_executor": fed["documents"] == 1 and fed["procedures"] == 0 and len(feed_rag.proc.documents) == 1 and not feed_rag.proc.procedures,
        "official_fetch_block_has_a_non_executable_digest": C.OFFICIAL_SOURCE_DIGESTS["Illustrator"]["url"].startswith("https://helpx.adobe.com/") and "scanner" in C.OFFICIAL_SOURCE_DIGESTS["Illustrator"]["text"].lower(),
        "source_digest_cannot_build_a_procedure": digested == 1 and len(digest_rag.proc.documents) == 1 and not digest_rag.proc.procedures and digest_args[0] == "premiere_pro" and digest_kwargs["kind"] == "source_digest" and digest_kwargs["trust"] == "official_doc" and digest_kwargs["build_procedures"] is False,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
