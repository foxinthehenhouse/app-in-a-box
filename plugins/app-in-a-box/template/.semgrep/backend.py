# Test cases for backend.yml, run by `semgrep --test` in CI (security.yml). A "ruleid"
# comment marks a line the named rule must flag; an "ok" comment, a line it must leave
# alone. Never imported.
# ruff: noqa
import hashlib
import pickle
import subprocess
import tempfile

import httpx
import jwt
import requests
import sqlalchemy
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def cases(user_input, cur, app, logger, request, token, key):
    # ruleid: no-eval-exec
    eval(user_input)
    # ruleid: no-eval-exec
    exec(user_input)
    # ok: no-eval-exec
    int(user_input)

    # ruleid: subprocess-shell-true
    subprocess.run("ls " + user_input, shell=True)
    # ok: subprocess-shell-true
    subprocess.run(["ls", user_input])

    # ruleid: tls-verification-disabled
    requests.get("https://example.com", verify=False)
    # ruleid: tls-verification-disabled
    httpx.Client(verify=False)
    # ok: tls-verification-disabled
    httpx.get("https://example.com")

    # ruleid: yaml-unsafe-load
    yaml.load(user_input)
    # ruleid: yaml-unsafe-load
    yaml.unsafe_load(user_input)
    # ok: yaml-unsafe-load
    yaml.load(user_input, Loader=yaml.SafeLoader)
    # ok: yaml-unsafe-load
    yaml.safe_load(user_input)

    # ruleid: pickle-untrusted
    pickle.loads(user_input)

    # ruleid: jwt-signature-not-verified
    jwt.decode(token, options={"verify_signature": False})
    # ruleid: jwt-signature-not-verified
    jwt.decode(token, key, algorithms=["none"])
    # ok: jwt-signature-not-verified
    jwt.decode(token, key, algorithms=["ES256"], audience="authenticated")

    # ruleid: sql-built-from-strings
    cur.execute(f"select * from notes where id = {user_input}")
    # ruleid: sql-built-from-strings
    cur.execute("select * from notes where id = %s" % user_input)
    # ruleid: sql-built-from-strings
    cur.execute("select * from notes where id = " + user_input)
    # ruleid: sql-built-from-strings
    sqlalchemy.text(f"select {user_input}")
    # ok: sql-built-from-strings
    cur.execute("select * from notes where id = %s", (user_input,))

    # ruleid: cors-wildcard-with-credentials
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    # ok: cors-wildcard-with-credentials
    app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"], allow_credentials=True)

    # ruleid: weak-hash-for-security
    hashlib.md5(user_input)
    # ok: weak-hash-for-security
    hashlib.md5(user_input, usedforsecurity=False)
    # ok: weak-hash-for-security
    hashlib.sha256(user_input)

    # ruleid: insecure-tempfile
    tempfile.mktemp()
    # ok: insecure-tempfile
    tempfile.mkstemp()

    # ruleid: fastapi-debug-on
    FastAPI(debug=True)
    # ok: fastapi-debug-on
    FastAPI(title="api")


async def logs(logger, request):
    # ruleid: request-body-logged
    logger.info("got %s", await request.json())
    # ok: request-body-logged
    logger.info("got a request on %s", request.url.path)
