"""Onboarding plan templates.

A plan = the company-wide base tasks + the tasks for the hire's department.
offset_days is relative to the start date (negative = before day 1).
owner is who has to do it: the new hire, their manager, or HR. "both" is a joint task
(a 1:1, agreeing on goals) that only counts as done once both people confirm it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskTemplate:
    title: str
    description: str
    offset_days: int
    owner: str  # "new_hire" | "manager" | "hr" | "both"


BASE_TASKS = [
    TaskTemplate(
        "Sign your offer and employment agreement",
        "Check your email for the e-signature link from HR.",
        -10,
        "new_hire",
    ),
    TaskTemplate(
        "Complete I-9 and tax forms",
        "Bring your ID documents on day 1 so HR can verify your I-9.",
        -5,
        "new_hire",
    ),
    TaskTemplate(
        "Set up direct deposit",
        "Add your bank details in the payroll portal so your first paycheck isn't delayed.",
        -3,
        "new_hire",
    ),
    TaskTemplate(
        "Order laptop and equipment",
        "Submit the IT hardware request so it arrives before day 1.",
        -7,
        "manager",
    ),
    TaskTemplate(
        "Assign an onboarding buddy",
        "Pick a teammate to answer day-to-day questions during the first month.",
        -3,
        "manager",
    ),
    TaskTemplate(
        "Prepare badge and welcome kit",
        "Badge photo, building access and the welcome swag box.",
        -2,
        "hr",
    ),
    TaskTemplate(
        "Read the first-day guide",
        "Where to go, when to arrive, parking, and who will meet you.",
        -1,
        "new_hire",
    ),
    TaskTemplate(
        "Attend the welcome session with HR",
        "9:30am in the main conference room (or the Zoom link in your calendar).",
        0,
        "new_hire",
    ),
    TaskTemplate(
        "First-day 1:1 with your manager",
        "Walk through the team, expectations for week 1, and this plan. You both confirm it.",
        0,
        "both",
    ),
    TaskTemplate(
        "Set up email, Slack and MFA",
        "IT will hand you your laptop; follow the sign-in card in the box.",
        1,
        "new_hire",
    ),
    TaskTemplate(
        "Complete security awareness training",
        "About 30 minutes in the learning portal.",
        2,
        "new_hire",
    ),
    TaskTemplate(
        "Read and acknowledge the employee handbook",
        "Covers time off, expenses and code of conduct.",
        6,
        "new_hire",
    ),
    TaskTemplate(
        "Enroll in benefits",
        "You have 30 days from your start date; enrolling early means coverage starts sooner.",
        13,
        "new_hire",
    ),
    TaskTemplate(
        "Set 30-day goals together",
        "Agree on 2-3 concrete goals for the first month. You both confirm them.",
        10,
        "both",
    ),
    TaskTemplate(
        "Complete harassment prevention training",
        "Required within your first month. About 1 hour.",
        20,
        "new_hire",
    ),
    TaskTemplate(
        "30-day check-in",
        "Review goals and share feedback on onboarding. You both confirm it.",
        29,
        "both",
    ),
]

DEPARTMENT_TASKS = {
    "Engineering": [
        TaskTemplate(
            "Request GitHub, AWS and VPN access",
            "File the access request so accounts are ready on day 1.",
            -2,
            "manager",
        ),
        TaskTemplate(
            "Set up your local dev environment",
            "Follow the 'Getting started' page in the engineering wiki.",
            1,
            "new_hire",
        ),
        TaskTemplate(
            "Read the architecture overview",
            "Start with the system diagram, then the service you'll work on.",
            3,
            "new_hire",
        ),
        TaskTemplate(
            "Ship your first small pull request",
            "Your buddy has a starter ticket ready for you.",
            5,
            "new_hire",
        ),
        TaskTemplate(
            "Shadow an on-call shift",
            "Sit with the on-call engineer for one shift.",
            12,
            "new_hire",
        ),
        TaskTemplate(
            "Complete secure coding training",
            "Required before you get production access.",
            20,
            "new_hire",
        ),
    ],
    "Sales": [
        TaskTemplate(
            "Request CRM and call-recording licenses",
            "Salesforce and Gong seats so accounts are ready on day 1.",
            -2,
            "manager",
        ),
        TaskTemplate(
            "Complete CRM basics training",
            "How we log leads, opportunities and activities.",
            1,
            "new_hire",
        ),
        TaskTemplate(
            "Learn the product pitch and demo script",
            "Watch the recorded demo, then practice with your buddy.",
            3,
            "new_hire",
        ),
        TaskTemplate(
            "Shadow three customer calls",
            "Ask your buddy to add you to upcoming calls.",
            8,
            "new_hire",
        ),
        TaskTemplate(
            "Run a mock demo with your manager",
            "15-minute demo followed by feedback. You both confirm it.",
            15,
            "both",
        ),
        TaskTemplate(
            "Hand over first territory accounts",
            "Assign a starter book of accounts.",
            25,
            "manager",
        ),
    ],
    "Customer Support": [
        TaskTemplate(
            "Request Zendesk and knowledge base access",
            "So the help desk account is ready on day 1.",
            -2,
            "manager",
        ),
        TaskTemplate(
            "Complete help desk tool training",
            "Ticket statuses, macros and escalation paths.",
            1,
            "new_hire",
        ),
        TaskTemplate(
            "Read the top 20 help articles", "These answer most incoming tickets.", 3, "new_hire"
        ),
        TaskTemplate(
            "Shadow a senior agent for a full shift",
            "Listen in on calls and watch how tickets are triaged.",
            4,
            "new_hire",
        ),
        TaskTemplate(
            "Answer your first 10 tickets with review",
            "Your buddy reviews replies before they're sent.",
            9,
            "new_hire",
        ),
        TaskTemplate(
            "Join the escalation rotation",
            "Add them to the rotation once they're comfortable.",
            21,
            "manager",
        ),
    ],
}

# Departments without their own template still get a sensible plan.
GENERAL_TASKS = [
    TaskTemplate(
        "Request access to your team's tools",
        "Check with the team which systems the new hire needs.",
        -2,
        "manager",
    ),
    TaskTemplate(
        "Meet your team one-on-one", "Your buddy will set up short intros.", 4, "new_hire"
    ),
    TaskTemplate(
        "Learn your team's core processes",
        "Ask your manager for the team's key docs.",
        8,
        "new_hire",
    ),
]

TEMPLATED_DEPARTMENTS = list(DEPARTMENT_TASKS)
# Operations has no template of its own, so it shows the General fallback.
DEPARTMENTS = TEMPLATED_DEPARTMENTS + ["Operations"]


def plan_for(department: str) -> list[TaskTemplate]:
    return BASE_TASKS + DEPARTMENT_TASKS.get(department, GENERAL_TASKS)
