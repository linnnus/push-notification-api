import cryptography.hazmat.primitives.serialization
import dbm.dumb
import hashlib
import json
import os
import py_vapid
import pywebpush
import typing as t
from . import utils
import werkzeug.exceptions
import werkzeug.middleware.proxy_fix
import werkzeug.middleware.shared_data
import werkzeug.routing.exceptions
import werkzeug.serving

app = utils.Application()

## Middleware

def convert_json(app: utils.Application, request: werkzeug.Request, next):
    """Middleware that converts all response and return-values (except
    :ref:`werkzeug.wrappers.Response`) in `/api` routes to JSON responses."""

    if request.path.startswith("/api"):
        try:
            body = next()
        except werkzeug.exceptions.HTTPException as e:
            app.log("exception", "Got HTTP exception")
            body = e
        except Exception as e:
            app.log("exception", "Got other exception")
            body = werkzeug.exceptions.InternalServerError(original_exception=e)

        if isinstance(body, werkzeug.exceptions.HTTPException):
            assert body.response is None, "Unhaled case"
            code = body.code or 500
            data = {
                "success": False,
                "info": {
                    "code": code,
                    "message": body.description
                }
            }
            return werkzeug.Response(json.dumps(data), status=code)
        elif isinstance(body, werkzeug.Response):
            # Don't alter Response objects.
            return body
        else:
            data = { "success": True, "data": body }
            return werkzeug.Response(json.dumps(data))
    else:
        return next()

app.use(utils.add_timing_header)
app.use(convert_json)

## routes

@app.route("/api/application-server-key.json")
def application_server_key(vapid: py_vapid.Vapid02):
    # Based on https://github.com/web-push-libs/vapid/blob/4b33f37badef47d1cdaa8a3bb9ad64c741bf731a/python/py_vapid/main.py#L68-L74
    raw_pub = vapid.public_key.public_bytes(
       cryptography.hazmat.primitives.serialization.Encoding.X962,
       cryptography.hazmat.primitives.serialization.PublicFormat.UncompressedPoint
    )
    key = py_vapid.b64urlencode(raw_pub)
    return { "key": key }

@app.route("/api/submit-subscription", method="POST")
def submit_subscription(db: dbm.dumb._Database, request: werkzeug.Request):
    try:
        subscription = request.json
        validate_subscription_json(subscription)
    except (ValueError, json.JSONDecodeError) as e:
        print(e)
        exc = werkzeug.exceptions.HTTPException(str(e))
        exc.code = 400
        raise exc

    token = hash_json(subscription)[:15]
    db[token] = json.dumps(subscription)
    return { "token": token }

def validate_subscription_json(subscription: t.Any):
    if not isinstance(subscription, dict):
        raise ValueError("Expected dictionary")
    if "endpoint" not in subscription:
        raise ValueError("Missing property 'endpoint'")
    if not isinstance(subscription["endpoint"], str):
        raise ValueError("Property 'endpoint' should be a string")
    if "keys" not in subscription:
        raise ValueError("Missing property 'keys'")
    if not isinstance(subscription["keys"], dict):
        raise ValueError("Property 'endpoint' should be an object")

# https://gist.github.com/magnetikonline/b226a6d2b5c2bc99fbbf20f0f607bbeb
def hash_json(data: t.Any) -> str:
    def hasher(value: t.Any):
        if type(value) is list:
            # hash each item within the list
            for item in value:
                hasher(item)
            return
        if type(value) is dict:
            # work over each property in the dictionary, using a sorted order
            for item_key in sorted(value.keys()):
                # hash both the property key and the value
                hash.update(item_key.encode())
                hasher(value[item_key])

            return
        if type(value) is not str:
            value = str(value)
        hash.update(value.encode())

    # create new hash, walk given data and return result
    hash = hashlib.sha1()
    hasher(data)

    return hash.hexdigest()

@app.route("/api/send-notification/<token>", method="POST")
def send_notification(request: werkzeug.Request, db: dbm.dumb._Database, token: str):
    try:
        subscription_text = db[token]
    except KeyError:
        exc = werkzeug.exceptions.HTTPException(f"Unknown token: {token}")
        exc.code = 404
        raise exc
    subscription = json.loads(subscription_text)

    try:
        notification_text = request.data
        notification = json.loads(notification_text)
        validate_notification_json(notification)
    except (ValueError, json.JSONDecodeError) as error:
        exc = werkzeug.exceptions.HTTPException(description=f"Malformed json: {error}")
        exc.code = 400
        raise exc

    try:
        pywebpush.webpush(subscription, notification_text, vapid_private_key=vapid,
                          vapid_claims={ "sub": "mailto:linusvejlo+vapid@gmail.com" })
    except pywebpush.WebPushException as error:
        description = f"Request to Web Push server failed"
        if error.response and (extra := error.response.json()):
            description += f"with message '{extra.message}' ({extra.code})"
        exc = werkzeug.exceptions.HTTPException(description)
        exc.code = 503
        raise exc

    return "idk man what'd you wnat me to say. it worked."

def validate_notification_json(notification: t.Any):
    if not isinstance(notification, dict):
        raise ValueError("Expected dictionary")
    if "title" not in notification:
        raise ValueError("Missing property 'title'")
    if not isinstance(notification["title"], str):
        raise ValueError("Property 'title' should be a string")
    if "message" in notification and not isinstance(notification["message"], str):
        raise ValueError("Optional property 'message' should be a string")
    if "url" in notification and not isinstance(notification["url"], str):
        raise ValueError("Optional property 'url' should be a string")

@app.route("/")
def redirect_to_index():
    raise werkzeug.routing.exceptions.RequestRedirect("/index.html")

# Serve static files from `./public`.
app.wsgi_app = werkzeug.middleware.shared_data.SharedDataMiddleware(app.wsgi_app, {
    "/": os.path.join(os.path.dirname(__file__), "public"),
})

# Handle running behind a proxy like NGINX.
app.wsgi_app = werkzeug.middleware.proxy_fix.ProxyFix(app.wsgi_app)

# Connect to database.
db_path = "./tokens"
app.ressources["db"] = dbm.dumb.open(db_path, "c")

# Load/generate private key.
private_key_path = "./private_key.pem"
try:
    with open(private_key_path, "rb") as f:
        pem = f.read()
    vapid = py_vapid.Vapid02.from_pem(pem)
except FileNotFoundError:
    print(f"No private key found at {private_key_path}. Generating new one.")
    vapid = py_vapid.Vapid02()
    vapid.generate_keys()
    vapid.save_key(private_key_path)
app.ressources["vapid"] = vapid
