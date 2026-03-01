.PHONY: test test-python test-web web-install

test: test-python test-web

test-python:
	pytest -q
	python3 -m compileall -q apps

web-install:
	@if [ ! -d apps/dashboard-web/node_modules ]; then \
		npm --prefix apps/dashboard-web ci; \
	fi

test-web: web-install
	npm --prefix apps/dashboard-web run typecheck
	npm --prefix apps/dashboard-web run test:e2e
