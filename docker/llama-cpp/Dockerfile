# llama.cpp server with CUDA + Spark-X2.5 architecture support.
#
# Built from the XHToken/llama.cpp fork, which adds Spark-X2.5 architecture
# support (upstream llama.cpp does not yet support it). CUDA arch 86 targets
# the Ampere RTX 3060 Laptop GPU used in this benchmark.
#
# Pin note: the fork is pulled from its default branch at build time. For
# bit-exact reproduction, record the resulting image digest (see
# benchmark/cross_bench_provenance.txt) after building.
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

# XHToken/llama.cpp: includes Spark-X2.5 architecture support.
RUN curl -L \
    https://github.com/XHToken/llama.cpp/archive/refs/heads/master.tar.gz \
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
       --target llama-server llama-cli

EXPOSE 8000

ENTRYPOINT ["/src/build/bin/llama-server"]
