"""Data store, seeded with realistic sample data relative to 'today'.

No real database on purpose: state lives in memory and is saved to a JSON file so
checked-off tasks survive a restart. "Reset demo data" re-seeds it.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .templates_data import DEPARTMENTS, plan_for

FOCUS_LIMIT = 3  # Emily: "I just want to know what I should focus on first."
FOCUS_WINDOW_DAYS = 3

# Joint tasks (a 1:1, agreeing on goals) only count once both people confirm them.
DUAL_PARTIES = ("new_hire", "manager")

PHASES = [
    ("before", "Before day 1"),
    ("week1", "Week 1"),
    ("weeks2_4", "Weeks 2–4"),
]


def phase_for(offset_days: int) -> str:
    if offset_days < 0:
        return "before"
    if offset_days < 7:
        return "week1"
    return "weeks2_4"


@dataclass
class Person:
    id: str
    name: str
    role: str  # "hr" | "manager" | "new_hire"
    title: str
    department: str = ""  # managers: the one department they can onboard people into


@dataclass
class Hire:
    person_id: str
    name: str
    title: str
    department: str
    manager_id: str
    start_date: date


@dataclass
class Task:
    id: int
    hire_id: str
    title: str
    description: str
    owner: str  # "new_hire" | "manager" | "hr" | "both" (new hire and manager each confirm)
    offset_days: int
    due: date
    done_on: date | None = None
    created_by: str | None = None  # None = came from the template; else the person who added it
    confirmed: dict[str, date] = field(default_factory=dict)  # "both" tasks: who confirmed, when

    @property
    def done(self) -> bool:
        return self.done_on is not None

    @property
    def dual(self) -> bool:
        return self.owner == "both"

    def involves(self, party: str) -> bool:
        """Does this person ('new_hire', 'manager' or 'hr') have to act on the task?"""
        return self.owner == party or (self.dual and party in DUAL_PARTIES)

    def done_by(self, party: str) -> bool:
        """Has this person done their part? For dual tasks, that's their own confirmation."""
        return party in self.confirmed if self.dual else self.done

    @property
    def waiting_on(self) -> list[str]:
        return [p for p in DUAL_PARTIES if p not in self.confirmed] if self.dual else []

    @property
    def phase(self) -> str:
        return phase_for(self.offset_days)


@dataclass
class Progress:
    done: int
    total: int
    overdue: list[Task]

    @property
    def percent(self) -> int:
        return round(100 * self.done / self.total) if self.total else 0


