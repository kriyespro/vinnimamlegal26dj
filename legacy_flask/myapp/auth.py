"""Auth helpers for LexAssist portal."""
from __future__ import annotations

from functools import wraps

from flask import flash, redirect, session, url_for

from db import get_user_by_id


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    user = get_user_by_id(uid)
    if not user or not user["active"]:
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please sign in to access the portal.", "error")
            return redirect(url_for("portal"))
        if not session.get("policy_accepted"):
            flash("You must accept the Portal Usage Policy.", "error")
            return redirect(url_for("portal"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user["role"] not in roles:
                flash("You do not have permission for that action.", "error")
                return redirect(url_for("portal_dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator
