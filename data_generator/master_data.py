"""Shared reference/master data, seeded RNG instances, and small generation utilities."""

import random
from datetime import timedelta

import numpy as np
from dateutil.relativedelta import relativedelta
from faker import Faker

from config.settings import RANDOM_SEED, REFERENCE_DATE

RNG = random.Random(RANDOM_SEED)
NP_RNG = np.random.default_rng(RANDOM_SEED)
FAKE = Faker()
Faker.seed(RANDOM_SEED)

HISTORY_START = REFERENCE_DATE - relativedelta(years=3)
RECENT_WINDOW_DAYS = 365

REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East & Africa"]
REGION_WEIGHTS = [0.35, 0.28, 0.20, 0.10, 0.07]

REGION_COUNTRIES = {
    "North America": ["United States", "Canada", "Mexico"],
    "Europe": ["United Kingdom", "Germany", "France", "Netherlands", "Spain", "Ireland"],
    "Asia Pacific": ["Australia", "Singapore", "Japan", "India", "South Korea"],
    "Latin America": ["Brazil", "Argentina", "Chile", "Colombia"],
    "Middle East & Africa": ["United Arab Emirates", "South Africa", "Saudi Arabia", "Nigeria"],
}

INDUSTRIES = [
    "Financial Services", "Healthcare", "Manufacturing", "Retail & E-commerce",
    "Technology", "Telecommunications", "Energy & Utilities", "Media & Entertainment",
    "Education", "Logistics & Transportation", "Professional Services", "Public Sector",
]

SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Startup"]
SEGMENT_WEIGHTS = [0.15, 0.30, 0.40, 0.15]
SEGMENT_REVENUE_MULTIPLIER = {"Enterprise": 3.2, "Mid-Market": 1.6, "SMB": 1.0, "Startup": 0.55}

REGION_REVENUE_MULTIPLIER = {
    "North America": 1.15,
    "Europe": 1.05,
    "Asia Pacific": 0.95,
    "Latin America": 0.75,
    "Middle East & Africa": 0.85,
}

DEPARTMENTS = [
    "Sales", "Account Management", "Project Management", "Customer Support",
    "Engineering", "Marketing", "Finance", "Human Resources", "Executive",
]
DEPARTMENT_WEIGHTS = [0.15, 0.08, 0.08, 0.20, 0.25, 0.08, 0.06, 0.05, 0.05]
CUSTOMER_FACING_DEPARTMENTS = ["Sales", "Account Management", "Project Management", "Customer Support"]

DEPARTMENT_TITLES = {
    "Sales": ["Sales Representative", "Senior Sales Representative", "Sales Manager"],
    "Account Management": ["Account Manager", "Senior Account Manager"],
    "Project Management": ["Project Manager", "Senior Project Manager"],
    "Customer Support": ["Support Agent", "Senior Support Agent", "Support Team Lead"],
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Engineering Manager"],
    "Marketing": ["Marketing Specialist", "Marketing Manager"],
    "Finance": ["Financial Analyst", "Finance Manager"],
    "Human Resources": ["HR Specialist", "HR Manager"],
    "Executive": ["Chief Executive Officer", "Vice President", "Director"],
}

LEAD_SOURCES = [
    "Website", "Referral", "Cold Outreach", "Trade Show",
    "Partner Network", "Social Media", "Email Campaign", "Webinar",
]
LEAD_STATUSES = ["New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost"]

DEAL_STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
OPEN_DEAL_STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation"]
CLOSED_DEAL_STAGES = ["Closed Won", "Closed Lost"]

PRODUCTS = [
    "NEXORA Analytics Cloud", "NEXORA CRM Suite", "NEXORA Data Warehouse",
    "NEXORA Insights API", "NEXORA Managed Services",
]

SUBSCRIPTION_PLANS = ["Basic", "Standard", "Premium", "Enterprise"]
PLAN_BASE_MRR = {"Basic": 400, "Standard": 1200, "Premium": 3500, "Enterprise": 9000}
SEGMENT_PLAN_WEIGHTS = {
    "Enterprise": [0.05, 0.15, 0.35, 0.45],
    "Mid-Market": [0.10, 0.40, 0.35, 0.15],
    "SMB": [0.45, 0.40, 0.13, 0.02],
    "Startup": [0.55, 0.35, 0.09, 0.01],
}
SUBSCRIPTION_STATUSES = ["Active", "Active", "Active", "Cancelled", "Expired", "Paused"]
BILLING_CYCLES = ["Monthly", "Annual"]

PROJECT_TYPES = [
    "Implementation", "Data Migration", "Custom Integration",
    "Analytics Rollout", "Platform Upgrade", "Managed Services Engagement",
]
PROJECT_STATUSES = ["Planned", "In Progress", "Completed", "On Hold", "Delayed", "Cancelled"]

SUPPORT_CATEGORIES = [
    "Billing", "Technical Issue", "Onboarding", "Feature Request",
    "Bug Report", "Account Management", "General Inquiry",
]
SUPPORT_PRIORITIES = ["Low", "Medium", "High", "Critical"]
SUPPORT_CHANNELS = ["Email", "Phone", "Live Chat", "Customer Portal"]
SUPPORT_STATUSES = ["Open", "In Progress", "Resolved", "Closed", "Escalated"]

ACTIVITY_TYPES = [
    "Login", "Feature Usage", "Report Generated", "API Call",
    "Dashboard View", "Data Export", "Training Session", "Support Chat",
]

PAYMENT_METHODS = ["Credit Card", "Bank Transfer", "ACH", "Wire Transfer", "Check"]
INVOICE_STATUSES = ["Paid", "Unpaid", "Overdue", "Partially Paid", "Cancelled"]


def make_id(prefix, number, width=6):
    return f"{prefix}{number:0{width}d}"


def weighted_choice(rng, options, weights):
    return rng.choices(options, weights=weights, k=1)[0]


def random_date(rng, start, end):
    if end <= start:
        return start
    delta_days = (end - start).days
    return start + timedelta(days=rng.randint(0, delta_days))


def seasonality_multiplier(month):
    """Enterprise software spend skews toward calendar Q4 and fiscal year-end budget flush."""
    multipliers = {
        1: 0.95, 2: 0.90, 3: 1.05, 4: 0.95, 5: 0.95, 6: 1.05,
        7: 0.85, 8: 0.85, 9: 1.05, 10: 1.10, 11: 1.15, 12: 1.25,
    }
    return multipliers[month]
