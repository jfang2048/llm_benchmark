# llama.cpp server built from PINNED upstream ggml-org/llama.cpp.
#
# Used by the mainstream 8-9B primary cohort. Unlike the legacy Spark fork
# image (docker/llama-cpp/), this image needs no Spark-specific patches and
# tracks a recent upstream release so that Qwen3, Llama, GLM4, and Gemma
# architectures are all served by the same binary.
#
# CUDA arch 86 targets the Ampere RTX 3060 Laptop GPU (6 GiB) used here.
FROM nvidia/cuda:13.3.1-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    curl \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Pinned upstream release (stable tag; all cohort architectures present:
# qwen3, llama, glm4, gemma2, gemma3). Resolves to commit
# 5ac847190e979e0da7c4a21806630805f396d487.
ARG LLAMA_CPP_TAG=v0.4.0
RUN curl -L \
    "https://github.com/ggml-org/llama.cpp/archive/refs/tags/${LLAMA_CPP_TAG}.tar.gz" \
    -o llama.tar.gz \
    && tar -xzf llama.tar.gz --strip-components=1 \
    && rm llama.tar.gz

RUN cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=OFF \
    -DGGML_CUDA=ON \
    -DGGML_BACKEND_DL=ON \
    -DGGML_CPU_ALL_VARIANTS=ON \
    -DCMAKE_CUDA_ARCHITECTURES=86 \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,--allow-shlib-undefined" \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_CURL=OFF \
    && cmake --build build \
       --config Release \
       -j"$(nproc)" \
       --target llama-server llama-cli llama-quantize llama-bench

EXPOSE 8000

ENTRYPOINT ["/src/build/bin/llama-server"]
