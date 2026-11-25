"""Config forms for the admin editor: every collector type's config model is
described field by field (name, type, required, help text)."""

import pytest

from blackkite.collectors import registry
from blackkite.collectors.forms import describe


def _walk(fields):
    for f in fields:
        yield f
        yield from _walk(f.get("fields", []))
        yield from _walk((f.get("items") or {}).get("fields", []))
        for variant in f.get("variants", []):
            yield from _walk(variant)


@pytest.mark.parametrize("ctype", sorted(registry.CONFIG_MODELS))
def test_every_field_has_name_type_required_and_help(ctype):
    form = registry.config_form(ctype)
    assert form["collector_type"] == ctype
    assert form["json_schema"]["type"] == "object"
    fields = list(_walk(form["fields"]))
    assert fields
    for f in fields:
        assert f["name"] and isinstance(f["required"], bool)
        assert f["type"] in (
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
            "enum",
        ), f
        assert len(f["help"]) > 5, f


def test_html_list_form_shape():
    fields = {f["name"]: f for f in registry.config_form("html_list")["fields"]}
    assert fields["list_url"] == {
        "name": "list_url",
        "required": True,
        "help": "Address of the listing page (page 1).",
        "type": "string",
    }
    assert fields["max_pages"]["default"] == 1 and fields["max_pages"]["maximum"] == 20
    sels = {f["name"]: f for f in fields["selectors"]["fields"]}
    assert sels["item"]["required"] and sels["title"]["required"]
    assert {f["name"] for f in sels["title"]["fields"]} == {"css", "attr"}


def test_config_forms_cover_every_registered_type():
    assert set(registry.config_forms()) == set(registry.CONFIG_MODELS)
    with pytest.raises(ValueError):
        registry.config_form("ftp")


def test_a_field_without_help_text_is_a_bug():
    from pydantic import BaseModel

    class Bad(BaseModel):
        url: str

    with pytest.raises(ValueError, match="no help text"):
        describe(Bad)
