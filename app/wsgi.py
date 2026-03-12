# wsgi.py (in root directory)

from gevent import monkey
monkey.patch_all()

from app import create_app, socketio

app = create_app()