"""run_pipeline extraction layer: VLM first, OCR fallback, cache, diagnostics.

No real OCR or VLM: the VLM call and the heuristic path are replaced with
fakes that return the committed happy-path fixtures.
"""

import json
from pathlib import Path

import pytest

import apmatch.api.pipeline as pipeline
from apmatch.parse import vlm
from apmatch.parse.dispatch import DocumentKind
from apmatch.schema.serialize import document_from_dict

FIXTURES = Path(__file__).resolve().parents[1] / "integration" / "fixtures" / "happy_path"
_FILES = {
    DocumentKind.INVOICE: ("invoice", "invoice.json"),
    DocumentKind.PURCHASE_ORDER: ("po", "po.json"),
    DocumentKind.GRNI: ("grni", "grni.json"),
    DocumentKind.PAYMENT_ADVICE: ("pard", "pard.json"),
}


def _fixture_doc(kind):
    key, name = _FILES[DocumentKind(kind)]
    return document_from_dict(key, json.loads((FIXTURES / name).read_text()))


@pytest.fixture
def images(tmp_path):
    paths = {}
    for kind, (key, _) in _FILES.items():
        p = tmp_path / f"{key}.png"
        p.write_bytes(f"fake image {key}".encode())
        paths[kind] = p
    return paths


def _run(images, **kw):
    return pipeline.run_pipeline(
        images[DocumentKind.INVOICE], images[DocumentKind.PURCHASE_ORDER],
        images[DocumentKind.GRNI], images[DocumentKind.PAYMENT_ADVICE],
        router=object(), layout=object(), **kw,
    )


@pytest.fixture
def fake_vlm(monkeypatch):
    calls = []

    def fake(kind, path):
        calls.append(DocumentKind(kind))
        return vlm.VlmExtraction(
            document=_fixture_doc(kind), model="fake", model_digest="sha256:f",
            prompt_version=vlm.PROMPT_VERSION, format_used="schema", raw_output=None,
        )

    monkeypatch.setattr(vlm, "extract_vlm_detailed", fake)
    monkeypatch.setenv("EXTRACTION_BACKEND", "vlm")
    return calls


def test_vlm_path_auto_approves_happy_path(images, fake_vlm):
    _, _, decision, entry, extracted = _run(images)
    assert decision.route.value == "AUTO_APPROVE"
    assert entry.extraction_source == "vlm"
    meta = extracted["_extraction"]
    assert {k: v["source"] for k, v in meta.items()} == {
        "invoice": "vlm", "po": "vlm", "grni": "vlm", "pard": "vlm"}
    assert meta["invoice"]["vlm"]["model_digest"] == "sha256:f"
    assert extracted["invoice"]["invoice_number"] == "INV-2026-1123"


def test_vlm_failure_falls_back_per_document(images, monkeypatch):
    def fake(kind, path):
        doc = None if DocumentKind(kind) is DocumentKind.GRNI else _fixture_doc(kind)
        return vlm.VlmExtraction(document=doc, model="fake", model_digest=None,
                                 prompt_version="p", error=None if doc else "ReadTimeout: x")

    heuristic_calls = []

    def fake_heuristic(engines, kind, path, ocr_debug):
        heuristic_calls.append(DocumentKind(kind))
        return _fixture_doc(kind)

    monkeypatch.setattr(vlm, "extract_vlm_detailed", fake)
    monkeypatch.setattr(pipeline, "_heuristic", fake_heuristic)
    monkeypatch.setenv("EXTRACTION_BACKEND", "vlm")
    _, _, decision, entry, extracted = _run(images)
    assert heuristic_calls == [DocumentKind.GRNI]
    assert extracted["_extraction"]["grni"]["source"] == "heuristic"
    assert extracted["_extraction"]["grni"]["vlm"]["error"].startswith("ReadTimeout")
    assert entry.extraction_source == "mixed"
    assert decision.route.value == "AUTO_APPROVE"


def test_ocr_backend_never_calls_the_vlm(images, monkeypatch):
    monkeypatch.setattr(vlm, "extract_vlm_detailed", lambda *a: pytest.fail("VLM called"))
    monkeypatch.setattr(pipeline, "_heuristic", lambda e, kind, p, d: _fixture_doc(kind))
    monkeypatch.setenv("EXTRACTION_BACKEND", "ocr")
    _, _, _, entry, _ = _run(images)
    assert entry.extraction_source == "heuristic"


