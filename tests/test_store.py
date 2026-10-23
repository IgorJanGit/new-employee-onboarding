from datetime import date, timedelta

import pytest

from onboarding.store import FOCUS_LIMIT, Store, open_store, seed, validate_new_hire
from onboarding.templates_data import BASE_TASKS, DEPARTMENT_TASKS, GENERAL_TASKS

TODAY = date(2026, 10, 21)  # a Wednesday


@pytest.fixture
def store():
    return seed(TODAY)


def titles(store, hire_id):
    return {t.title for t in store.tasks_for(hire_id)}


def test_plan_is_base_plus_department_tasks(store):
    hire = store.add_hire("Ana Lopez", "", "Sales", "priya", TODAY + timedelta(days=7))
    got = titles(store, hire.person_id)
    assert got == {t.title for t in BASE_TASKS + DEPARTMENT_TASKS["Sales"]}
    assert not got & {t.title for t in DEPARTMENT_TASKS["Engineering"]}


def test_department_without_template_gets_general_plan(store):
    hire = store.add_hire("Sam Ito", "", "Operations", "omar", TODAY + timedelta(days=7))
    assert titles(store, hire.person_id) == {t.title for t in BASE_TASKS + GENERAL_TASKS}


def test_due_dates_are_relative_to_start_date(store):
    start = date(2026, 11, 2)
    hire = store.add_hire("Ana Lopez", "", "Engineering", "david", start)
    for task in store.tasks_for(hire.person_id):
        assert task.due == start + timedelta(days=task.offset_days)


def test_focus_is_capped_and_puts_overdue_first(store):
    focus, rest = store.focus("emily-park")
    assert 0 < len(focus) <= FOCUS_LIMIT
    assert store.is_overdue(focus[0])
    assert all(t.involves("new_hire") and not t.done_by("new_hire") for t in focus + rest)
    assert not set(t.id for t in focus) & set(t.id for t in rest)


def test_focus_shows_next_task_when_nothing_is_due_soon(store):
    hire = store.add_hire("Far Future", "", "Sales", "priya", TODAY + timedelta(days=60))
    focus, _ = store.focus(hire.person_id)
    assert len(focus) == 1  # never a blank screen while work remains


def test_focus_empty_when_everything_done(store):
    for t in store.tasks_for("jordan-reyes"):
        for party in ("new_hire", "manager") if t.dual else (None,):
            store.set_done(t.id, True, party)
    assert store.focus("jordan-reyes") == ([], [])
    assert store.status(store.hires["jordan-reyes"]) == "complete"


def test_status_flags_overdue_even_before_start(store):
    # Marcus starts next week, but his laptop order (a manager task) is overdue.
    assert store.status(store.hires["marcus-bell"]) == "attention"


def test_unchecking_a_task_clears_done(store):
    task = store.tasks_for("emily-park")[0]
    store.set_done(task.id, True)
    store.set_done(task.id, False)
    assert not task.done


def test_day_label(store):
    assert store.day_label(store.hires["emily-park"]) == "Day 4"
    assert store.day_label(store.hires["marcus-bell"]) == "Starts in 6 days"


def test_duplicate_names_get_unique_ids(store):
    a = store.add_hire("Emily Park", "", "Sales", "priya", TODAY + timedelta(days=30))
    assert a.person_id == "emily-park-2"


def test_state_round_trips_through_json(tmp_path):
    path = tmp_path / "state.json"
    s1 = seed(TODAY, path)
    task = s1.tasks_for("marcus-bell")[0]
    s1.set_done(task.id, True)
    s2 = open_store(TODAY, path)
    assert s2.tasks[task.id].done
    assert s2.hires["marcus-bell"].start_date == s1.hires["marcus-bell"].start_date
    new = s2.add_hire("Ana Lopez", "", "Sales", "priya", TODAY)
    assert min(t.id for t in s2.tasks_for(new.person_id)) > max(s1.tasks)


