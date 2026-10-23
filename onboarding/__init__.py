from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .store import (
    OWNERS,
    PHASES,
    Store,
    open_store,
    phase_for,
    seed,
    validate_new_hire,
    validate_new_task,
)
from .templates_data import DEPARTMENTS

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"


def create_app(today: date | None = None, data_path: Path | None = DEFAULT_DATA_PATH) -> Flask:
    """data_path=None keeps everything in memory (used by the tests)."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-only-prototype-key"
    today = today or date.today()
    store: Store = open_store(today, data_path)
    app.extensions["store"] = store

    # --- helpers ------------------------------------------------------------

    def current_user():
        return store.people.get(session.get("user_id", ""))

    def require_role(*roles):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = current_user()
                if not user:
                    return redirect(url_for("index"))
                if user.role not in roles:
                    abort(403)
                return view(user, *args, **kwargs)

            return wrapped

        return decorator

    def can_view_hire(user, hire) -> bool:
        return user.role == "hr" or (user.role == "manager" and hire.manager_id == user.id)

    def party_of(user, task) -> str | None:
        """Which side of this task the user is on: 'new_hire', 'manager', 'hr' or None."""
        if not user:
            return None
        hire = store.hires[task.hire_id]
        if user.id == hire.person_id:
            return "new_hire"
        if user.id == hire.manager_id:
            return "manager"
        return "hr" if user.role == "hr" else None

    def can_check(user, task) -> bool:
        """Only the person who owns a task can check it off. Dual tasks: each side confirms."""
        party = party_of(user, task)
        return party is not None and task.involves(party)

    def can_remove(user, task) -> bool:
        """Template tasks stay; added tasks can be removed by whoever added them, or HR."""
        return bool(user and task.created_by and (user.id == task.created_by or user.role == "hr"))

    def due_this_week(tasks, party):
        """Tasks still waiting on this party, due within 7 days (or late), plus how many later."""
        open_tasks = sorted((t for t in tasks if not t.done_by(party)), key=lambda t: t.due)
        horizon = store.today + timedelta(days=7)
        soon = [t for t in open_tasks if t.due <= horizon]
        return soon, len(open_tasks) - len(soon)

    def safe_next(default: str) -> str:
        target = request.form.get("next", "")
        return target if target.startswith("/") and not target.startswith("//") else default

    @app.template_filter("due_label")
    def due_label(task) -> str:
        days = (task.due - store.today).days
        if task.done:
            return f"Done {task.done_on:%b %-d}"
        if days < 0:
            return f"Overdue · was due {task.due:%b %-d}"
        if days == 0:
            return "Due today"
        if days == 1:
            return "Due tomorrow"
        if days < 7:
            return f"Due {task.due:%A}"
        return f"Due {task.due:%b %-d}"

    @app.context_processor
    def inject():
        people = sorted(
            store.people.values(), key=lambda p: ("hr", "manager", "new_hire").index(p.role)
        )
        user = current_user()
        return dict(
            user=user,
            people=people,
            store=store,
            today=store.today,
            PHASES=PHASES,
            OWNERS=OWNERS,
            can_check=lambda task: can_check(user, task),
            party_of=lambda task: party_of(user, task),
            can_remove=lambda task: can_remove(user, task),
        )

    # --- routes -------------------------------------------------------------

    @app.get("/")
    def index():
        user = current_user()
        if not user:
            return render_template("pick_user.html")
        return redirect(
            url_for({"hr": "hr_home", "manager": "manager_home", "new_hire": "my_plan"}[user.role])
        )

    @app.get("/switch")
    def switch_user():
        user_id = request.args.get("user_id", "")
        if user_id not in store.people:
            session.pop("user_id", None)
        else:
            session["user_id"] = user_id
        return redirect(url_for("index"))

    @app.get("/me")
    @require_role("new_hire")
    def my_plan(user):
        hire = store.hires[user.id]
        focus, rest = store.focus(hire.person_id)
        my_tasks = store.tasks_for(hire.person_id, party="new_hire")
        current = phase_for((store.today - hire.start_date).days)
        phase_keys = [key for key, _ in PHASES]
        board = []
        for key, label in PHASES:
            # Open cards first, finished ones sink to the bottom of the column.
            tasks = sorted(
                (t for t in my_tasks if t.phase == key), key=lambda t: t.done_by("new_hire")
            )
            open_count = sum(not t.done_by("new_hire") for t in tasks)
            # Later phases start collapsed; earlier ones stay open only if something slipped.
            if phase_keys.index(key) > phase_keys.index(current):
                expanded = False
            else:
                expanded = key == current or open_count > 0
            board.append(dict(label=label, tasks=tasks, open=open_count, expanded=expanded))
        others_tasks = [t for t in store.tasks_for(hire.person_id) if not t.involves("new_hire")]
        return render_template(
            "my_plan.html",
            hire=hire,
            focus=focus,
            rest=rest,
            board=board,
            others_tasks=others_tasks,
            manager=store.people[hire.manager_id],
            progress=store.progress(hire.person_id),
        )

    @app.get("/manager")
    @require_role("manager")
    def manager_home(user):
        hires = store.hires_for_manager(user.id)
        # Same idea as the new hire's focus list: only what's due this week (or late).
        soon, later_count = due_this_week(
            (t for h in hires for t in store.tasks_for(h.person_id, party="manager")), "manager"
        )
        return render_template("manager.html", hires=hires, my_tasks=soon, later_count=later_count)

    def viewable_hire(user, hire_id):
        hire = store.hires.get(hire_id) or abort(404)
        if not can_view_hire(user, hire):
            abort(403)
        return hire

    def render_hire_detail(hire, form=None, errors=None):
        default_due = max(store.today, hire.start_date) + timedelta(days=2)
        return render_template(
            "hire_detail.html",
            hire=hire,
            tasks=store.tasks_for(hire.person_id),
            manager=store.people[hire.manager_id],
            progress=store.progress(hire.person_id),
            form=form or {},
            errors=errors or {},
            default_due=default_due.isoformat(),
        ), (400 if errors else 200)

    @app.get("/hires/<hire_id>")
    @require_role("hr", "manager")
    def hire_detail(user, hire_id):
        return render_hire_detail(viewable_hire(user, hire_id))

    @app.post("/hires/<hire_id>/tasks")
    @require_role("hr", "manager")
    def add_task(user, hire_id):
        hire = viewable_hire(user, hire_id)
        form = request.form.to_dict()
        data, errors = validate_new_task(form, store)
        if errors:
            return render_hire_detail(hire, form, errors)
        task = store.add_task(hire.person_id, created_by=user.id, **data)
        flash(f"Added “{task.title}” to {hire.name.split()[0]}'s plan ({OWNERS[task.owner]}).")
        return redirect(url_for("hire_detail", hire_id=hire.person_id))

    @app.post("/tasks/<int:task_id>/delete")
    def delete_task(task_id):
        user = current_user()
        if not user:
            abort(401)
        task = store.tasks.get(task_id) or abort(404)
        if not can_remove(user, task):
            abort(403)
        store.delete_task(task_id)
        flash(f"Removed “{task.title}”.")
        return redirect(url_for("hire_detail", hire_id=task.hire_id))

    @app.route("/hr", methods=["GET", "POST"])
    @require_role("hr")
    def hr_home(user):
        form, errors = {}, {}
        if request.method == "POST":
            form = request.form.to_dict()
            data, errors = validate_new_hire(form, store)
            if not errors:
                hire = store.add_hire(**data)
                count = len(store.tasks_for(hire.person_id))
                flash(
                    f"Created {hire.name}'s {hire.department} onboarding plan "
                    f"({count} tasks). {store.people[hire.manager_id].name} can now "
                    "track progress."
                )
                return redirect(url_for("hire_detail", hire_id=hire.person_id))
        return render_hr(form=form, errors=errors)

    @app.post("/hr/tasks")
    @require_role("hr")
    def hr_assign_task(user):
        """Assign one task to several new hires at once."""
        assign = request.form.to_dict()
        hire_ids = request.form.getlist("hire_ids")
        assign["hire_ids"] = hire_ids
        data, assign_errors = validate_new_task(assign, store)
        if not hire_ids:
            assign_errors["hire_ids"] = "Choose at least one person."
        elif any(h not in store.hires for h in hire_ids):
            assign_errors["hire_ids"] = "One of the people you chose no longer exists."
        if assign_errors:
            return render_hr(assign=assign, assign_errors=assign_errors)

        assigned, skipped = store.assign_task(hire_ids, created_by=user.id, **data)

        def names(hires):
            return ", ".join(h.name.split()[0] for h in hires)

        if assigned:
            people = "1 person" if len(assigned) == 1 else f"{len(assigned)} people"
            flash(f"Assigned “{data['title']}” to {people}: {names(assigned)}.")
        if skipped:
            flash(f"Skipped {names(skipped)}: they already have “{data['title']}”.")
        return redirect(url_for("hr_home"))

    def render_hr(form=None, errors=None, assign=None, assign_errors=None):
        default_start = store.today + timedelta(days=14)
        hr_tasks, hr_later_count = due_this_week(
            (t for h in store.all_hires() for t in store.tasks_for(h.person_id, owner="hr")), "hr"
        )
        return render_template(
            "hr.html",
            hr_tasks=hr_tasks,
            hr_later_count=hr_later_count,
            hires=store.all_hires(),
            departments=DEPARTMENTS,
            managers=store.managers(),
            form=form or {},
            errors=errors or {},
            default_start=default_start.isoformat(),
            assign=assign or {},
            assign_errors=assign_errors or {},
            default_due=(store.today + timedelta(days=3)).isoformat(),
        ), (400 if errors or assign_errors else 200)

    @app.post("/tasks/<int:task_id>/toggle")
    def toggle_task(task_id):
        user = current_user()
        if not user:
            abort(401)
        task = store.tasks.get(task_id) or abort(404)
        hire = store.hires[task.hire_id]
        if not can_check(user, task):
            abort(403)
        done = request.form.get("done") == "1"
        party = party_of(user, task)
        store.set_done(task_id, done, party)
        percent = store.progress(hire.person_id).percent
        whose = "Your" if user.id == hire.person_id else f"{hire.name.split()[0]}'s"
        if task.dual and not task.done:
            other = task.waiting_on[0] if task.waiting_on else None
            other_name = (
                hire.name.split()[0]
                if other == "new_hire"
                else store.people[hire.manager_id].name.split()[0]
            )
            if done:
                flash(
                    f"You confirmed “{task.title}”. Waiting for {other_name} to confirm too; "
                    "it counts as done once you both have."
                )
            else:
                flash(f"Removed your confirmation of “{task.title}”.")
        elif task.dual and done:
            flash(
                f"✓ You both confirmed “{task.title}”. "
                f"{whose} onboarding is now {percent}% complete."
            )
        elif done:
            flash(f"✓ “{task.title}” done. {whose} onboarding is now {percent}% complete.")
        else:
            flash(f"“{task.title}” marked not done. {whose} onboarding is {percent}% complete.")
        return redirect(safe_next(url_for("index")))

    @app.post("/reset")
    def reset_demo():
        nonlocal store
        store = seed(today, data_path)
        app.extensions["store"] = store
        flash("Demo data reset to the original sample hires.")
        return redirect(url_for("index"))

    @app.errorhandler(403)
    def forbidden(_):
        return render_template(
            "error.html", code=403, message="You don't have access to that page."
        ), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="We couldn't find that page."), 404

    return app
