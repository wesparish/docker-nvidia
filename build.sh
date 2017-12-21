#!/bin/bash

VERSION_LIST=(384.90)

for version in $VERSION_LIST; do
  docker build -t nvidia:$version -f Dockerfile.$version .
  docker push nvidia:$version
done
