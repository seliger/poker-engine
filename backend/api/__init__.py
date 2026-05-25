"""REST API Layer package.

Exposes create_app() via backend.app. Internal modules:
  errors       — error codes and APIError exception
  validators   — request validation helpers
  serializers  — Game Layer → JSON serializers
  socket       — Flask-SocketIO instance
  game_manager — GameManager class (in-memory session and hand state)
  routes/      — Flask blueprints for each endpoint group

Layer: REST API (communicates with Game Layer and Persistence Layer only).
"""
