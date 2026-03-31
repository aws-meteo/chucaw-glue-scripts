Getting Started
===============

Instalacion para documentacion
------------------------------

Desde la raiz del repo:

.. code-block:: powershell

   .\.venv\Scripts\python.exe -m pip install -r requirements-docs.txt

Build local HTML
----------------

.. code-block:: powershell

   cd docs/sphinx
   ..\..\.venv\Scripts\python.exe -m sphinx -b html source build/html

Alternativa con Makefile:

.. code-block:: powershell

   cd docs/sphinx
   make html

Salida esperada
---------------

El sitio generado queda en:

``docs/sphinx/build/html/index.html``
