#!/bin/bash

#VERSION_LIST=(384.90 384.98)
VERSION_LIST=(384.90-ubuntu1604)

for version in ${VERSION_LIST[@]}; do
  echo "*** BUILDING $version ***"
  docker build -t wesparish/nvidia:$version -f Dockerfile.$version .
  docker push wesparish/nvidia:$version
done
