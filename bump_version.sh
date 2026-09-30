#!/bin/bash

if [ ! -f "pyproject.toml" ]; then
  echo "Error: pyproject.toml not found"
  exit 1
fi

VERSION=$(grep -E '^\s*version\s*=\s*"' pyproject.toml | sed -E 's/.*version\s*=\s*"([^"]+)".*/\1/')
if [ -z "$VERSION" ]; then
  echo "Error: Could not find version in pyproject.toml"
  exit 1
fi

TAG="v$VERSION"
git tag "$TAG"
if [ $? -ne 0 ]; then
  echo "Error: Failed to create Git tag $TAG"
  exit 1
fi

git push origin "$TAG"
if [ $? -ne 0 ]; then
  echo "Error: Failed to push tag $TAG"
  exit 1
fi

echo "Successfully created and pushed tag $TAG"
