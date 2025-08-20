# docker build -f docker/build/meilisearch-devstack/Dockerfile . -t edxops/meilisearch:devstack

FROM getmeili/meilisearch:v1.10.0
LABEL maintainer="edxops"

# (Optional) Create a data directory
RUN mkdir -p /meili_data && chown -R root:root /meili_data

# Set environment variables (can be overridden at runtime)
ENV MEILI_ENV=development \
    MEILI_HTTP_ADDR=0.0.0.0:7700 \
    MEILI_DB_PATH=/meili_data

# Expose API port
EXPOSE 7700

# Default entrypoint
CMD ["meilisearch"]