def test_corrupt_state_file_falls_back_to_sample_data(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert "emily-park" in open_store(TODAY, path).hires


# --- validation ----------------------------------------------------------------


def form(**overrides):
    base = dict(
        name="Ana Lopez",
        title="",
        department="Sales",
        manager_id="priya",
        start_date=(TODAY + timedelta(days=10)).isoformat(),
    )
    return {**base, **overrides}


def test_valid_form(store):
    data, errors = validate_new_hire(form(name="  Ana   Lopez "), store)
    assert errors == {}
    assert data["name"] == "Ana Lopez"


@pytest.mark.parametrize(
    "overrides, field",
    [
        (dict(name="   "), "name"),
        (dict(name="x" * 81), "name"),
        (dict(department="Space Program"), "department"),
        (dict(manager_id="emily-park"), "manager_id"),  # a new hire isn't a manager
        (dict(manager_id="nobody"), "manager_id"),
        (dict(start_date="2026-13-40"), "start_date"),
        (dict(start_date=""), "start_date"),
        (dict(start_date=(TODAY - timedelta(days=30)).isoformat()), "start_date"),
        (dict(start_date=(TODAY + timedelta(days=400)).isoformat()), "start_date"),
    ],
)
def test_invalid_form(store, overrides, field):
    _, errors = validate_new_hire(form(**overrides), store)
    assert field in errors


def test_recent_past_start_is_allowed(store):
    _, errors = validate_new_hire(form(start_date=(TODAY - timedelta(days=3)).isoformat()), store)
    assert errors == {}


def test_duplicate_hire_rejected(store):
    start = store.hires["marcus-bell"].start_date.isoformat()
    _, errors = validate_new_hire(form(name="marcus bell", start_date=start), store)
    assert "already has an onboarding plan" in errors["name"]


def test_store_without_path_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Store(TODAY)
    s.save()
    assert list(tmp_path.iterdir()) == []


def test_manager_must_be_in_hires_department(store):
    # A Sales hire can't be given the Engineering manager.
    _, errors = validate_new_hire(form(department="Sales", manager_id="david"), store)
    assert errors["manager_id"] == ("David Chen manages Engineering. Choose a Sales manager.")


@pytest.mark.parametrize(
    "department, manager_id",
    [
        ("Engineering", "david"),
        ("Sales", "priya"),
        ("Customer Support", "lena"),
        ("Operations", "omar"),
    ],
)
def test_every_department_has_a_matching_manager(store, department, manager_id):
    _, errors = validate_new_hire(form(department=department, manager_id=manager_id), store)
    assert errors == {}


def test_state_saved_before_manager_departments_is_reseeded(tmp_path):
    import json

    path = tmp_path / "state.json"
    seed(TODAY, path)
    data = json.loads(path.read_text())
    for person in data["people"]:
        person.pop("department")
    path.write_text(json.dumps(data))
    store = open_store(TODAY, path)
    assert store.people["david"].department == "Engineering"


# --- tasks added by managers and HR ---------------------------------------------

from onboarding.store import validate_new_task  # noqa: E402


def task_form(**overrides):
    base = dict(
        title="Meet the security team",
        description="",
        owner="new_hire",
        due=(TODAY + timedelta(days=3)).isoformat(),
    )
    return {**base, **overrides}


def test_added_task_lands_in_the_right_phase(store):
    hire = store.hires["marcus-bell"]  # starts in 6 days
    task = store.add_task(
        hire.person_id,
        "Read the sales playbook",
        "",
        "new_hire",
        hire.start_date + timedelta(days=10),
        created_by="priya",
    )
    assert task.phase == "weeks2_4"
    assert task.created_by == "priya"
    assert task in store.tasks_for(hire.person_id)


def test_added_task_counts_toward_progress(store):
    before = store.progress("jordan-reyes").total
    store.add_task(
        "jordan-reyes",
        "Demo your first dashboard",
        "",
        "new_hire",
        TODAY + timedelta(days=2),
        created_by="david",
    )
    assert store.progress("jordan-reyes").total == before + 1


def test_seed_includes_a_task_added_by_a_manager(store):
    added = [t for t in store.tasks_for("emily-park") if t.created_by]
    assert [t.created_by for t in added] == ["david"]


def test_valid_task_form(store):
    data, errors = validate_new_task(task_form(title="  Meet   the team "), store)
    assert errors == {}
    assert data["title"] == "Meet the team"


@pytest.mark.parametrize(
    "overrides, field",
    [
        (dict(title=" "), "title"),
        (dict(title="x" * 101), "title"),
        (dict(description="x" * 301), "description"),
        (dict(owner="ceo"), "owner"),
        (dict(owner=""), "owner"),
        (dict(due="tomorrow"), "due"),
        (dict(due=(TODAY - timedelta(days=1)).isoformat()), "due"),
        (dict(due=(TODAY + timedelta(days=400)).isoformat()), "due"),
    ],
)
def test_invalid_task_form(store, overrides, field):
    _, errors = validate_new_task(task_form(**overrides), store)
    assert field in errors


def test_added_task_survives_save_and_reload(tmp_path):
    path = tmp_path / "state.json"
    s1 = seed(TODAY, path)
    task = s1.add_task("marcus-bell", "Call Marcus", "", "hr", TODAY, created_by="sarah")
    s2 = open_store(TODAY, path)
    assert s2.tasks[task.id].created_by == "sarah"
    assert s2.tasks[task.id].owner == "hr"


# --- dual sign-off (new hire + manager) ------------------------------------------


def dual_task(store, hire_id="jordan-reyes"):
    return next(t for t in store.tasks_for(hire_id) if t.dual and not t.confirmed)


def test_joint_template_tasks_need_both_people(store):
    dual_titles = {t.title for t in store.tasks_for("emily-park") if t.dual}
    assert {
        "First-day 1:1 with your manager",
        "Set 30-day goals together",
        "30-day check-in",
    } <= dual_titles


def test_dual_task_done_only_after_both_confirm(store):
    task = dual_task(store)
    store.set_done(task.id, True, "new_hire")
    assert not task.done and task.waiting_on == ["manager"]
    assert task.done_by("new_hire") and not task.done_by("manager")
    store.set_done(task.id, True, "manager")
    assert task.done and task.waiting_on == []


def test_dual_confirmation_order_does_not_matter(store):
    task = dual_task(store)
    store.set_done(task.id, True, "manager")
    assert not task.done
    store.set_done(task.id, True, "new_hire")
    assert task.done


def test_one_side_undoing_reopens_a_dual_task(store):
    task = dual_task(store)
    store.set_done(task.id, True, "new_hire")
    store.set_done(task.id, True, "manager")
    store.set_done(task.id, False, "manager")
    assert not task.done and task.waiting_on == ["manager"]


def test_confirming_twice_is_harmless(store):
    task = dual_task(store)
    store.set_done(task.id, True, "new_hire")
    store.set_done(task.id, True, "new_hire")
    assert not task.done and task.waiting_on == ["manager"]


def test_dual_task_requires_a_party(store):
    with pytest.raises(ValueError):
        store.set_done(dual_task(store).id, True)


def test_half_confirmed_task_leaves_new_hires_focus_but_stays_overdue(store):
    task = next(
        t for t in store.tasks_for("emily-park") if t.title == "First-day 1:1 with your manager"
    )
    assert task.confirmed.keys() == {"new_hire"}  # seeded: Emily confirmed, David hasn't
    focus, rest = store.focus("emily-park")
    assert task not in focus + rest
    assert store.is_overdue(task)


def test_confirmations_survive_save_and_reload(tmp_path):
    path = tmp_path / "state.json"
    s1 = seed(TODAY, path)
    task = dual_task(s1)
    s1.set_done(task.id, True, "manager")
    s2 = open_store(TODAY, path)
    assert s2.tasks[task.id].confirmed == {"manager": TODAY}
    assert not s2.tasks[task.id].done


# --- HR assigns a task to several people ------------------------------------------


def test_assign_task_gives_each_person_their_own_copy(store):
    assigned, skipped = store.assign_task(
        ["emily-park", "marcus-bell"],
        "Attend the benefits webinar",
        "",
        "new_hire",
        TODAY + timedelta(days=2),
        created_by="sarah",
    )
    assert [h.person_id for h in assigned] == ["emily-park", "marcus-bell"] and skipped == []
    copies = [t for t in store.tasks.values() if t.title == "Attend the benefits webinar"]
    assert {t.hire_id for t in copies} == {"emily-park", "marcus-bell"}
    assert len({t.id for t in copies}) == 2  # checking one off doesn't affect the other


def test_assign_task_skips_people_who_already_have_it(store):
    store.assign_task(
        ["emily-park"], "Attend the benefits webinar", "", "new_hire", TODAY, created_by="sarah"
    )
    assigned, skipped = store.assign_task(
        ["emily-park", "jordan-reyes"],
        "attend the BENEFITS webinar",
        "",
        "new_hire",
        TODAY,
        created_by="sarah",
    )
    assert [h.person_id for h in assigned] == ["jordan-reyes"]
    assert [h.person_id for h in skipped] == ["emily-park"]


def test_assigned_task_phase_depends_on_each_start_date(store):
    due = TODAY + timedelta(days=2)
    store.assign_task(
        ["jordan-reyes", "marcus-bell"],
        "Fill in the culture survey",
        "",
        "new_hire",
        due,
        created_by="sarah",
    )
    phases = {
        t.hire_id: t.phase for t in store.tasks.values() if t.title == "Fill in the culture survey"
    }
    assert phases == {"jordan-reyes": "weeks2_4", "marcus-bell": "before"}
