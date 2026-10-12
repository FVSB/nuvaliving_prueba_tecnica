---
name: prefer-inheritance
description: Prefer inheritance for project models with a clear shared semantic contract; ask the user when the relationship is ambiguous.
metadata:
  author: project
---

# Prefer Inheritance

Before adding or maintaining parallel models, look for an existing model with the same meaningful
fields, validation rules, lifecycle, and contract. When the relationship is clearly an **is-a**
relationship, introduce or extend a shared base class rather than duplicating that structure.

Apply this especially to domain and application contracts, including dataclasses, state objects,
and value models. Preserve immutability, slots, validation, and public behavior when extracting a
base class.

Do not force inheritance only because two classes coincidentally share primitive fields. If it is
unclear whether the shared structure represents one semantic contract, whether subclasses need
different lifecycle/validation behavior, or whether composition would communicate intent better,
ask the user before changing the hierarchy.

When a base is introduced, update focused tests to prove subclasses retain the shared contract and
avoid changing unrelated behavior.
