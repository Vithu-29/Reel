from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    accounts = current_app.extensions["accounts"]
    account = accounts.get()
    if account and session.get("account_version") == account["version"]:
        return redirect(url_for("pages.index"))
    error = None
    status = 200
    if request.method == "POST":
        limiter = current_app.extensions["login_limiter"]
        key = request.remote_addr or "local"
        if not limiter.allow(key):
            error, status = "Too many attempts. Please try again in five minutes.", 429
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            result = (
                accounts.verify(username[:64], password[:256]) if len(password) <= 256 else None
            )
            if result and len(username) <= 64:
                limiter.reset(key)
                session.clear()
                session.permanent = True
                session["username"] = result["username"]
                session["account_version"] = result["version"]
                return redirect(url_for("pages.index"))
            error, status = "Incorrect username or password.", 401
    return render_template("login.html", error=error, configured=bool(account)), status


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
