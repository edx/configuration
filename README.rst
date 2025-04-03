Configuration Management
########################

(Note: This is the 2U fork of `<https://github.com/openedx/configuration>`__, which has been deprecated from Open edX.)

Description
***********

A collection of configuration scripts using Ansible for deploying edx.org.
This is not meant for general Open edX deployment and use. View the
`Open EdX Installation options`_ page for recommended deployment options.

For info on any large recent changes please see the `change log`_.

What is in this Repo?
*********************

* `playbooks </playbooks>`__: This directory contains ansible playbooks that can
  be used to configure individual services in the openedx platform. See
  `Open EdX Installation options`_ before trying to use any of the scripts in
  this directory.
* `docker </docker>`__: This directory contains dockerfiles that can be used to
  test that playbooks execute cleanly.  See `Makefiles <Makefiles.rst>`__ for
  Documentation on how to run these containers.
* `requirements </requirements>`__ : inputs for `pip-compile <https://github.com/jazzband/pip-tools>`__
  Update files in this directory and then run ``make upgrade`` to update
  ``requirements.txt``
* `tests </tests>`__: scripts used by travis-ci to test changes to this repo
* `util </util>`__: one-off scripts or tools used to perform certain functions
  related to openedx management.
* `vagrant </vagrant>`__: vagrant tooling for testing changes to this repo.


Roadmap
*******

This repository is in ``sustained`` status.  The goal is to deprecate this codebase
and move the deployment code into the repos with the application code.

With the adoption of containerized application platforms like `Kubernetes
<https://kubernetes.io/>`__, the tools in this repository are complex
and inappropriate for building small single purpose containers.

At edx.org, we are focusing on deployment of applications using `Terraform
<https://www.terraform.io/>`__ and `Kubernetes <https://kubernetes.io/>`__.  We
hope to provide open source tooling for this soon.


Contributing
************

* Bugfixes: If you would like to contribute a bugfix to this codebase, please open
  a pull request. A bot will automatically walk your contribution through the
  `Open Source Contribution process <https://edx-developer-guide.readthedocs.io/en/latest/process/overview.html>`__.


.. _Open EdX Installation options: https://open.edx.org/installation-options
.. _Ansible: http://ansible.com/
.. _change log: https://github.com/openedx/configuration/blob/master/CHANGELOG.md
