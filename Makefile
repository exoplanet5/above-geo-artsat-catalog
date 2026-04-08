PY ?= ~/.venvs/astro313/bin/python
HOST ?= 127.0.0.1
PORT ?= 8090
DIST := dist

.PHONY: build serve run open clean dist dist-clean release

# Parse ~/tles/tle_list.txt -> data/orbits.json. Local-only because it
# needs the TLE files on disk. CI does NOT run this; it consumes the
# committed data/orbits.json instead.
build:
	$(PY) build.py

serve:
	$(PY) serve.py --host $(HOST) --port $(PORT)

run: build
	$(PY) serve.py --host $(HOST) --port $(PORT) --open

open:
	open http://$(HOST):$(PORT)/

# Assemble a self-contained static bundle ready to push to a Hugging Face
# Static Space. Layout:
#   dist/
#     README.md           (HF Spaces metadata frontmatter)
#     index.html
#     app.js
#     styles.css
#     data/orbits.json
#
# This target deliberately does NOT depend on `build` so it can run in CI
# from the committed data/orbits.json without needing ~/tles.
dist:
	@if [ ! -f data/orbits.json ]; then \
		echo "ERROR: data/orbits.json missing. Run 'make build' locally first."; \
		exit 1; \
	fi
	@rm -rf $(DIST)
	@mkdir -p $(DIST)/data
	cp web/index.html $(DIST)/index.html
	cp web/app.js     $(DIST)/app.js
	cp web/styles.css $(DIST)/styles.css
	cp data/orbits.json $(DIST)/data/orbits.json
	cp deploy/README.md $(DIST)/README.md
	@echo
	@echo "dist/ ready. Contents:"
	@ls -lh $(DIST) $(DIST)/data
	@echo
	@echo "Next: commit data/orbits.json and push -- the GitHub Action"
	@echo "syncs dist/ to your HF Space. See DEPLOY.md."

# Convenience: rebuild data + assemble bundle in one shot, for local
# inspection of dist/ before committing data/orbits.json.
release: build dist

dist-clean:
	rm -rf $(DIST)

clean:
	rm -f data/orbits.json
	rm -rf $(DIST)
