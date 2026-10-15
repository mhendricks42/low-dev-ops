FROM mcr.microsoft.com/devcontainers/python:3.2.6-3.13-bookworm

# Every tool is pinned. Bump a version with its own PR.
ARG NODE_VERSION=22.23.3
ARG NPM_VERSION=12.2.0
ARG PIP_VERSION=26.2.1
ARG UV_VERSION=0.13.1
ARG TERRAFORM_VERSION=1.16.6
ARG TFLINT_VERSION=0.64.0
ARG TRIVY_VERSION=0.76.0
ARG CONFTEST_VERSION=0.71.1
ARG CHECKOV_VERSION=3.3.29
ARG AZURE_CLI_VERSION=2.91.0
ARG TARGETARCH

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

RUN case "$TARGETARCH" in \
      amd64) NODE=x64;   TRIVY=64bit; CONFTEST=x86_64 ;; \
      arm64) NODE=arm64; TRIVY=ARM64; CONFTEST=arm64 ;; \
      *) echo "unsupported arch $TARGETARCH" && exit 1 ;; \
    esac \
 && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE}.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1 \
 # The npm bundled with Node lags behind on security fixes.
 && npm install -g --no-fund --no-audit "npm@${NPM_VERSION}" && npm cache clean --force \
 && curl -fsSLo /tmp/tf.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TARGETARCH}.zip" \
 && unzip -o /tmp/tf.zip terraform -d /usr/local/bin \
 && curl -fsSLo /tmp/tflint.zip "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_${TARGETARCH}.zip" \
 && unzip -o /tmp/tflint.zip tflint -d /usr/local/bin \
 && curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${TRIVY}.tar.gz" \
    | tar -xz -C /usr/local/bin trivy \
 && curl -fsSL "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${CONFTEST}.tar.gz" \
    | tar -xz -C /usr/local/bin conftest \
 && rm -f /tmp/*.zip

# Python CLIs live in isolated uv tool envs, outside the project venv.
ENV UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin
RUN pip install --no-cache-dir "pip==${PIP_VERSION}" "uv==${UV_VERSION}" \
 && uv tool install --no-cache "checkov==${CHECKOV_VERSION}" \
 && uv tool install --no-cache "azure-cli==${AZURE_CLI_VERSION}"
