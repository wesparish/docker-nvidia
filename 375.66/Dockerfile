FROM ubuntu:17.04

LABEL maintainer="Alexandre Buisine <alexandrejabuisine@gmail.com>"

COPY resources/etc/OpenCL/vendors/nvidia.icd /etc/OpenCL/vendors/nvidia.icd
COPY resources/usr/bin/nvidia-smi /usr/bin/nvidia-smi
COPY resources/usr/share/nvidia/nvidia-application-profiles-375.66-rc \
 /usr/share/nvidia/nvidia-application-profiles-375.66-rc
COPY resources/usr/lib/x86_64-linux-gnu/libcuda.so.375.66 \
 resources/usr/lib/x86_64-linux-gnu/libnvidia-fatbinaryloader.so.375.66 \
 resources/usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.375.66 \
 resources/usr/lib/x86_64-linux-gnu/libOpenCL.so.1.0.0 \
 /usr/lib/x86_64-linux-gnu/

RUN ln -s /usr/lib/x86_64-linux-gnu/libcuda.so.375.66 /usr/lib/x86_64-linux-gnu/libcuda.so.1 \
 && ln -s /usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.375.66 /usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.1 \
 && ln -s /usr/lib/x86_64-linux-gnu/libOpenCL.so.1.0.0 /usr/lib/x86_64-linux-gnu/libOpenCL.so.1.0 \
 && ln -s /usr/lib/x86_64-linux-gnu/libOpenCL.so.1.0 /usr/lib/x86_64-linux-gnu/libOpenCL.so.1 \
 && ln -s /usr/lib/x86_64-linux-gnu/libOpenCL.so.1 /usr/lib/x86_64-linux-gnu/libOpenCL.so \
 && ldconfig