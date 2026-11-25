from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


ROLES = ("employee", "l1", "l2", "admin")
URGENCIES = ("low", "medium", "high", "critical")
STATUSES = ("open", "in_progress", "escalated", "resolved", "closed")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="employee")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
        }


class Article(db.Model):
    """Knowledge-base article used by the chatbot matcher."""
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False, index=True)
    keywords = db.Column(db.Text, nullable=False, default="")
    solution = db.Column(db.Text, nullable=False)
    default_urgency = db.Column(db.String(20), nullable=False, default="medium")
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "keywords": self.keywords,
            "solution": self.solution,
            "default_urgency": self.default_urgency,
            "is_published": self.is_published,
        }


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(80), nullable=False, default="General")
    urgency = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    level = db.Column(db.Integer, nullable=False, default=1)  # 1 = L1, 2 = L2

    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=True)

    sla_due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    rating = db.Column(db.Integer, nullable=True)  # 1 to 5
    rating_comment = db.Column(db.Text, nullable=True)

    requester = db.relationship("User", foreign_keys=[requester_id], backref="tickets_created")
    assignee = db.relationship("User", foreign_keys=[assignee_id], backref="tickets_assigned")
    article = db.relationship("Article")
    updates = db.relationship(
        "TicketUpdate",
        backref="ticket",
        order_by="TicketUpdate.created_at",
        cascade="all, delete-orphan",
    )


class TicketUpdate(db.Model):
    """History: comments, status changes, escalations, reassignments."""
    __tablename__ = "ticket_updates"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    kind = db.Column(db.String(30), nullable=False, default="comment")
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    author = db.relationship("User")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    sender = db.Column(db.String(10), nullable=False)  # "user" or "bot"
    message = db.Column(db.Text, nullable=False)
    matched_article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)