def test_extraction_cache_skips_second_vlm_call(images, fake_vlm, tmp_path):
    cache = tmp_path / "cache"
    first = _run(images, extraction_cache_dir=cache)
    assert len(fake_vlm) == 4
    second = _run(images, extraction_cache_dir=cache)
    assert len(fake_vlm) == 4  # all four came from the cache
    assert second[4]["_extraction"]["invoice"]["cache"] == "hit"
    assert second[2].route == first[2].route
    assert second[3].input_hash == first[3].input_hash


def test_derivation_applied_after_extraction(images, monkeypatch):
    def fake(kind, path):
        doc = _fixture_doc(kind)
        if DocumentKind(kind) is DocumentKind.INVOICE:
            from dataclasses import replace

            # The model read no subtotal and no line-1 amount: both are derivable.
            lines = (replace(doc.line_items[0], amount=None), *doc.line_items[1:])
            doc = replace(doc, subtotal=None, line_items=lines)
        return vlm.VlmExtraction(document=doc, model="f", model_digest=None, prompt_version="p")

    monkeypatch.setattr(vlm, "extract_vlm_detailed", fake)
    monkeypatch.setenv("EXTRACTION_BACKEND", "vlm")
    _, _, decision, _, extracted = _run(images)
    assert extracted["invoice"]["subtotal"] == "1000.00"
    assert extracted["invoice"]["line_items"][0]["amount"] == "450.00"
    assert decision.route.value == "AUTO_APPROVE"


def test_lazy_engines_build_once_on_first_use(monkeypatch):
    built = []

    class FakeRouter:
        def __init__(self):
            built.append("router")

        def recognize(self, path):
            return path

    import apmatch.api.pipeline as p

    proxy = p._Lazy(FakeRouter)
    assert built == []
    proxy.recognize("a")
    proxy.recognize("b")
    assert built == ["router"]


def test_cache_hit_reparses_raw_vlm_output_with_current_code(images, monkeypatch, tmp_path):
    raw = json.dumps({
        "invoice_number": "INV-2026-1123", "vendor_name": "Mekong Supplies Co., Ltd.",
        "invoice_date": "20/08/2026", "invoice_date_iso": "2026-08-20", "currency": "$",
        "po_number": "PO-2026-0451", "subtotal": "1,000.00", "tax_amount": "100.00", "total": "1,100.00",
        "line_items": [],
    })

    def fake(kind, path):
        doc = _fixture_doc(kind)
        return vlm.VlmExtraction(document=doc, model="f", model_digest=None, prompt_version="p",
                                 raw_output=raw if DocumentKind(kind) is DocumentKind.INVOICE else None)

    monkeypatch.setattr(vlm, "extract_vlm_detailed", fake)
    monkeypatch.setenv("EXTRACTION_BACKEND", "vlm")
    cache = tmp_path / "cache"
    _run(images, extraction_cache_dir=cache)
    _, _, _, _, extracted = _run(images, extraction_cache_dir=cache)
    # Second run re-parsed the raw reply: no line items in it, and the bare "$"
    # currency was resolved from the PO by reconcile.
    assert extracted["invoice"]["line_items"] == []
    assert extracted["invoice"]["currency"] == "USD"
    assert extracted["_extraction"]["invoice"]["vlm"]["date_candidates"] == ["2026-08-20"]


def test_old_cache_format_is_reparsed_from_info(images, monkeypatch, tmp_path):
    """A PROD-B3 cache file (raw reply only inside info.vlm) is still re-parsed."""
    import apmatch.api.pipeline as p

    monkeypatch.setenv("EXTRACTION_BACKEND", "vlm")
    monkeypatch.setattr(vlm, "extract_vlm_detailed", lambda *a: pytest.fail("VLM called"))
    cache = tmp_path / "cache"
    cache.mkdir()
    raw = json.dumps({"pard_number": "PARD-9", "invoice_number": "INV-2026-1123",
                      "amount": "1,100.00", "currency": "USD", "payment_date": "25/08/2026",
                      "payment_date_iso": "2026-08-25", "reference": None})
    path = images[DocumentKind.PAYMENT_ADVICE]
    f = p._cache_path(cache, DocumentKind.PAYMENT_ADVICE, path, "vlm")
    f.write_text(json.dumps({"document": {"pard_number": "STALE"},
                             "info": {"source": "vlm", "vlm": {"raw_output": raw}, "cache": "miss"}}))
    doc, info = p._recognize_and_parse(p._Engines(object(), object()), DocumentKind.PAYMENT_ADVICE,
                                       path, False, cache)
    assert doc.pard_number == "PARD-9" and info["cache"] == "hit"
