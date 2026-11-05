"""Unit tests for knowledge base sync, identity, and lifecycle operations.

Uses isolated temporary directories and mock embeddings to ensure:
1. Zero Cohere API usage / credits consumed.
2. Complete isolation from real project documents and database.
3. Strict verification of conditions a through h.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import chromadb

import rag


class MockEmbedResponse:
    def __init__(self, vectors: list[list[float]]):
        self.embeddings = MagicMock()
        self.embeddings.float_ = vectors


class MockCohereClient:
    """Mock Cohere client that produces deterministic 64-dimensional embeddings."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def embed(
        self,
        model: str,
        texts: list[str],
        input_type: str,
        embedding_types: list[str] | None = None,
    ) -> MockEmbedResponse:
        if self.should_fail:
            raise RuntimeError("Simulated Cohere network error")

        vectors: list[list[float]] = []
        for text in texts:
            # Deterministic pseudo-embedding from text hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(b / 255.0) for b in h[:32]]  # 32 floats
            # Pad to 64 floats
            vec.extend([(b / 255.0) * 0.5 for b in h[32:64]] if len(h) >= 64 else [0.0] * (64 - len(vec)))
            vectors.append(vec[:64])

        return MockEmbedResponse(vectors)


class TestSyncAndLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mce_test_")
        self.docs_path = Path(self.temp_dir) / "documents"
        self.db_path = Path(self.temp_dir) / "chroma_db"
        self.docs_path.mkdir(parents=True, exist_ok=True)
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.chroma_client.create_collection(
            name="test_collection", metadata={"hnsw:space": "cosine"}
        )
        self.mock_client = MockCohereClient(should_fail=False)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_new_document_retrievable(self):
        """a. A new document becomes retrievable."""
        doc_file = self.docs_path / "overview.txt"
        doc_file.write_text("Malnad College of Engineering was established in 1960 in Hassan, Karnataka.")

        report = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(report["added"]), 1)
        self.assertEqual(report["added"][0]["source"], "overview.txt")

        hits = rag.retrieve(self.mock_client, self.collection, "When was MCE established?", top_k=5)
        self.assertTrue(len(hits) > 0)
        self.assertEqual(hits[0]["source"], "overview.txt")
        self.assertIn("1960", hits[0]["text"])

    def test_b_rerunning_sync_changes_nothing(self):
        """b. Re-running sync changes nothing."""
        doc_file = self.docs_path / "overview.txt"
        doc_file.write_text("Civil Engineering department was established in 1960.")

        rep1 = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(rep1["added"]), 1)

        rep2 = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(rep2["added"]), 0)
        self.assertEqual(len(rep2["updated"]), 0)
        self.assertEqual(len(rep2["removed"]), 0)
        self.assertEqual(rep2["unchanged"], ["overview.txt"])

    def test_c_editing_document_removes_old_chunks(self):
        """c. Editing a document (same name) removes old chunks; old text is gone, new is retrievable."""
        doc_file = self.docs_path / "fees.txt"
        doc_file.write_text("Old fee structure is 50000 INR per year.")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)

        # Update file with new text
        doc_file.write_text("New revised fee structure is 85000 INR per year.")
        rep = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(rep["updated"]), 1)

        # Inspect all documents in collection
        all_docs = self.collection.get(include=["documents"])["documents"]
        combined_text = " ".join(all_docs)
        self.assertNotIn("50000", combined_text, "Old text should have been removed from collection")
        self.assertIn("85000", combined_text, "New text should be present in collection")

    def test_d_replacing_document_with_different_name(self):
        """d. Replacing a document with a differently named file removes the old one completely."""
        doc1 = self.docs_path / "old_guide.txt"
        doc1.write_text("Old placement guide rules 2023.")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)

        new_data = b"New placement brochure 2026."
        rag.replace_document_with(
            client=self.mock_client,
            collection=self.collection,
            old_source="old_guide.txt",
            new_filename="new_guide.txt",
            data=new_data,
            folder=self.docs_path,
        )

        sources = rag.list_sources(self.collection)
        self.assertNotIn("old_guide.txt", sources)
        self.assertIn("new_guide.txt", sources)
        self.assertFalse((self.docs_path / "old_guide.txt").exists())
        self.assertTrue((self.docs_path / "_deleted" / "old_guide.txt").exists())

    def test_e_deleting_file_and_syncing_removes_chunks(self):
        """e. Deleting a file from the folder and syncing removes its chunks."""
        doc1 = self.docs_path / "hostel.txt"
        doc1.write_text("Hostel facilities include mess and wifi.")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(self.collection.count(), 1)

        doc1.unlink()
        rep = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(rep["removed"]), 1)
        self.assertEqual(rep["removed"][0]["source"], "hostel.txt")
        self.assertEqual(self.collection.count(), 0)

    def test_f_renaming_file_leaves_no_duplicates(self):
        """f. Renaming a file leaves no duplicates."""
        content = "MCE has state of the art sports complex and gymnasium."
        f1 = self.docs_path / "sports_old.txt"
        f1.write_text(content)
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(self.collection.count(), 1)

        # Rename on disk
        f2 = self.docs_path / "sports_new.txt"
        f1.rename(f2)

        rep = rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(len(rep["renamed"]), 1)
        self.assertEqual(rep["renamed"][0]["old_source"], "sports_old.txt")
        self.assertEqual(rep["renamed"][0]["new_source"], "sports_new.txt")

        # Must leave no duplicates: collection count should still be exactly 1
        self.assertEqual(self.collection.count(), 1)
        sources = rag.list_sources(self.collection)
        self.assertNotIn("sports_old.txt", sources)
        self.assertIn("sports_new.txt", sources)

    def test_g_failed_embedding_preserves_old_version(self):
        """g. A failed embedding during an update does NOT delete the old version."""
        f = self.docs_path / "policy.txt"
        f.write_text("Original safe policy text 2024.")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        self.assertEqual(self.collection.count(), 1)

        # Now edit file
        f.write_text("Corrupted draft policy 2026.")

        # Sync using a failing client
        failing_client = MockCohereClient(should_fail=True)
        rep = rag.sync_documents(failing_client, self.collection, folder=self.docs_path)

        self.assertEqual(len(rep["failed"]), 1)
        self.assertEqual(rep["failed"][0]["source"], "policy.txt")

        # Database must still contain the original safe version
        all_docs = self.collection.get(include=["documents"])["documents"]
        self.assertEqual(len(all_docs), 1)
        self.assertIn("Original safe policy text", all_docs[0])

    def test_h_no_duplicate_chunk_ids_ever_exist(self):
        """h. No duplicate chunk IDs ever exist across adds, updates and renames."""
        # Add 3 multi-page documents
        for i in range(3):
            p = self.docs_path / f"multi_{i}.txt"
            p.write_text(f"Document {i} line 1\nDocument {i} line 2\nDocument {i} line 3")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)

        ids1 = self.collection.get(include=[])["ids"]
        self.assertEqual(len(ids1), len(set(ids1)), "Duplicate IDs found after initial add")

        # Re-index same folder (idempotence)
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        ids2 = self.collection.get(include=[])["ids"]
        self.assertEqual(len(ids2), len(set(ids2)), "Duplicate IDs found after rerun")

        # Edit one document
        (self.docs_path / "multi_1.txt").write_text("Modified text for document 1.")
        rag.sync_documents(self.mock_client, self.collection, folder=self.docs_path)
        ids3 = self.collection.get(include=[])["ids"]
        self.assertEqual(len(ids3), len(set(ids3)), "Duplicate IDs found after edit")


if __name__ == "__main__":
    unittest.main()
