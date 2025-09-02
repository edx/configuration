# docker build -f docker/build/meilisearch-devstack/Dockerfile . -t edxops/meilisearch:devstack

FROM getmeili/meilisearch:v1.10.0
LABEL maintainer="edxops"

# Default working directory
WORKDIR /meili_data

# Expose Meilisearch default port
EXPOSE 7700

# Start Meilisearch
CMD ["meilisearch", "--db-path", "/meili_data", "--http-addr", "0.0.0.0:7700"]
