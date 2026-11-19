.PHONY: install test run-api run-demo

install:
	pip install -r service/requirements.txt

test:
	cd service && pytest tests/ -v

run-api:
	cd service && uvicorn main:app --reload --host 0.0.0.0 --port 8001

run-demo:
	cd demo && python server.py
