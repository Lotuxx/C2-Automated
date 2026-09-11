# Contributing

## 1. Purpose

This document defines the development workflow and repository conventions for **C2-AUTOMATED**.

The goal is to keep development organized, protect stable versions of the project, and ensure that implementation changes remain consistent with the documented architecture.

---

# 2. Development Model

Development follows a three-level branch structure:

```text
feature/*
    │
    ▼
   dev
    │
    ▼
  main
```

Each branch has a specific role.

### `main`

`main` represents the **stable and validated state** of the project.

It should contain code that is considered suitable for:

- demonstration;
- evaluation;
- project milestones;
- release or submission points.

Direct development on `main` should be avoided.

---

### `dev`

`dev` is the **integration branch**.

Completed feature work is merged into `dev` before being considered for `main`.

The purpose of `dev` is to verify that independently developed components work correctly together.

`dev` may temporarily contain unfinished or integration-level issues that are not appropriate for `main`.

---

### `feature/*`

Feature branches are used for isolated development work.

Examples:

```text
feature/architecture
feature/c2-server
feature/agent
feature/protocol
feature/task-manager
feature/file-transfer
feature/tests
```

A feature branch should normally be created from `dev`.

---

# 3. Branch Workflow

The normal workflow is:

```text
Create feature branch
        │
        ▼
Implement change
        │
        ▼
Test locally
        │
        ▼
Pull Request → dev
        │
        ▼
Integration and validation
        │
        ▼
Pull Request → main
        │
        ▼
Stable state
```

The general rule is:

> **Develop on feature branches, integrate through `dev`, and keep `main` stable.**

---

# 4. Feature Branches

A feature branch should focus on one coherent change.

For example:

```text
feature/file-transfer
```

is preferable to a branch containing unrelated changes to:

- file transfer;
- database structure;
- CLI layout;
- logging;
- documentation.

Small and focused branches make changes easier to review, test, and revert.

## Branch Naming

Use descriptive names following the pattern:

```text
feature/<name>
fix/<name>
docs/<name>
test/<name>
refactor/<name>
```

Examples:

```text
feature/session-manager
feature/file-transfer
fix/protocol-validation
docs/protocol
test/task-lifecycle
refactor/storage-interface
```

---

# 5. Pull Requests

Changes should be merged through Pull Requests rather than pushed directly into protected branches.

A Pull Request should clearly explain:

- what was changed;
- why the change was necessary;
- which part of the architecture it affects;
- how it was tested;
- whether documentation was updated.

For architectural changes, the Pull Request should also identify the relevant entry in [`DECISIONS.md`](DECISIONS.md), when applicable.

---

# 6. Keeping the Documentation Consistent

The repository documentation is part of the project design.

When a change affects the architecture, the relevant documentation must be updated.

Examples:

| Change | Documentation |
|---|---|
| Component responsibility changes | `ARCHITECTURE.md` |
| Important design choice | `DECISIONS.md` |
| Security property/control changes | `SECURITY.md` |
| Detailed subsystem behaviour | `docs/` |
| Project usage/install instructions | `README.md` |

The objective is to avoid a situation where the code and documentation describe different architectures.

---

# 7. Commits

Commits should describe the change they introduce.

Prefer clear, action-oriented messages.

Examples:

```text
feat: add session manager
feat: implement task lifecycle
fix: reject invalid protocol messages
test: add task manager tests
docs: update architecture
refactor: isolate file storage interface
```

Avoid vague messages such as:

```text
update
changes
stuff
fix
work
```

A commit should ideally represent one logical change.

---

# 8. Testing Before Merge

Changes should be tested before being merged into `dev`.

At minimum, the contributor should verify that:

- the modified component behaves as expected;
- existing relevant tests still pass;
- the application starts correctly when applicable;
- the change does not break another architectural component.

Before merging into `main`, the integrated system should be validated rather than relying only on isolated component tests.

---

# 9. Security-Sensitive Changes

Changes involving the following areas require particular care:

- TLS and transport;
- protocol validation;
- authentication or identity;
- task execution;
- file handling;
- filesystem paths;
- storage;
- secrets or credentials;
- logging of sensitive information.

Such changes should be reviewed against [`SECURITY.md`](SECURITY.md).

Secrets, credentials, private keys, certificates containing private material, and other sensitive development artifacts must not be committed to the repository.

---

# 10. Configuration and Local Data

Local development data should remain separate from source-controlled project files where appropriate.

This includes:

- local databases;
- generated files;
- temporary files;
- transferred test files;
- local certificates and private keys;
- environment-specific configuration;
- logs generated during development.

These files should be covered by `.gitignore` where they are not intended to be version controlled.

---

# 11. Documentation Changes

Documentation should be updated together with the implementation when a change affects documented behaviour.

For example:

```text
Code change
    │
    ├── architecture affected?
    │       └── update ARCHITECTURE.md
    │
    ├── design decision?
    │       └── update DECISIONS.md
    │
    ├── security affected?
    │       └── update SECURITY.md
    │
    └── detailed subsystem behaviour?
            └── update docs/
```

Documentation should describe the current state of the project rather than planned features as though they were already implemented.

---

# 12. Architecture Changes

Not every implementation change requires an architecture change.

For example:

```text
Changing an internal helper function
→ normally no architecture change.

Changing the responsibility of TaskManager
→ architecture change.

Replacing SQLite with another persistence backend
→ architecture and decision change.

Adding a new transport implementation
→ architecture/decision documentation may need updating.
```

When a change modifies a major component boundary, responsibility, dependency, or security property, the change should be documented before or together with its implementation.

---

# 13. Laboratory and Testing Scope

C2-AUTOMATED is an academic project intended for an authorized laboratory environment.

Development and testing must remain restricted to systems and environments for which explicit authorization exists.

---

# 14. Current Development Workflow

The expected workflow for the project is:

```text
1. Read the relevant architecture/documentation
        ↓
2. Create a feature branch from `dev`
        ↓
3. Implement one coherent change
        ↓
4. Test the change
        ↓
5. Update documentation when necessary
        ↓
6. Merge into `dev`
        ↓
7. Validate the integrated system
        ↓
8. Merge validated changes into `main`
```

The repository should therefore evolve through **small, understandable, testable changes** rather than large unstructured modifications.
