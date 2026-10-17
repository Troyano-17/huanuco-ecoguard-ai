"""Offline tests for safeguards that could otherwise leak data or bypass review."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ecoguard_data import (CLASSES, assign_splits, build, reusable_license,
                           safe_path, taco_proposals, validate_reviews)


def reviewed(identifier="a", category=CLASSES[0], group=None):
    return dict(id=identifier, categoria=category, grupo_escena=group or identifier,
                estado="aprobada", revisor="Revisor", fecha_revision="2026-10-15",
                evidencia="Residuos visibles; contexto rural comprobado", autor="Autora",
                fuente="https://commons.wikimedia.org/wiki/File:Example.jpg",
                licencia="CC BY-SA 4.0", licencia_url="https://creativecommons.org/licenses/by-sa/4.0/",
                procedencia="sources/example.json", ubicacion="Perú")


class DataGates(unittest.TestCase):
    def test_taco_uses_scene_schema_and_keeps_rights_pending(self):
        data = dict(scene_categories=[dict(id=5, name="Vegetation"), dict(id=6, name="Water")],
                    scene_annotations=[dict(image_id=1, background_ids=[5]),
                                       dict(image_id=1, background_ids=[6]),
                                       dict(image_id=2, background_ids=[5])],
                    images=[dict(id=i, file_name=f"{i}.jpg", license=None) for i in (1, 2)])
        proposals = taco_proposals(data)
        self.assertEqual([r["categoria"] for r in proposals], [CLASSES[0], CLASSES[1]])
        self.assertTrue(all(r["estado"].startswith("pendiente") for r in proposals))
        self.assertTrue(all(r["licencia_original"] is None for r in proposals))

    def test_empty_dataset_cannot_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "No hay"):
                build(Path(tmp), Path(tmp) / "absent.json")

    def test_pending_review_blocks(self):
        row = reviewed()
        row["estado"] = "pendiente"
        with self.assertRaisesRegex(ValueError, "pendiente"):
            validate_reviews([row])

    def test_review_without_evidence_blocks(self):
        row = reviewed()
        row["evidencia"] = ""
        with self.assertRaises(ValueError):
            validate_reviews([row])

    def test_unknown_class_blocks(self):
        with self.assertRaises(ValueError):
            validate_reviews([reviewed(category="deforestacion")])

    def test_unknown_scene_blocks(self):
        row = reviewed()
        row["grupo_escena"] = ""
        with self.assertRaises(ValueError):
            validate_reviews([row])

    def test_license_allowlist(self):
        self.assertFalse(reusable_license("MIT", "https://opensource.org/license/mit"))
        self.assertFalse(reusable_license("CC BY 4.0", "https://example.com"))
        self.assertFalse(reusable_license("CC BY-NC-ND 4.0", ""))
        self.assertTrue(reusable_license("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"))

    def test_path_traversal_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_path(Path(tmp), "../../etc/passwd")

    def test_transitive_duplicate_groups_stay_together(self):
        rows = [reviewed(f"{c}-{i}", c) for c in CLASSES for i in range(50)]
        ids = [r["id"] for r in rows[:3]]
        pairs = [dict(a=ids[0], b=ids[1]), dict(a=ids[1], b=ids[2])]
        assignments = assign_splits(rows, pairs)
        self.assertEqual(len({assignments[i] for i in ids}), 1)
        self.assertEqual(assignments, assign_splits(rows, pairs))

    def test_scene_groups_across_categories_stay_together(self):
        rows = [reviewed(f"{c}-{i}", c, f"scene-{i}") for c in CLASSES for i in range(50)]
        assignments = assign_splits(rows, [])
        for i in range(50):
            self.assertEqual(len({assignments[f"{c}-{i}"] for c in CLASSES}), 1)

    def test_one_scene_per_class_is_insufficient(self):
        rows = [reviewed(f"{c}-{i}", c, c) for c in CLASSES for i in range(50)]
        with self.assertRaisesRegex(ValueError, "particiones"):
            assign_splits(rows, [])


if __name__ == "__main__":
    unittest.main()
