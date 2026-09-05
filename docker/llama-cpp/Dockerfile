# llama.cpp server with CUDA + Spark-X2.5 architecture support.
#
# Built from the XHToken/llama.cpp fork, which adds Spark-X2.5 architecture
# support (upstream llama.cpp does not yet support it). CUDA arch 86 targets
# the Ampere RTX 3060 Laptop GPU used in this benchmark.
#
# The fork is PINNED to a specific commit for reproducible builds. Divergence
# from upstream ggml-org/llama.cpp at this commit: 15 commits ahead (Spark2_5
# arch + tokenizer + chat template + function-calling parser, ~18 files),
# 321 commits behind. See docs/engine.md.
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

# XHToken/llama.cpp pinned commit (2026-09-04): includes Spark-X2.5 arch.
ARG LLAMA_CPP_COMMIT=4a3635c32fc9f044c2bde9ebeabf50c7e1ec5991
RUN curl -L \
    "https://github.com/XHToken/llama.cpp/archive/${LLAMA_CPP_COMMIT}.tar.gz" \
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
       --target llama-server llama-cli llama-quantize

EXPOSE 8000

ENTRYPOINT ["/src/build/bin/llama-server"]
