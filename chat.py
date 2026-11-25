from flask import Blueprint, g, jsonify, render_template, request

from auth import login_required
from extensions import db
from models import Article, ChatMessage
import nlp

chat_bp = Blueprint("chat", __name__)

MAX_MESSAGE_LENGTH = 500

SMALLTALK_REPLIES = {
    "greeting": "Hello! I'm the Auraflow assistant. Tell me what's going wrong, for example \"my VPN is not connecting\".",
    "thanks": "You're welcome! Message me any time if something else breaks.",
    "bye": "Goodbye! I'm here whenever you need IT help.",
}


def _save(sender, text, article_id=None, confidence=None):
    db.session.add(
        ChatMessage(
            user_id=g.user.id,
            sender=sender,
            message=text,
            matched_article_id=article_id,
            confidence=confidence,
        )
    )


@chat_bp.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html")


@chat_bp.route("/api/chat/history")
@login_required
def chat_history():
    rows = (
        ChatMessage.query.filter_by(user_id=g.user.id)
        .order_by(ChatMessage.id.desc())
        .limit(40)
        .all()
    )
    rows.reverse()
    return jsonify(messages=[{"sender": r.sender, "message": r.message} for r in rows])


@chat_bp.route("/api/chat", methods=["POST"])
@login_required
def chat_send():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify(error="Please type a message."), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify(error=f"Please keep messages under {MAX_MESSAGE_LENGTH} characters."), 400

    _save("user", message)

    # Greetings, thanks, goodbye
    intent = nlp.detect_smalltalk(message)
    if intent:
        reply = SMALLTALK_REPLIES[intent]
        _save("bot", reply)
        db.session.commit()
        return jsonify(reply=reply, matched=False, article=None, suggestions=[])

    articles = [a.to_dict() for a in Article.query.filter_by(is_published=True).all()]
    results = nlp.find_matches(message, articles)

    if results and results[0][2] >= nlp.MATCH_THRESHOLD:
        best, _score, confidence = results[0]
        reply = f"This looks like: {best['title']}. Here is what to try:"

        suggestions = [
            {"id": a["id"], "title": a["title"]}
            for a, _s, c in results[1:3]
            if c >= nlp.ALT_MIN_CONFIDENCE and c >= confidence * nlp.ALT_MIN_RATIO
        ]

        _save("bot", f"{reply}\n\n{best['solution']}", best["id"], confidence)
        db.session.commit()
        return jsonify(
            reply=reply,
            matched=True,
            confidence=round(confidence * 100),
            article={
                "id": best["id"],
                "title": best["title"],
                "category": best["category"],
                "solution": best["solution"],
            },
            suggestions=suggestions,
        )

    # No confident match: offer the closest topics, or the first few
    if results and results[0][1] > 0:
        pool = [a for a, _s, _c in results[:3]]
    else:
        pool = articles[:4]
    suggestions = [{"id": a["id"], "title": a["title"]} for a in pool]

    reply = (
        "I'm not sure I understood that. Could you describe the problem with a few more details "
        "(what you were doing and any error message)? Or pick one of these topics:"
    )
    _save("bot", reply)
    db.session.commit()
    return jsonify(reply=reply, matched=False, article=None, suggestions=suggestions)