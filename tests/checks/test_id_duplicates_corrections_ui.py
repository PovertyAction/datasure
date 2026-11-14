"""Tests for the correction controls on the ID duplicate cards, via AppTest."""

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

from datasure.processing.correction_log import Action


class FakeProcessor:
    """Records `apply_corrections` calls; fails them if `error` is set."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[dict] = []
        self.error = error

    def apply_corrections(self, alias, key_col, entries, source):
        if self.error:
            raise self.error
        self.calls.append(
            {"alias": alias, "key_col": key_col, "entries": entries, "source": source}
        )


def _cards_app(
    data, settings_file, processor, survey_data=None, resolved=0, all_data=None
):
    from datasure.checks.id_duplicates_ui import IdView, render_id_duplicates

    view = IdView(
        name="backcheck" if survey_data is not None else "survey",
        data=data,
        id_col="hhid",
        key_col="KEY",
        date_col=None,
        staff_col=None,
        team_col=None,
        display_cols_setting="id_table_display_cols",
        survey_data=survey_data,
        alias="bc_alias" if survey_data is not None else "survey_alias",
        processor=processor,
        resolved=resolved,
        all_data=all_data,
    )
    render_id_duplicates(view, settings_file)


@pytest.fixture
def survey():
    """ID A is on k1 and k2; k3 holds B."""
    return pl.DataFrame({"hhid": ["A", "A", "B"], "KEY": ["k1", "k2", "k3"]})


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "page_settings.json")


def _run(data, settings_file, processor, **kwargs):
    at = AppTest.from_function(
        _cards_app,
        args=(data, settings_file, processor),
        kwargs=kwargs,
        default_timeout=30,
    )
    at.run()
    assert not at.exception, at.exception
    return at


def _radio(at, key):
    return next(r for r in at.radio if r.label == f"Decision for KEY {key}")


def _new_id(at, key):
    return next(t for t in at.text_input if t.label == f"New hhid for KEY {key}")


def _save(at):
    return next(b for b in at.button if b.label == "Save")


def _note(at):
    return next(t for t in at.text_input if t.label == "Note")


def _reason(at):
    return next(s for s in at.selectbox if s.label == "Reason")


def _captions(at):
    return [c.value for c in at.caption]


def _fill_reason(at):
    _reason(at).select("Repeat visit")
    _note(at).input("Second visit after a failed first attempt")


def test_save_is_disabled_until_the_group_is_resolved(survey, settings_file):
    at = _run(survey, settings_file, FakeProcessor())

    assert [r.value for r in at.radio] == ["Keep", "Keep"]
    assert list(_radio(at, "k1").options) == ["Keep", "Modify ID", "Drop"]
    assert _save(at).disabled
    assert (
        ":material/info: 2 records still hold ID A. Keep at most one: modify "
        "or drop the others." in _captions(at)
    )

    _fill_reason(at)
    _radio(at, "k2").set_value("Drop").run()

    assert not _save(at).disabled


def test_save_logs_one_entry_per_changed_record(survey, settings_file):
    processor = FakeProcessor()
    at = _run(survey, settings_file, processor)
    _fill_reason(at)
    _radio(at, "k1").set_value("Modify ID").run()
    _new_id(at, "k1").input("D").run()
    _radio(at, "k2").set_value("Drop").run()

    _save(at).click().run()

    assert not at.exception
    (call,) = processor.calls
    assert call["alias"] == "survey_alias"
    assert call["key_col"] == "KEY"
    assert call["source"] == "duplicates"
    modify, drop = call["entries"]
    assert (modify.key_value, modify.action, modify.new_value) == (
        "k1",
        Action.MODIFY_VALUE,
        "D",
    )
    assert (drop.key_value, drop.action) == ("k2", Action.REMOVE_ROW)
    reason = "Repeat visit: Second visit after a failed first attempt"
    assert modify.reason == drop.reason == reason
    assert (
        "2 corrections logged this session. To undo one, remove it from the "
        "Correction Log." in _captions(at)
    )


def test_modify_id_to_an_existing_id_names_its_key(survey, settings_file):
    at = _run(survey, settings_file, FakeProcessor())
    _fill_reason(at)
    _radio(at, "k2").set_value("Modify ID").run()

    _new_id(at, "k2").input("B").run()

    assert _save(at).disabled
    assert ":material/info: ID B already belongs to KEY k3." in _captions(at)


def test_dropping_every_record_asks_for_confirmation(survey, settings_file):
    processor = FakeProcessor()
    at = _run(survey, settings_file, processor)
    _fill_reason(at)
    _radio(at, "k1").set_value("Drop").run()
    _radio(at, "k2").set_value("Drop").run()

    _save(at).click().run()

    # The dialog opens; nothing is saved until the user confirms.
    assert not at.exception
    assert processor.calls == []


def test_failed_save_shows_an_error_and_logs_nothing(survey, settings_file):
    processor = FakeProcessor(error=ValueError("disk full"))
    at = _run(survey, settings_file, processor)
    _fill_reason(at)
    _radio(at, "k2").set_value("Drop").run()

    _save(at).click().run()

    assert not at.exception
    assert [e.value for e in at.error] == [
        "The corrections for hhid A were not saved: disk full"
    ]
    assert not any("logged this session" in c for c in _captions(at))


def test_unmatched_backcheck_offers_modify_id_or_drop(settings_file):
    survey = pl.DataFrame({"hhid": ["A", "B"], "KEY": ["s1", "s2"]})
    backcheck = pl.DataFrame({"hhid": ["A", "Q"], "KEY": ["b1", "b2"]})
    processor = FakeProcessor()
    at = _run(backcheck, settings_file, processor, survey_data=survey)

    radio = _radio(at, "b2")
    assert list(radio.options) == ["Modify ID", "Drop"]
    _fill_reason(at)
    _new_id(at, "b2").input("Z").run()
    assert ":material/info: ID Z is not in the survey data." in _captions(at)

    _new_id(at, "b2").input("B").run()
    _save(at).click().run()

    (call,) = processor.calls
    assert call["alias"] == "bc_alias"
    (entry,) = call["entries"]
    assert (entry.key_value, entry.column, entry.current_value, entry.new_value) == (
        "b2",
        "hhid",
        "Q",
        "B",
    )


def test_resolved_metric_shows_the_given_count(survey, settings_file):
    at = _run(survey, settings_file, FakeProcessor(), resolved=4)

    assert {m.label: m.value for m in at.metric}["Resolved"] == "4"


def test_cards_sharing_a_key_cannot_be_corrected(settings_file):
    data = pl.DataFrame({"hhid": ["A", "A"], "KEY": ["k1", "k1"]})
    at = _run(data, settings_file, FakeProcessor())

    assert not at.radio
    assert "share a KEY" in at.warning[0].value


def test_a_key_also_on_a_hidden_record_cannot_be_corrected(survey, settings_file):
    # Records to Include hides a fourth record that also has KEY k1.
    all_data = pl.concat([survey, pl.DataFrame({"hhid": ["Z"], "KEY": ["k1"]})])
    at = _run(survey, settings_file, FakeProcessor(), all_data=all_data)

    assert not at.radio
    assert "share a KEY" in at.warning[0].value


def test_a_missing_key_cannot_be_corrected(settings_file):
    data = pl.DataFrame({"hhid": ["A", "A"], "KEY": ["k1", None]})
    at = _run(data, settings_file, FakeProcessor())

    assert not at.radio
    assert "have no KEY" in at.warning[0].value


def test_decision_widgets_are_scoped_to_the_dataset(survey, settings_file):
    # Cards with the same ID in another dataset must not share decisions.
    at = _run(survey, settings_file, FakeProcessor())

    assert "survey_alias" in _radio(at, "k1").key
    assert "survey_alias" in _reason(at).key


@pytest.mark.parametrize("scope", ["_logged_key", "_notice_scope"])
def test_session_state_is_scoped_to_the_dataset(survey, scope):
    # A count or notice from one dataset's cards must not show on another's.
    from datasure.checks import id_duplicates_ui
    from datasure.checks.id_duplicates_ui import IdView

    def view(alias):
        return IdView(
            name="survey",
            data=survey,
            id_col="hhid",
            key_col="KEY",
            date_col=None,
            staff_col=None,
            team_col=None,
            display_cols_setting="id_table_display_cols",
            alias=alias,
            processor=FakeProcessor(),
        )

    key = getattr(id_duplicates_ui, scope)
    assert key(view("alias_a")) != key(view("alias_b"))
