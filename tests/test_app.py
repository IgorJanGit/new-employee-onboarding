from datetime import date, timedelta

import pytest

from onboarding import create_app

TODAY = date(2026, 10, 21)


@pytest.fixture
def app():
    return create_app(today=TODAY, data_path=None)


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, user_id):
    client.get(f"/switch?user_id={user_id}")


def test_no_user_shows_picker(client):
    assert b"Who's using the prototype?" in client.get("/").data


def test_unknown_user_is_logged_out(client):
    login(client, "emily-park")
    login(client, "hacker")
    assert b"Who's using the prototype?" in client.get("/").data


@pytest.mark.parametrize(
    "user_id, target",
    [
        ("sarah", "/hr"),
        ("david", "/manager"),
        ("emily-park", "/me"),
    ],
)
def test_home_redirects_by_role(client, user_id, target):
    login(client, user_id)
    assert client.get("/").headers["Location"].endswith(target)


def test_new_hire_sees_focus_and_board(client):
    login(client, "emily-park")
    html = client.get("/me").data.decode()
    assert "Focus on now" in html
    assert "Set up your local dev environment" in html  # her overdue task
    assert "Weeks 2–4" in html


def test_new_hire_can_check_off_own_task(client, app):
    login(client, "emily-park")
    store = app.extensions["store"]
    task = next(t for t in store.tasks_for("emily-park", owner="new_hire") if not t.done)
    r = client.post(f"/tasks/{task.id}/toggle", data={"done": "1", "next": "/me"})
    assert r.status_code == 302 and r.headers["Location"] == "/me"
    assert store.tasks[task.id].done


def test_new_hire_cannot_check_off_manager_task(client, app):
    login(client, "emily-park")
    task = app.extensions["store"].tasks_for("emily-park", owner="manager")[0]
    assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 403


def test_new_hire_cannot_check_off_someone_elses_task(client, app):
    login(client, "emily-park")
    task = app.extensions["store"].tasks_for("jordan-reyes", owner="new_hire")[0]
    assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 403


def test_toggle_requires_login_and_existing_task(client):
    assert client.post("/tasks/1/toggle").status_code == 401
    login(client, "emily-park")
    assert client.post("/tasks/99999/toggle").status_code == 404


def test_toggle_ignores_offsite_next(client, app):
    login(client, "emily-park")
    task = app.extensions["store"].tasks_for("emily-park", owner="new_hire")[-1]
    r = client.post(f"/tasks/{task.id}/toggle", data={"done": "1", "next": "//evil.com"})
    assert "evil.com" not in r.headers["Location"]


def test_manager_sees_only_their_hires(client):
    login(client, "david")
    html = client.get("/manager").data.decode()
    table = html[html.index('<table class="hires">') : html.index("</table>")]
    assert "Emily Park" in table and "Jordan Reyes" in table
    assert "Marcus Bell" not in table


def test_manager_cannot_open_other_managers_hire(client):
    login(client, "david")
    assert client.get("/hires/marcus-bell").status_code == 403


def test_manager_with_no_hires_sees_empty_state(client):
    login(client, "lena")
    assert b"No new hires yet" in client.get("/manager").data


def test_overdue_is_highlighted_for_manager(client):
    login(client, "priya")
    html = client.get("/manager").data.decode()
    assert "Needs attention" in html and "1 overdue" in html


def test_new_hire_cannot_open_hr_or_manager_pages(client):
    login(client, "emily-park")
    assert client.get("/hr").status_code == 403
    assert client.get("/manager").status_code == 403
    assert client.get("/hires/emily-park").status_code == 403


