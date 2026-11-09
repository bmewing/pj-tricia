#!/bin/bash
set -e
# Runs in DigitalOcean's python:3.13 runtime container, so the compiled dependencies
# (asyncpg, pydantic-core, cryptography) are built for the platform the function runs on.
virtualenv --without-pip virtualenv
pip install -r requirements.txt --target virtualenv/lib/python3.13/site-packages
