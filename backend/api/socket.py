"""REST API Layer: Flask-SocketIO singleton.

The SocketIO object is created here and attached to the Flask application in
app.create_app(). Route handlers and the game manager import this instance
to emit WebSocket events to connected clients.

Layer: REST API.
"""

from flask_socketio import SocketIO

socketio: SocketIO = SocketIO()