def test_hr_creates_hire_and_manager_sees_them(client):
    login(client, "sarah")
    start = (TODAY + timedelta(days=12)).isoformat()
    r = client.post(
        "/hr",
        data=dict(
            name="Ana Lopez",
            title="Support Specialist",
            department="Customer Support",
            manager_id="lena",
            start_date=start,
        ),
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Created Ana Lopez&#39;s Customer Support onboarding plan" in r.data
    login(client, "lena")
    assert b"Ana Lopez" in client.get("/manager").data


def test_hr_form_shows_errors_and_keeps_input(client):
    login(client, "sarah")
    r = client.post(
        "/hr",
        data=dict(name="Ana Lopez", department="", manager_id="lena", start_date="not-a-date"),
    )
    assert r.status_code == 400
    html = r.data.decode()
    assert "Choose a department." in html and "Enter a valid start date." in html
    assert 'value="Ana Lopez"' in html


def test_unknown_hire_is_404(client):
    login(client, "sarah")
    assert client.get("/hires/nobody").status_code == 404


def test_reset_restores_sample_data(client, app):
    login(client, "sarah")
    client.post(
        "/hr",
        data=dict(
            name="Ana Lopez",
            department="Sales",
            manager_id="priya",
            start_date=(TODAY + timedelta(days=5)).isoformat(),
        ),
    )
    r = client.post("/reset", follow_redirects=True)
    assert b"Demo data reset" in r.data
    assert "ana-lopez" not in app.extensions["store"].hires
    assert b"Ana Lopez" not in client.get("/hr").data


def test_manager_todos_only_show_this_week(client):
    login(client, "priya")
    html = client.get("/manager").data.decode()
    assert "Order laptop and equipment" in html  # overdue
    assert "Hand over first territory accounts" not in html  # weeks away
    assert "more later in their onboarding" in html


def test_toggle_shows_new_progress(client, app):
    login(client, "emily-park")
    store = app.extensions["store"]
    task = next(t for t in store.tasks_for("emily-park", owner="new_hire") if not t.done)
    r = client.post(
        f"/tasks/{task.id}/toggle", data={"done": "1", "next": "/me"}, follow_redirects=True
    )
    percent = store.progress("emily-park").percent
    assert f"Your onboarding is now {percent}% complete." in r.data.decode()
    r = client.post(
        f"/tasks/{task.id}/toggle", data={"done": "0", "next": "/me"}, follow_redirects=True
    )
    assert "marked not done" in r.data.decode()


def test_manager_toggle_message_names_the_hire(client, app):
    login(client, "priya")
    task = app.extensions["store"].tasks_for("marcus-bell", owner="manager")[0]
    r = client.post(
        f"/tasks/{task.id}/toggle", data={"done": "1", "next": "/manager"}, follow_redirects=True
    )
    assert "Marcus&#39;s onboarding is now" in r.data.decode()


def test_hr_form_rejects_manager_from_other_department(client):
    login(client, "sarah")
    r = client.post(
        "/hr",
        data=dict(
            name="Ana Lopez",
            department="Sales",
            manager_id="david",
            start_date=(TODAY + timedelta(days=5)).isoformat(),
        ),
    )
    assert r.status_code == 400
    assert "Choose a Sales manager." in r.data.decode()


def test_hr_form_tags_managers_with_department(client):
    login(client, "sarah")
    html = client.get("/hr").data.decode()
    assert 'value="priya" data-department="Sales"' in html


# --- tasks added by managers and HR ---------------------------------------------


def add_task(client, hire_id, **overrides):
    data = dict(
        title="Meet the security team",
        description="Ask about the VPN.",
        owner="new_hire",
        due=(TODAY + timedelta(days=3)).isoformat(),
    )
    return client.post(f"/hires/{hire_id}/tasks", data={**data, **overrides})


def test_manager_adds_task_and_new_hire_sees_it(client, app):
    login(client, "david")
    r = add_task(client, "emily-park")
    assert r.status_code == 302
    task = next(
        t
        for t in app.extensions["store"].tasks_for("emily-park")
        if t.title == "Meet the security team"
    )
    assert task.created_by == "david"
    login(client, "emily-park")
    html = client.get("/me").data.decode()
    assert "Meet the security team" in html and "Added by David" in html


def test_manager_cannot_add_task_for_other_managers_hire(client):
    login(client, "david")
    assert add_task(client, "marcus-bell").status_code == 403


def test_new_hire_cannot_add_tasks(client):
    login(client, "emily-park")
    assert add_task(client, "emily-park").status_code == 403


def test_add_task_errors_keep_input(client):
    login(client, "priya")
    r = add_task(client, "marcus-bell", title="", due=(TODAY - timedelta(days=2)).isoformat())
    assert r.status_code == 400
    html = r.data.decode()
    assert "Enter what needs to be done." in html
    assert "Due date can&#39;t be in the past." in html
    assert 'value="Ask about the VPN."' in html


def test_hr_adds_hr_task_and_sees_it_in_their_todos(client, app):
    login(client, "sarah")
    add_task(client, "marcus-bell", title="Order Marcus's parking pass", owner="hr")
    html = client.get("/hr").data.decode()
    assert "Your to-dos this week" in html
    assert "Order Marcus&#39;s parking pass" in html


def test_only_hr_can_check_off_hr_tasks(client, app):
    store = app.extensions["store"]
    task = store.tasks_for("marcus-bell", owner="hr")[0]
    login(client, "priya")
    assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 403
    login(client, "sarah")
    assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 302
    assert store.tasks[task.id].done


def test_creator_can_remove_added_task(client, app):
    store = app.extensions["store"]
    task = next(t for t in store.tasks_for("emily-park") if t.created_by == "david")
    login(client, "david")
    assert client.post(f"/tasks/{task.id}/delete").status_code == 302
    assert task.id not in store.tasks


def test_hr_can_remove_a_managers_added_task(client, app):
    store = app.extensions["store"]
    task = next(t for t in store.tasks_for("emily-park") if t.created_by == "david")
    login(client, "sarah")
    assert client.post(f"/tasks/{task.id}/delete").status_code == 302


def test_template_tasks_cannot_be_removed(client, app):
    task = app.extensions["store"].tasks_for("emily-park")[0]
    assert task.created_by is None
    login(client, "sarah")
    assert client.post(f"/tasks/{task.id}/delete").status_code == 403


def test_others_cannot_remove_added_task(client, app):
    task = next(t for t in app.extensions["store"].tasks_for("emily-park") if t.created_by)
    login(client, "emily-park")
    assert client.post(f"/tasks/{task.id}/delete").status_code == 403
    login(client, "priya")
    assert client.post(f"/tasks/{task.id}/delete").status_code == 403


# --- dual sign-off ----------------------------------------------------------------


def emily_1on1(app):
    return next(
        t
        for t in app.extensions["store"].tasks_for("emily-park")
        if t.title == "First-day 1:1 with your manager"
    )


def test_manager_confirming_completes_half_confirmed_task(client, app):
    task = emily_1on1(app)
    login(client, "david")
    assert "First-day 1:1 with your manager" in client.get("/manager").data.decode()
    r = client.post(
        f"/tasks/{task.id}/toggle", data={"done": "1", "next": "/manager"}, follow_redirects=True
    )
    assert "You both confirmed" in r.data.decode()
    assert task.done


def test_first_confirmation_says_who_it_is_waiting_for(client, app):
    store = app.extensions["store"]
    task = next(t for t in store.tasks_for("emily-park") if t.title == "Set 30-day goals together")
    login(client, "emily-park")
    r = client.post(
        f"/tasks/{task.id}/toggle", data={"done": "1", "next": "/me"}, follow_redirects=True
    )
    assert "Waiting for David to confirm too" in r.data.decode()
    assert not task.done and task.confirmed.keys() == {"new_hire"}


def test_new_hire_undo_only_removes_their_own_confirmation(client, app):
    task = emily_1on1(app)
    login(client, "david")
    client.post(f"/tasks/{task.id}/toggle", data={"done": "1"})
    login(client, "emily-park")
    client.post(f"/tasks/{task.id}/toggle", data={"done": "0"})
    assert task.confirmed.keys() == {"manager"} and not task.done


def test_hr_and_other_managers_cannot_confirm_dual_tasks(client, app):
    task = emily_1on1(app)
    for user_id in ("sarah", "priya"):
        login(client, user_id)
        assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 403
    assert not task.done


def test_manager_still_cannot_complete_new_hire_only_tasks(client, app):
    task = app.extensions["store"].tasks_for("emily-park", owner="new_hire")[-1]
    login(client, "david")
    assert client.post(f"/tasks/{task.id}/toggle", data={"done": "1"}).status_code == 403


def test_card_shows_who_has_confirmed(client):
    login(client, "david")
    html = client.get("/hires/emily-park").data.decode()
    assert "Waiting for you" in html  # David is the one holding up the 1:1


def test_add_task_can_require_both(client, app):
    login(client, "david")
    client.post(
        "/hires/emily-park/tasks",
        data=dict(
            title="Agree on on-call readiness",
            owner="both",
            due=(TODAY + timedelta(days=5)).isoformat(),
        ),
    )
    task = next(
        t
        for t in app.extensions["store"].tasks_for("emily-park")
        if t.title == "Agree on on-call readiness"
    )
    assert task.dual


# --- HR assigns a task to several people ------------------------------------------


def assign(client, hire_ids, **overrides):
    data = dict(
        title="Attend the benefits webinar",
        description="Thursday 2pm.",
        owner="new_hire",
        due=(TODAY + timedelta(days=3)).isoformat(),
        hire_ids=hire_ids,
    )
    return client.post("/hr/tasks", data={**data, **overrides}, follow_redirects=True)


def test_hr_assigns_task_to_several_people(client, app):
    login(client, "sarah")
    r = assign(client, ["emily-park", "jordan-reyes", "marcus-bell"])
    assert "Assigned “Attend the benefits webinar” to 3 people: Emily, Jordan, Marcus." in (
        r.data.decode()
    )
    store = app.extensions["store"]
    for hire_id in ("emily-park", "jordan-reyes", "marcus-bell"):
        task = next(t for t in store.tasks_for(hire_id) if t.title == "Attend the benefits webinar")
        assert task.created_by == "sarah"
    login(client, "marcus-bell")
    assert "Attend the benefits webinar" in client.get("/me").data.decode()


def test_assigning_again_reports_skipped_people(client):
    login(client, "sarah")
    assign(client, ["emily-park"])
    html = assign(client, ["emily-park", "jordan-reyes"]).data.decode()
    assert "to 1 person: Jordan." in html
    assert "Skipped Emily: they already have" in html


def test_assign_requires_people_and_keeps_input(client):
    login(client, "sarah")
    r = assign(client, [], title="")
    assert r.status_code == 400
    html = r.data.decode()
    assert "Choose at least one person." in html
    assert "Enter what needs to be done." in html
    assert 'value="Thursday 2pm."' in html


def test_assign_rejects_unknown_people(client, app):
    login(client, "sarah")
    r = assign(client, ["emily-park", "ghost"])
    assert r.status_code == 400
    assert not any(
        t.title == "Attend the benefits webinar" for t in app.extensions["store"].tasks.values()
    )


def test_assign_keeps_checked_people_after_error(client):
    login(client, "sarah")
    html = assign(client, ["jordan-reyes"], title="").data.decode()
    assert 'value="jordan-reyes"\n                     checked' in html or (
        'value="jordan-reyes" checked' in " ".join(html.split())
    )


def test_only_hr_can_bulk_assign(client):
    for user_id in ("david", "emily-park"):
        login(client, user_id)
        assert client.post("/hr/tasks", data={"title": "x"}).status_code == 403
