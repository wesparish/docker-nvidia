#!/bin/bash

VERSION_LIST=(384.90)

for version in $VERSION_LIST; do
  docker build -t wesparish/nvidia:$version -f Dockerfile.$version .
  docker push wesparish/nvidia:$version
done
