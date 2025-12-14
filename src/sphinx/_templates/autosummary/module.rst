{{ name.split('.')[-1] | underline }}

.. currentmodule:: {{ fullname }}

**Full import path:** ``{{ fullname }}``

.. code-block:: python

   from {{ fullname.rsplit('.', 1)[0] }} import {{ fullname.split('.')[-1] }}
   # or (import a symbol defined in the module)
   from {{ fullname }} import <symbol>

.. automodule:: {{ fullname }}
   :members:
   :undoc-members:
   :show-inheritance:
