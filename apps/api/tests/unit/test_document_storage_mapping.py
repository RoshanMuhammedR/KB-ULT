"""Serialization of parsed `Document`s to and from the `documents` JSONB column.

This pair is load-bearing for a subtlety in the pipeline: a fresh ingestion chunks the
objects the handler just built, while a retry resuming at the chunking step reloads them
from Postgres. Both paths must hand the chunker the same type, or the resume path breaks in
a way no handler test would catch.
"""

import json
from unittest import TestCase

from langchain_core.documents import Document

from src.core.text import sanitize_json_for_storage
from src.infrastructure.repositories.mappers import documents_to_domain, documents_to_storage


class DocumentStorageMappingTest(TestCase):
    def test_round_trip_preserves_content_and_locator(self) -> None:
        documents = [
            Document(page_content="Page one.", metadata={"locator": {"type": "page", "value": 1}}),
            Document(page_content="0:42 onwards", metadata={"locator": {"type": "timestamp", "value": 42}}),
        ]

        self.assertEqual(documents_to_domain(documents_to_storage(documents)), documents)

    def test_stored_form_is_actually_json_serializable(self) -> None:
        # The reason serialization is explicit: `sanitize_json_for_storage` only strips NUL
        # bytes and returns anything it doesn't recognise by identity, so an un-dumped
        # Document sails through it and only fails later inside json.dumps at commit time.
        documents = [Document(page_content="Body.", metadata={"locator": None})]

        encoded = json.dumps(sanitize_json_for_storage(documents_to_storage(documents)))
        self.assertIn("Body.", encoded)

        # Sanitizing alone is not enough — this is the failure the dump step prevents.
        with self.assertRaises(TypeError):
            json.dumps(sanitize_json_for_storage(documents))

    def test_nul_bytes_are_stripped_before_storage(self) -> None:
        # PostgreSQL rejects NUL bytes inside JSONB strings, and PDF extractors emit them.
        stored = sanitize_json_for_storage(
            documents_to_storage([Document(page_content="Head\x00ing")])
        )

        self.assertEqual(documents_to_domain(stored)[0].page_content, "Heading")

    def test_missing_or_empty_column_decodes_to_no_documents(self) -> None:
        # What rows written before migration 0007 look like. The pipeline reads an empty
        # list as "re-extract" rather than indexing nothing.
        self.assertEqual(documents_to_domain(None), [])
        self.assertEqual(documents_to_domain([]), [])

    def test_malformed_rows_are_skipped_rather_than_crashing_ingestion(self) -> None:
        stored = [
            {"page_content": "Good.", "metadata": {"locator": {"type": "page", "value": 1}}},
            {"metadata": {"locator": None}},  # no page_content
            "not a mapping at all",
        ]

        documents = documents_to_domain(stored)

        self.assertEqual([document.page_content for document in documents], ["Good."])