class Store:
    def __init__(self, today: date, path: Path | None = None):
        self.today = today
        self.path = path
        self.people: dict[str, Person] = {}
        self.hires: dict[str, Hire] = {}
        self.tasks: dict[int, Task] = {}
        self._next_task_id = 1

    # --- people & hires -------------------------------------------------

    def add_person(self, person: Person) -> Person:
        self.people[person.id] = person
        return person

    def managers(self) -> list[Person]:
        return [p for p in self.people.values() if p.role == "manager"]

    def hires_for_manager(self, manager_id: str) -> list[Hire]:
        return sorted(
            (h for h in self.hires.values() if h.manager_id == manager_id),
            key=lambda h: h.start_date,
        )

    def all_hires(self) -> list[Hire]:
        return sorted(self.hires.values(), key=lambda h: h.start_date)

    def _new_person_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "hire"
        candidate, n = base, 2
        while candidate in self.people:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def add_hire(
        self, name: str, title: str, department: str, manager_id: str, start_date: date
    ) -> Hire:
        """Create the new hire and auto-generate their plan from the department template."""
        person = self.add_person(Person(self._new_person_id(name), name, "new_hire", title))
        hire = Hire(person.id, name, title, department, manager_id, start_date)
        self.hires[hire.person_id] = hire
        for tmpl in plan_for(department):
            task = Task(
                id=self._next_task_id,
                hire_id=hire.person_id,
                title=tmpl.title,
                description=tmpl.description,
                owner=tmpl.owner,
                offset_days=tmpl.offset_days,
                due=start_date + timedelta(days=tmpl.offset_days),
            )
            self.tasks[task.id] = task
            self._next_task_id += 1
        self.save()
        return hire

    # --- tasks ------------------------------------------------------------

    def tasks_for(
        self, hire_id: str, owner: str | None = None, party: str | None = None
    ) -> list[Task]:
        """owner= matches the task's owner exactly; party= also includes dual tasks."""
        tasks = [t for t in self.tasks.values() if t.hire_id == hire_id]
        if owner:
            tasks = [t for t in tasks if t.owner == owner]
        if party:
            tasks = [t for t in tasks if t.involves(party)]
        return sorted(tasks, key=lambda t: (t.due, t.id))

    def add_task(
        self, hire_id: str, title: str, description: str, owner: str, due: date, created_by: str
    ) -> Task:
        """A one-off task a manager or HR adds to one person's plan."""
        hire = self.hires[hire_id]
        task = Task(
            id=self._next_task_id,
            hire_id=hire_id,
            title=title,
            description=description,
            owner=owner,
            offset_days=(due - hire.start_date).days,
            due=due,
            created_by=created_by,
        )
        self.tasks[task.id] = task
        self._next_task_id += 1
        self.save()
        return task

    def assign_task(
        self,
        hire_ids: list[str],
        title: str,
        description: str,
        owner: str,
        due: date,
        created_by: str,
    ) -> tuple[list[Hire], list[Hire]]:
        """HR assigns one task to several new hires; each gets their own copy.

        Anyone who already has a task with the same title is skipped, so assigning
        twice doesn't create duplicates. Returns (assigned, skipped).
        """
        assigned, skipped = [], []
        for hire_id in hire_ids:
            hire = self.hires[hire_id]
            if any(t.title.lower() == title.lower() for t in self.tasks_for(hire_id)):
                skipped.append(hire)
                continue
            self.add_task(hire_id, title, description, owner, due, created_by)
            assigned.append(hire)
        return assigned, skipped

    def delete_task(self, task_id: int) -> None:
        del self.tasks[task_id]
        self.save()

    def set_done(self, task_id: int, done: bool, party: str | None = None) -> Task:
        """Check a task off (or undo). For dual tasks, record just this party's confirmation."""
        task = self.tasks[task_id]
        if task.dual:
            if party not in DUAL_PARTIES:
                raise ValueError(f"dual task needs a party, got {party!r}")
            if done:
                task.confirmed[party] = self.today
            else:
                task.confirmed.pop(party, None)
            both = len(task.confirmed) == len(DUAL_PARTIES)
            task.done_on = max(task.confirmed.values()) if both else None
        else:
            task.done_on = self.today if done else None
        self.save()
        return task

    def is_overdue(self, task: Task) -> bool:
        return not task.done and task.due < self.today

    def progress(self, hire_id: str) -> Progress:
        tasks = self.tasks_for(hire_id)
        return Progress(
            done=sum(t.done for t in tasks),
            total=len(tasks),
            overdue=[t for t in tasks if self.is_overdue(t)],
        )

    def status(self, hire: Hire) -> str:
        p = self.progress(hire.person_id)
        if p.total and p.done == p.total:
            return "complete"
        if p.overdue:
            return "attention"
        if hire.start_date > self.today:
            return "preboarding"
        return "on_track"

    def focus(self, hire_id: str) -> tuple[list[Task], list[Task]]:
        """Split the new hire's open tasks into 'focus now' (max 3) and 'everything else'.

        Focus = overdue or due within the next few days, earliest first. If nothing is
        that close, show just the single next task so the screen is never blank while
        work remains.
        """
        open_tasks = [
            t for t in self.tasks_for(hire_id, party="new_hire") if not t.done_by("new_hire")
        ]
        horizon = self.today + timedelta(days=FOCUS_WINDOW_DAYS)
        focus = [t for t in open_tasks if t.due <= horizon][:FOCUS_LIMIT]
        if not focus and open_tasks:
            focus = open_tasks[:1]
        rest = [t for t in open_tasks if t not in focus]
        return focus, rest

    def save(self) -> None:
        if not self.path:
            return
        data = {
            "people": [asdict(p) for p in self.people.values()],
            "hires": [
                {**asdict(h), "start_date": h.start_date.isoformat()} for h in self.hires.values()
            ],
            "tasks": [
                {
                    **asdict(t),
                    "due": t.due.isoformat(),
                    "done_on": t.done_on.isoformat() if t.done_on else None,
                    "confirmed": {k: v.isoformat() for k, v in t.confirmed.items()},
                }
                for t in self.tasks.values()
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    @classmethod
    def load(cls, path: Path, today: date) -> "Store":
        data = json.loads(path.read_text())
        store = cls(today, path)
        for p in data["people"]:
            if p["role"] == "manager" and not p.get("department"):
                raise KeyError("department")  # saved before managers had departments
            store.people[p["id"]] = Person(**p)
        for h in data["hires"]:
            store.hires[h["person_id"]] = Hire(
                **{**h, "start_date": date.fromisoformat(h["start_date"])}
            )
        for t in data["tasks"]:
            done_on = date.fromisoformat(t["done_on"]) if t["done_on"] else None
            confirmed = {k: date.fromisoformat(v) for k, v in t.get("confirmed", {}).items()}
            store.tasks[t["id"]] = Task(
                **{
                    **t,
                    "due": date.fromisoformat(t["due"]),
                    "done_on": done_on,
                    "confirmed": confirmed,
                }
            )
        store._next_task_id = max(store.tasks, default=0) + 1
        return store

    def day_label(self, hire: Hire) -> str:
        delta = (hire.start_date - self.today).days
        if delta > 1:
            return f"Starts in {delta} days"
        if delta == 1:
            return "Starts tomorrow"
        return f"Day {-delta + 1}"


# --- validation -------------------------------------------------------------

MAX_NAME_LEN = 80
MAX_PAST_START_DAYS = 14


def validate_new_hire(form: dict, store: Store) -> tuple[dict, dict[str, str]]:
    """Return (clean data, errors by field). Errors are user-facing messages."""
    errors: dict[str, str] = {}
    name = " ".join((form.get("name") or "").split())
    title = " ".join((form.get("title") or "").split())
    department = form.get("department") or ""
    manager_id = form.get("manager_id") or ""
    start_raw = (form.get("start_date") or "").strip()

    if not name:
        errors["name"] = "Enter the new hire's name."
    elif len(name) > MAX_NAME_LEN:
        errors["name"] = f"Name must be {MAX_NAME_LEN} characters or fewer."

    if len(title) > MAX_NAME_LEN:
        errors["title"] = f"Job title must be {MAX_NAME_LEN} characters or fewer."

    if department not in DEPARTMENTS:
        errors["department"] = "Choose a department."

    manager = store.people.get(manager_id)
    if not manager or manager.role != "manager":
        errors["manager_id"] = "Choose a manager."
    elif department in DEPARTMENTS and manager.department != department:
        errors["manager_id"] = (
            f"{manager.name} manages {manager.department}. Choose a {department} manager."
        )

    start_date = None
    try:
        start_date = date.fromisoformat(start_raw)
    except ValueError:
        errors["start_date"] = "Enter a valid start date."
    if start_date:
        if start_date < store.today - timedelta(days=MAX_PAST_START_DAYS):
            errors["start_date"] = (
                f"Start date is more than {MAX_PAST_START_DAYS} days ago. "
                "Onboarding plans are for upcoming or recent hires."
            )
        elif start_date > store.today + timedelta(days=365):
            errors["start_date"] = "Start date must be within the next year."

    if not errors and any(
        h.name.lower() == name.lower() and h.start_date == start_date for h in store.hires.values()
    ):
        errors["name"] = f"{name} already has an onboarding plan starting on that date."

    data = dict(
        name=name,
        title=title,
        department=department,
        manager_id=manager_id,
        start_date=start_date,
    )
    return data, errors


OWNERS = {
    "new_hire": "New hire",
    "manager": "Manager",
    "both": "New hire + manager",
    "hr": "HR",
}
MAX_TASK_TITLE_LEN = 100
MAX_TASK_DESCRIPTION_LEN = 300


def validate_new_task(form: dict, store: Store) -> tuple[dict, dict[str, str]]:
    """Validate a task added by a manager or HR. Return (clean data, errors by field)."""
    errors: dict[str, str] = {}
    title = " ".join((form.get("title") or "").split())
    description = (form.get("description") or "").strip()
    owner = form.get("owner") or ""
    due_raw = (form.get("due") or "").strip()

    if not title:
        errors["title"] = "Enter what needs to be done."
    elif len(title) > MAX_TASK_TITLE_LEN:
        errors["title"] = f"Keep the title to {MAX_TASK_TITLE_LEN} characters or fewer."

    if len(description) > MAX_TASK_DESCRIPTION_LEN:
        errors["description"] = (
            f"Keep the details to {MAX_TASK_DESCRIPTION_LEN} characters or fewer."
        )

    if owner not in OWNERS:
        errors["owner"] = "Choose who does this task."

    due = None
    try:
        due = date.fromisoformat(due_raw)
    except ValueError:
        errors["due"] = "Enter a valid due date."
    if due:
        if due < store.today:
            errors["due"] = "Due date can't be in the past."
        elif due > store.today + timedelta(days=365):
            errors["due"] = "Due date must be within the next year."

    data = dict(title=title, description=description, owner=owner, due=due)
    return data, errors


# --- seed data --------------------------------------------------------------


def open_store(today: date, path: Path | None) -> Store:
    """Load saved state if there is any; otherwise start from fresh sample data."""
    if path and path.exists():
        try:
            return Store.load(path, today)
        except (ValueError, KeyError, TypeError):
            pass  # corrupt or old-format file: fall back to fresh sample data
    return seed(today, path)


def seed(today: date, path: Path | None = None) -> Store:
    store = Store(today)
    for p in [
        Person("sarah", "Sarah Kim", "hr", "HR Manager"),
        Person("david", "David Chen", "manager", "Engineering Manager", "Engineering"),
        Person("priya", "Priya Nair", "manager", "Sales Manager", "Sales"),
        Person("lena", "Lena Morales", "manager", "Customer Support Manager", "Customer Support"),
        Person("omar", "Omar Haddad", "manager", "Operations Manager", "Operations"),
    ]:
        store.add_person(p)

    emily = store.add_hire(
        "Emily Park", "Software Engineer", "Engineering", "david", today - timedelta(days=3)
    )
    jordan = store.add_hire(
        "Jordan Reyes", "Data Engineer", "Engineering", "david", today - timedelta(days=18)
    )
    marcus = store.add_hire(
        "Marcus Bell", "Account Executive", "Sales", "priya", today + timedelta(days=6)
    )

    # Everything due before today is done, except a few realistic slips.
    slipped = {
        (emily.person_id, "Set up your local dev environment"),
        (marcus.person_id, "Order laptop and equipment"),
    }
    # Emily confirmed her first-day 1:1 happened; David hasn't yet.
    half_confirmed = {(emily.person_id, "First-day 1:1 with your manager"): "new_hire"}
    for hire in (emily, jordan, marcus):
        for task in store.tasks_for(hire.person_id):
            key = (hire.person_id, task.title)
            if task.due >= today or key in slipped:
                continue
            if key in half_confirmed:
                task.confirmed = {half_confirmed[key]: task.due}
                continue
            task.done_on = task.due
            if task.dual:
                task.confirmed = {party: task.due for party in DUAL_PARTIES}
    # A one-off task David added for Emily on top of the Engineering template.
    store.add_task(
        emily.person_id,
        "Pair with Jordan on the data pipeline",
        "Jordan joined last month and knows the ingestion jobs well.",
        "new_hire",
        today + timedelta(days=2),
        created_by="david",
    )
    store.path = path
    store.save()
    return store
