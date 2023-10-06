import functools
import inspect
import logging
import time
import typing as t
import werkzeug
import werkzeug.exceptions
import werkzeug.routing

class MiddlewareError(Exception):
    pass

Middleware: t.TypeAlias = t.Callable
"""Part of a middleware chain. Middleware takes an optional `next` parameter
which evaluates the next item in the chain."""

class Application:
    """
    Lightweight wrapper around Werkzeug utilities, allowing more flask-like usage.
    """

    def __init__(self):
        self._middlewares = list[Middleware]()
        self._endpoints = { }
        self._url_map = werkzeug.routing.Map()
        self.ressources = dict[str, t.Any]()

    def use(self, middleware):
        """Add global middleware."""

        self._middlewares.append(middleware)

    def route(self, string: str, middlewares: list[Middleware]=[], method="GET"):
        """
        Decorator a
        """

        def decorator(func):
            handler = self.compose_middleware(self._middlewares + middlewares + [ func ])
            endpoint = f"{func.__module__}.{func.__name__}"[16:]
            self._endpoints[endpoint] = handler
            rule = werkzeug.routing.Rule(string, endpoint=endpoint, methods=[method])
            self._url_map.add(rule)
            return func

        return decorator

    @staticmethod
    def compose_middleware(fns: list[Middleware]):
        def composed(injectables):
            index = -1

            def dispatch(i: int):
                nonlocal index
                if i < index:
                    raise MiddlewareError("next() called multiple times")
                try:
                    fn = fns[i]
                except IndexError:
                    raise MiddlewareError("next() must not be called from final function")
                index = i
                next = functools.partial(dispatch, i + 1)
                return Application.inject(fn, { **injectables, "next": next })

            return dispatch(0)

        return composed

    def wsgi_app(self, environ, start_response):
        """WSGI-compatible application"""
        urls = self._url_map.bind_to_environ(environ)
        try:
            endpoint, args = urls.match()

            request = werkzeug.Request(environ)
            injectables = { "app": self, "request": request, **self.ressources, **args }
            response = self._endpoints[endpoint](injectables)
            assert isinstance(response, werkzeug.Response)
            return response(environ, start_response)
        except werkzeug.exceptions.HTTPException as e:
            # Render default error page
            return e(environ, start_response)

    def log(self, level: str, *args, **kwargs):
        if not hasattr(self, "logger"):
            self.logger = logging.Logger("app")
        if not self.logger.hasHandlers():
            self.logger.addHandler(logging.StreamHandler())
        if self.logger.level == logging.NOTSET:
            self.logger.setLevel(logging.INFO)
        getattr(self.logger, level)(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """Make :ref:`Application` instances directly callable as WSGI applications."""
        return self.wsgi_app(*args, **kwargs)

    @staticmethod
    def inject(f: t.Callable, injectables: dict[str, t.Any]):
        args, varargs, varkw = inspect.getargs(f.__code__)
        if not (varargs is None and varkw is None):
            raise ValueError("Weird argument types are not supported")
        call_args = dict([(k, v) for k, v in injectables.items() if k in args])
        return f(**call_args)

def add_timing_header(next):
    """Middleware that adds a basic `Server-Timing` header."""
    start = time.time()
    response = next()
    assert isinstance(response, werkzeug.Response)
    delta = time.time() - start
    response.headers.add("Server-Timing", f"app;dur={delta:.1f}")
    return response

