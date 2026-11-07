"""Shared objects created once at startup and used by every router/agent."""
from app.orchestrator.blackboard import Blackboard
from app.services.firebase import init_firestore

blackboard = Blackboard(db=init_firestore())
