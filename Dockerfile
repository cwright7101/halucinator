FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN echo "deb-src http://archive.ubuntu.com/ubuntu/ jammy-security main restricted universe multiverse" >> /etc/apt/sources.list


RUN apt-get update && \
  apt-get build-dep -y qemu && \
  apt-get install -y \
  build-essential \
  ca-certificates \
  cmake \
  ethtool \
  g++ \
  gcc-arm-none-eabi \
  git \
  gdb-multiarch \
  libpixman-1-dev \
  python3-pip \
  python3-venv \
  python-tk \
  sudo \
  tcpdump \
  vim \
  wget \
  ninja-build && \
  apt-get clean && \
  apt-get autoclean -y && \
  rm -rf /var/lib/apt/lists/*


WORKDIR /root
ADD . ./halucinator
WORKDIR /root/halucinator
RUN pip install -e deps/avatar2/
RUN pip install -r src/requirements.txt
RUN pip install -e src

RUN mkdir -p deps/build-qemu/arm-softmmu
RUN mkdir -p deps/build-qemu/aarch64-softmmu
RUN mkdir -p deps/build-qemu/ppc-softmmu
RUN mkdir -p deps/build-qemu/ppc64-softmmu
RUN mkdir -p deps/build-qemu/mips-softmmu
# RUN pip install meson

WORKDIR /root/halucinator/deps/build-qemu/arm-softmmu
RUN /root/halucinator/deps/avatar-qemu/configure --target-list=arm-softmmu
RUN make all -j`nproc`

WORKDIR /root/halucinator/deps/build-qemu/aarch64-softmmu
RUN /root/halucinator/deps/avatar-qemu/configure --target-list=aarch64-softmmu
RUN make all -j`nproc`

WORKDIR /root/halucinator/deps/build-qemu/ppc-softmmu
RUN /root/halucinator/deps/avatar-qemu/configure --target-list=ppc-softmmu
RUN make all -j`nproc`

WORKDIR /root/halucinator/deps/build-qemu/mips-softmmu
RUN /root/halucinator/deps/avatar-qemu/configure --target-list=mips-softmmu
RUN make all -j`nproc`

WORKDIR /root/halucinator/deps/build-qemu/ppc64-softmmu
RUN /root/halucinator/deps/avatar-qemu/configure --target-list=ppc64-softmmu
RUN make all -j`nproc`

WORKDIR  /root/halucinator

# Symlink so VSCode extensions can find halucinator at /halucinator/
RUN ln -s /root/halucinator /halucinator

# Generate bpdata.json for VSCode extensions
RUN python3 extra_tools/parse_bp_handlers.py -s src/halucinator -o bpdata.json

# Set QEMU environment variables
ENV HALUCINATOR_QEMU_ARM="/root/halucinator/deps/build-qemu/arm-softmmu/qemu-system-arm"
ENV HALUCINATOR_QEMU_ARM64="/root/halucinator/deps/build-qemu/aarch64-softmmu/qemu-system-aarch64"
ENV HALUCINATOR_QEMU_PPC="/root/halucinator/deps/build-qemu/ppc-softmmu/qemu-system-ppc"
ENV HALUCINATOR_QEMU_PPC64="/root/halucinator/deps/build-qemu/ppc64-softmmu/qemu-system-ppc64"
ENV HALUCINATOR_QEMU_MIPS="/root/halucinator/deps/build-qemu/mips-softmmu/qemu-system-mips"

# Target directory for user projects
ENV TARGET="/home/haluser/project"

# Create haluser with sudo access for Docker workflows
RUN useradd -u 20000 -m -s /bin/bash haluser && \
    echo "haluser:password" | chpasswd && \
    echo "haluser    ALL=(ALL:ALL) ALL" >> /etc/sudoers && \
    usermod -aG sudo haluser && \
    echo "PS1='halucinator-docker:\w # '" >> /home/haluser/.bashrc

# Copy demo files to user home
RUN cp -r demo /home/haluser/demo && chown -R haluser:haluser /home/haluser/demo

USER haluser
WORKDIR /home/haluser
