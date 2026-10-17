from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages import get_messages
from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment, pass_context


PATH_PARAMS = {
    "state_slug", "doc_id", "case_id", "milestone_id", "request_id",
    "consultation_id", "invoice_id", "enquiry_id", "draft_id", "payment_id", "slug", "user_id", "offering_id",
}


def url_for(endpoint, **kwargs):
    """Flask-style helper so ported templates keep working.

    Unknown kwargs become a query string; `static` maps to staticfiles.
    """
    if endpoint == "static":
        return static(kwargs["filename"])
    pattern_kwargs = {}
    query = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        (pattern_kwargs if key in PATH_PARAMS else query)[key] = value
    url = reverse(endpoint, kwargs=pattern_kwargs or None)
    return f"{url}?{urlencode(query)}" if query else url


@pass_context
def get_flashed_messages(context, with_categories=False):
    request = context.get("request")
    if request is None:
        return []
    tag_map = {"error": "error", "success": "success"}
    items = list(get_messages(request))
    if with_categories:
        return [(tag_map.get(m.level_tag, m.level_tag), str(m)) for m in items]
    return [str(m) for m in items]


def environment(**options):
    options.setdefault("autoescape", True)  # explicit: template variables are HTML-escaped by default
    env = Environment(**options)  # noqa: S701
    env.globals.update(
        url_for=url_for,
        url=url_for,
        static=lambda path: static(path),
        get_flashed_messages=get_flashed_messages,
    )
    return env
