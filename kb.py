from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from auth import role_required
from extensions import db
from models import URGENCIES, Article, ChatMessage, Ticket
import nlp

kb_bp = Blueprint("kb", __name__, url_prefix="/admin/kb")


def _clean_keywords(raw):
    seen = set()
    cleaned = []
    for part in raw.replace("\n", ",").split(","):
        word = " ".join(part.split())
        key = word.lower()
        if word and key not in seen:
            seen.add(key)
            cleaned.append(word)
    return ", ".join(cleaned)


def _read_form():
    """Returns (values, error)."""
    values = {
        "title": " ".join(request.form.get("title", "").split()),
        "category": " ".join(request.form.get("category", "").split()),
        "keywords": _clean_keywords(request.form.get("keywords", "")),
        "solution": request.form.get("solution", "").strip(),
        "default_urgency": request.form.get("default_urgency", "medium"),
        "is_published": request.form.get("is_published") == "on",
    }

    error = None
    if len(values["title"]) < 3 or len(values["title"]) > 200:
        error = "Title must be 3 to 200 characters."
    elif len(values["category"]) < 2 or len(values["category"]) > 80:
        error = "Category must be 2 to 80 characters."
    elif not values["keywords"]:
        error = "Add at least one keyword. The chatbot finds articles through them."
    elif len(values["solution"]) < 10:
        error = "The solution needs at least 10 characters."
    elif len(values["solution"]) > 5000:
        error = "The solution is too long (5000 characters maximum)."
    elif values["default_urgency"] not in URGENCIES:
        error = "Please choose a valid urgency."
    return values, error


def _title_taken(title, ignore_id=None):
    query = Article.query.filter(func.lower(Article.title) == title.lower())
    if ignore_id is not None:
        query = query.filter(Article.id != ignore_id)
    return query.first() is not None


def _categories():
    rows = db.session.query(Article.category).distinct().order_by(Article.category).all()
    return [r[0] for r in rows]


def _usage(article_id):
    tickets = Ticket.query.filter_by(article_id=article_id).count()
    chats = ChatMessage.query.filter_by(matched_article_id=article_id).count()
    return tickets, chats


@kb_bp.route("")
@role_required("admin")
def article_list():
    articles = Article.query.order_by(Article.category, Article.title).all()

    ticket_counts = dict(
        db.session.query(Ticket.article_id, func.count(Ticket.id))
        .filter(Ticket.article_id.isnot(None))
        .group_by(Ticket.article_id)
        .all()
    )
    chat_counts = dict(
        db.session.query(ChatMessage.matched_article_id, func.count(ChatMessage.id))
        .filter(ChatMessage.matched_article_id.isnot(None))
        .group_by(ChatMessage.matched_article_id)
        .all()
    )
    rows = [(a, ticket_counts.get(a.id, 0), chat_counts.get(a.id, 0)) for a in articles]

    # Matcher test box
    q = request.args.get("q", "").strip()[:500]
    test = None
    if q:
        published = [a.to_dict() for a in articles if a.is_published]
        results = nlp.find_matches(q, published)[:3]
        test = {
            "query": q,
            "smalltalk": nlp.detect_smalltalk(q),
            "threshold": round(nlp.MATCH_THRESHOLD * 100),
            "results": [
                {
                    "title": art["title"],
                    "confidence": round(conf * 100),
                    "passes": conf >= nlp.MATCH_THRESHOLD,
                }
                for art, _score, conf in results
            ],
        }

    return render_template("kb_list.html", rows=rows, test=test, q=q)


@kb_bp.route("/new", methods=["GET", "POST"])
@role_required("admin")
def article_new():
    if request.method == "POST":
        values, error = _read_form()
        if not error and _title_taken(values["title"]):
            error = "An article with that title already exists."
        if error:
            flash(error, "error")
            return render_template(
                "kb_form.html", form=values, is_new=True,
                urgencies=URGENCIES, categories=_categories(),
            ), 400

        article = Article(**values)
        db.session.add(article)
        db.session.commit()
        flash(f'Article "{article.title}" created.', "success")
        return redirect(url_for("kb.article_list"))

    blank = {
        "title": "", "category": "", "keywords": "", "solution": "",
        "default_urgency": "medium", "is_published": True,
    }
    return render_template(
        "kb_form.html", form=blank, is_new=True,
        urgencies=URGENCIES, categories=_categories(),
    )


@kb_bp.route("/<int:article_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def article_edit(article_id):
    article = db.session.get(Article, article_id)
    if article is None:
        abort(404)

    if request.method == "POST":
        values, error = _read_form()
        if not error and _title_taken(values["title"], ignore_id=article.id):
            error = "Another article already has that title."
        if error:
            flash(error, "error")
            return render_template(
                "kb_form.html", form=values, is_new=False, article=article,
                urgencies=URGENCIES, categories=_categories(),
            ), 400

        for key, value in values.items():
            setattr(article, key, value)
        db.session.commit()
        flash(f'Article "{article.title}" saved.', "success")
        return redirect(url_for("kb.article_list"))

    return render_template(
        "kb_form.html", form=article.to_dict(), is_new=False, article=article,
        urgencies=URGENCIES, categories=_categories(),
    )


@kb_bp.route("/<int:article_id>/toggle", methods=["POST"])
@role_required("admin")
def article_toggle(article_id):
    article = db.session.get(Article, article_id)
    if article is None:
        abort(404)
    article.is_published = not article.is_published
    db.session.commit()
    state = "published" if article.is_published else "unpublished (hidden from the chatbot)"
    flash(f'"{article.title}" {state}.', "success")
    return redirect(url_for("kb.article_list"))


@kb_bp.route("/<int:article_id>/delete", methods=["POST"])
@role_required("admin")
def article_delete(article_id):
    article = db.session.get(Article, article_id)
    if article is None:
        abort(404)

    tickets, chats = _usage(article.id)
    if tickets or chats:
        flash(
            f'"{article.title}" has been used by {tickets} ticket(s) and {chats} chat message(s), '
            "so it cannot be deleted. Unpublish it instead.",
            "error",
        )
        return redirect(url_for("kb.article_list"))

    title = article.title
    db.session.delete(article)
    db.session.commit()
    flash(f'Article "{title}" deleted.', "success")
    return redirect(url_for("kb.article_list"))