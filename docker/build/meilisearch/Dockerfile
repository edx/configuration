FROM edxops/xenial-common:latest
LABEL maintainer="edxops"

# Copy ansible roles/playbooks into container
ADD . /edx/app/edx_ansible/edx_ansible
WORKDIR /edx/app/edx_ansible/edx_ansible/docker/plays

# Run ansible playbook for Meilisearch (you need meilisearch.yml role defined)
RUN /edx/app/edx_ansible/venvs/edx_ansible/bin/ansible-playbook meilisearch.yml -c local \
   -i '127.0.0.1,'

WORKDIR /etc/meilisearch
CMD service meilisearch start && sleep 5 && tail -f /edx/var/log/meilisearch/meilisearch.log
EXPOSE 7700 7701
