# New Employee Onboarding: BrightPath Prototype

**Scenario 1: New Employee Onboarding** (MangoApps Associate Product Manager, AI Builder take-home)

One place where a new hire at BrightPath Technologies sees what to do, and their manager sees how they're progressing. HR creates the plan in one step. It's built automatically from company-wide tasks plus the new hire's department tasks.

**Who it's for:** the new hire first (Emily), then their manager (David), then HR (Sarah).

## Run it

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
flask --app onboarding:create_app run --port 5050
```

Open http://localhost:5050 and pick a person from the **View as** menu. There are no real logins.

In VS Code, open the folder and press **F5** ("Run New Employee Onboarding"). The interpreter, Ruff formatting and pytest are already configured in `.vscode/`.

Run the tests:

```bash
pytest
```

## The workflow (end to end)

The steps below are in setup order, starting with HR creating the plan. The primary user is still the new hire; HR's part is a one-time setup.

1. **HR (Sarah) adds a new hire**: name, department, manager and start date (job title is optional). Only managers from the chosen department can be picked.
2. **The app builds the plan automatically**: company tasks plus that department's tasks. Due dates are calculated from the start date.
3. **The new hire sees "Focus on now"**: at most 3 tasks that are overdue or due in the next few days. Below that is the full plan as Trello-style columns: **Before day 1, Week 1, Weeks 2–4**. Later phases start collapsed. They check tasks off and the progress bar updates.
4. **The manager sees their new hires**: start date, % complete, and overdue tasks highlighted in red. They also see their own to-dos for each hire (order laptop, first-day 1:1…) for this week.
5. **Managers and HR add their own tasks**: on a new hire's page, **+ Add a task** adds something the template doesn't cover, such as "Pair with Jordan on the data pipeline". They choose who does it (new hire, manager or HR) and a due date, and the task appears in the right phase with an "Added by David" tag. HR has its own to-dos list too, for example "Prepare badge and welcome kit".
6. **HR assigns a task to several people at once**: on the HR overview, **Assign a task** lets Sarah tick one or more new hires (or "Select all") and give them all the same task, for example "Attend the benefits webinar". Each person gets their own copy in their plan.
7. **Joint tasks need both people to confirm**: tasks like the first-day 1:1 or setting 30-day goals show two sign-off tags (for example "✓ Emily ○ David"). Each person clicks separately to confirm their side. The card says "Waiting for David" until the second confirmation, and only then does the task count as done.

### Sample data (dates are relative to today)

| Person | Role | What it shows |
|---|---|---|
| Sarah Kim | HR Manager | Everyone's progress, plus adding a new hire |
| David Chen | Engineering Manager | Two hires; Emily's first-day 1:1 is waiting for his confirmation |
| Priya Nair | Sales Manager | A hire who hasn't started yet, whose laptop order is already late |
| Lena Morales | Customer Support Manager | Empty state (no hires yet) |
| Omar Haddad | Operations Manager | Empty state; Operations hires get the General plan |
| Emily Park | Software Engineer, day 4 | Focus list with one overdue task, a task David added for her, and a 1:1 she confirmed but David hasn't |
| Jordan Reyes | Data Engineer, day 19 | Nearly finished |
| Marcus Bell | Account Executive, starts in 6 days | Pre-boarding |

Checked-off tasks are saved to `data/state.json`. **Reset demo data** in the footer restores the sample data.

## How I handled the two people who disagree

- **David (Engineering Manager):** "Every department has different onboarding needs." → Each department has its own task template on top of the shared company tasks. Engineering gets GitHub/AWS access, a dev environment and a first PR. Sales gets CRM, demo practice and call shadowing. Customer Support gets help desk training and ticket shadowing.
- **Emily (New Employee):** "I don't want to … see 40 things … I just want to know what I should focus on first." → Her screen leads with **3 tasks at most**. Everything else is grouped by phase, and future phases are collapsed.

They don't really conflict. David is talking about *what's in* the plan, and Emily is talking about *how much of it she sees at once*. So the plan can be complete and detailed while the screen stays short. Managers get the same treatment: their to-do list only shows this week.

## Assumptions

- **Departments:** Engineering, Sales and Customer Support have their own templates. Operations has no template of its own and gets a short **General** template. That shows how any department without a template could still be onboarded.
- **Every new hire has a manager when HR creates their plan.** The form requires one, because so much of the plan (the 1:1s, equipment, goals) depends on the manager. What happens without one is a question for Sarah, below.
- **A manager can only onboard people into their own department.** Each manager belongs to one department. When HR picks a department, the Manager list shows only that department's managers (and auto-selects one if there's only one). The server rejects a mismatch too, for example a Sales hire with the Engineering manager: *"David Chen manages Engineering. Choose a Sales manager."* I assumed BrightPath's reporting lines follow departments; cross-department reporting (for example, a Sales Engineer reporting into Engineering) is out of scope for now.
- **Phases** are calendar days from the start date: Before day 1 (< 0), Week 1 (days 0–6), Weeks 2–4 (days 7–29). Onboarding ends after 30 days.
- **New hires can use the app before day 1** (after they accept the offer), since Sarah said some tasks must happen before the first day.
- **Managers and HR want to add their own tasks.** Templates cover what every hire in a department needs, but managers know things specific to one person (pair with a teammate, meet a key customer), and HR has its own steps (badge, welcome kit). So both can add one-off tasks to a hire's plan, and each task is tagged with who added it.
  - A manager can add tasks only for their own hires. HR can add tasks for anyone.
  - An added task can be removed by whoever added it, or by HR. Template tasks can't be removed, so nobody accidentally deletes a required step like the I-9.
  - Due dates for added tasks can't be in the past. The phase (Before day 1 / Week 1 / Weeks 2–4) is worked out from the due date.
  - Added tasks are for one person only. They don't change the department template.
- **HR wants to assign the same task to several new hires at once** (a benefits webinar, a culture survey), without opening each person's plan. Each person gets their own copy, so one person checking it off doesn't affect anyone else.
  - Only HR can assign to several people. Managers add tasks one hire at a time, and only for their own hires.
  - There's one due date for everyone, and each copy lands in the right phase for that person's start date. For example, the same date can be "Before day 1" for one hire and "Weeks 2–4" for another.
  - If someone already has a task with the same name, they're skipped and HR is told who, so assigning twice doesn't create duplicates.
  - "Manager" as the owner means each person's own manager.
- **Each task has an owner, and only the owner can complete it.** The owner is the new hire, their manager, or HR. A manager can't mark a new hire's task as done for them, and a new hire can't mark a manager's task done. New hires see everyone else's tasks read-only under "Being handled for you", so they know their laptop and badge are on the way.
- **Joint tasks need both the new hire and the manager to confirm (dual sign-off).** Some tasks happen between two people: the first-day 1:1, setting 30-day goals, the 30-day check-in, and the Sales mock demo. If either person could tick these off alone, a manager could mark a 1:1 "done" that never happened, or the other way round. So each person confirms their own side separately, and the task only counts toward progress once both have.
  - Until both confirm, the card shows who has confirmed and who it's waiting on. The task stays on the other person's to-do list and still shows as overdue if it's late.
  - Each person can only undo their own confirmation. Undoing one side reopens the task.
  - HR and other managers can see joint tasks but can't confirm them.
  - When adding a task, managers and HR can choose "New hire + manager" to make it a joint task.
- **Who can do what:** a new hire can check off their own tasks and confirm their side of joint tasks. A manager can only see their own hires, check off manager tasks, and confirm their side of joint tasks. HR sees everyone and checks off HR tasks.
- **"Focus on now"** means overdue or due within 3 days, max 3 tasks. If nothing is that close, it shows the single next task, so the screen is never empty while work remains.
- **Start dates** may be up to 14 days in the past (HR entered someone late) and up to a year ahead. A second plan with the same name and start date is rejected as a likely duplicate.
- **"Done" is self-reported.** There are no approvals or proof (for example, of I-9 verification).

## What I left out (and why)

- **Editing plans and templates in the app.** Templates live in `onboarding/templates_data.py`. A template editor for HR and managers is the natural next step, but the core loop came first.
- **Editing tasks after they're added.** For now, you remove the task and add it again.
- **Saving an added task back to the department template**, for example "add this to every Engineering plan".
- **Notifications and reminders** (email or Slack when tasks are due or overdue).
- **Real logins, a real database, an HR system integration.** Out of scope for a prototype; the role switcher stands in for logins.
- **Tasks owned by IT or a buddy.** Only new hire, manager and HR tasks for now.
- **Role-based templates within a department** (for example, a Data Engineer vs. a Frontend Engineer). Sarah said "role or department", and I started with department.

## Questions I'd ask Sarah next

Some things I assumed wouldn't come up, or felt out of scope for a first version:

1. What happens if a new hire doesn't have a manager yet? Right now the app requires one.
2. How are managers assigned? Does HR decide, or does it come from an HR system?
3. How private should tasks be? For example, should a manager be able to add a task that HR can't see? Right now HR can see every plan.
4. Which tasks really need both people to confirm? I picked the 1:1s, goal setting and the mock demo. Should HR sign off on anything (for example, the I-9)?
5. Who owns the templates: HR, or each department's manager? Who approves changes?
6. Should anyone besides the manager see progress, for example IT for equipment and accounts?
7. What should happen when something is overdue: a nudge to the new hire, the manager, or HR?
8. Does onboarding really end at 30 days, or do some roles need 60–90?
9. Which HR system holds new hires today? Plans could be created automatically from it.
10. Does anyone report to a manager outside their department? If so, we'd need to allow it with a warning.

## Testing

`pytest` runs 103 tests covering plan generation (department and General fallback), due dates, focus logic (cap, overdue first, empty and all-done states), form validation (blank name, unknown department, a manager from another department, bad or far-off dates, duplicates), adding and removing tasks (who may add, remove or check off what; template tasks can't be removed), HR assigning a task to several people (own copies, skipping duplicates, errors), dual sign-off (done only after both confirm, in either order; undoing one side reopens it; HR and other managers can't confirm), permissions (no checking off or viewing other people's tasks), JSON save and reload (including a corrupt file), and the manager empty state.

## Project layout

```
onboarding/
  __init__.py         Flask app and routes
  store.py            data model, plan generation, focus logic, validation, sample data
  templates_data.py   company and department task templates
  templates/          HTML pages (Jinja)
  static/style.css
tests/
.vscode/              interpreter, debug (F5), pytest and Ruff settings
```
