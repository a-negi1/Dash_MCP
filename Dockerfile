FROM mcr.microsoft.com/dotnet/runtime:8.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.11 python3-pip curl unzip \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://github.com/pbi-tools/pbi-tools/releases/download/1.2.0/pbi-tools.core.1.2.0_linux-x64.zip \
    -o /tmp/pbi-tools.zip \
    && unzip /tmp/pbi-tools.zip -d /usr/local/bin/pbi-tools-dir \
    && ln -s /usr/local/bin/pbi-tools-dir/pbi-tools.core /usr/local/bin/pbi-tools \
    && chmod +x /usr/local/bin/pbi-tools-dir/pbi-tools.core \
    && rm /tmp/pbi-tools.zip
ENV PATH="$PATH:/usr/local/bin"
COPY requirements.txt .
RUN pip3 install -r requirements.txt --break-system-packages
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
