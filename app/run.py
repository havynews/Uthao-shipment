# run.py
# from app import create_app, socketio

# app = create_app()

# if __name__ == '__main__':
#     socketio.run(app, debug=True, host="0.0.0.0", port=8000)
    # app.run(debug=True, host="0.0.0.0", port=8000)

# run.py  ← sits at Uthao-Shipment/run.py
import eventlet
eventlet.monkey_patch()

from app.app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=False, host="0.0.0.0", port=8000)