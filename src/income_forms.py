"""Reading the income forms (W-2, 1099s, SSA-1099) out of what Extraction produced, and spotting the
in-scope forms whose amounts were not read (issue #27). Kept apart from the agents so the draft form
and Computation can share it without one depending on the other. Plain functions over plain data:
no state, no tools, no arithmetic."""
import re

# line -> [(document kind, extracted field)]. Kinds are normalised (see document_kind). The field names
# are Computation's assumptions about Extraction's output; see docs/provenance.md.
DOC_LINES = {
    "line_1a": [("w2", "box_1")],
    "line_2a": [("1099int", "box_8")],
    "line_2b": [("1099int", "box_1")],
    "line_3a": [("1099div", "box_1b")],
    "line_3b": [("1099div", "box_1a")],
    "line_4a": [("1099r-ira", "box_1")],
    "line_4b": [("1099r-ira", "box_2a")],
    "line_5a": [("1099r-pension", "box_1")],
    "line_5b": [("1099r-pension", "box_2a")],
    "line_6a": [("ssa1099", "box_5")],
    "line_25a": [("w2", "box_2")],
    "line_25b": [("1099int", "box_4"), ("1099div", "box_4"), ("1099r-ira", "box_4"),
                 ("1099r-pension", "box_4"), ("ssa1099", "box_6")],
}

# In-scope forms Extraction does not read yet: normalised kind -> (name, the Intake answer that says
# the taxpayer has it).
UNREAD_FORMS = {
    "ssa1099": ("SSA-1099", "has_ssa_1099"),
    "1099int": ("1099-INT", "has_1099_int"),
    "1099div": ("1099-DIV", "has_1099_div"),
}


# Amounts the taxpayer types in for the forms Extraction does not read (issue #27, step 2): fact name ->
# (normalised kind, line). Proposed names, to agree in docs/answer-names.md; Intake does not ask them yet.
TYPED_AMOUNTS = {
    "ssa1099_benefits": ("ssa1099", "line_6a"),
    "ssa1099_withheld": ("ssa1099", "line_25b"),
    "int1099_tax_exempt": ("1099int", "line_2a"),
    "int1099_taxable": ("1099int", "line_2b"),
    "int1099_withheld": ("1099int", "line_25b"),
    "div1099_qualified": ("1099div", "line_3a"),
    "div1099_ordinary": ("1099div", "line_3b"),
    "div1099_withheld": ("1099div", "line_25b"),
}


def fact_value(facts, name, default=None):
    item = facts.get(name)
    return item.get("value", default) if isinstance(item, dict) else default


def record_field(record, field):
    item = (record.get("fields") or {}).get(field)
    return item.get("value") if isinstance(item, dict) else item


def document_kind(record):
    """Normalised document kind. A 1099-R is split into IRA vs pension by its IRA/SEP/SIMPLE
    checkbox (extracted field `ira_sep_simple`)."""
    kind = "".join(c for c in str(record.get("kind", "")).lower() if c.isalnum())
    if kind == "1099r":
        return "1099r-ira" if record_field(record, "ira_sep_simple") else "1099r-pension"
    return kind


def as_number(item):
    value = item.get("value") if isinstance(item, dict) else item
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


TEXT_AMOUNT = re.compile(r"\s*\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*")


def text_amount(value):
    """A plain amount written as text ("20000.00", "$20,000.00", "1,234") as a number, else
    None. Strict on purpose: anything else (words, signs, ranges) is not read."""
    match = TEXT_AMOUNT.fullmatch(value) if isinstance(value, str) else None
    return float(match.group(1).replace(",", "") + (match.group(2) or "")) if match else None


def document_amounts(extracted, specs, read_text=False):
    """(label, value, doc_id) for each extracted document field named in `specs`. Text amounts
    are only read when `read_text` (a send-back from Review asked for it)."""
    found = []
    for doc_id, record in sorted(extracted.items()):
        for kind, field in specs:
            if document_kind(record) == kind:
                raw = record_field(record, field)
                value = as_number(raw)
                if value is None and read_text:
                    value = text_amount(raw)
                if value is not None:
                    found.append((f"{doc_id}.{field}", value, doc_id))
    return found


def typed_amounts(facts, line):
    """[(fact name, value)] of the amounts the taxpayer typed in for `line`, in TYPED_AMOUNTS order."""
    return [(name, as_number(facts.get(name))) for name, (_, target) in TYPED_AMOUNTS.items()
            if target == line and as_number(facts.get(name)) is not None]


def typed_for_kind(facts, kind):
    return any(as_number(facts.get(name)) is not None
               for name, (form, _) in TYPED_AMOUNTS.items() if form == kind)


def unread_forms(facts, extracted, read_text=False):
    """In-scope income forms the taxpayer has (one was uploaded, or Intake recorded "yes") whose
    amounts were not read. Returns [{"form": "SSA-1099", "lines": ["line_6a", "line_25b"]}]. A form
    from which any amount was read, from a document or typed in by the taxpayer, is not listed, so
    this stops flagging once Extraction or the taxpayer supplies the amounts."""
    found = []
    for kind, (name, answer) in UNREAD_FORMS.items():
        specs = [(k, field) for specs in DOC_LINES.values() for k, field in specs if k == kind]
        has = answered_yes(facts, answer) or any(document_kind(r) == kind for r in extracted.values())
        if has and not document_amounts(extracted, specs, read_text) and not typed_for_kind(facts, kind):
            found.append({"form": name,
                          "lines": [line for line, spec in DOC_LINES.items()
                                    if any(k == kind for k, _ in spec)]})
    return found


def answered_yes(facts, *names):
    return any(fact_value(facts, n) in (True, "yes") for n in names)


def missing_income_forms(facts, extracted):
    """The income forms the taxpayer says they have, or uploaded, for which no amount is held, as
    [{"form": "W-2", "lines": ["line_1a", "line_25a"]}]. The three forms Extraction does not read
    (see `unread_forms`), plus a W-2 or 1099-R the taxpayer declared but never uploaded. A typed-in
    amount or a text amount counts as held. Fixed names and lines only (never document text), so the
    list is safe to show the orchestrator and on the draft."""
    found = unread_forms(facts, extracted, read_text=True)
    if answered_yes(facts, "has_w2") and not document_amounts(extracted, [("w2", "box_1")], read_text=True):
        found.insert(0, {"form": "W-2", "lines": ["line_1a", "line_25a"]})
    if answered_yes(facts, "has_1099_r") and not any(document_kind(r).startswith("1099r") for r in extracted.values()):
        found.append({"form": "1099-R",
                      "lines": [line for line, spec in DOC_LINES.items() if any(k.startswith("1099r") for k, _ in spec)]})
    return found


def forms_without_amounts(facts, extracted):
    """Names of the forms in `missing_income_forms` (fixed names, safe to show the orchestrator)."""
    return [form["form"] for form in missing_income_forms(facts, extracted)]
