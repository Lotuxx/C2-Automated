# Contributing

## 1. Purpose

This document defines the development workflow and repository conventions for **C2-AUTOMATED**.

The goal is to keep development organized, protect stable versions of the project, and ensure that implementation changes remain consistent with the documented architecture.

---

# 2. Development Model

Development follows a three-level branch structure:

```text
feature/* / fix/* / docs/* / test/* / refactor/*
                         │
                         ▼
                        dev
                         │
                         ▼
                       main
```

Each level has a specific role.

### `main`

`main` represents the **stable and validated state** of the project.

It should contain code that is considered suitable for:

- demonstrations;
- evaluations;
- project milestones;
- stable submission states.

Direct development on `main` should be avoided.

---

### `dev`

`dev` is the **integration branch**.

Purpose-specific branches are merged into `dev` before being considered for `main`.

Its role is to verify that independently developed changes work correctly together.

`dev` may temporarily contain integration issues that should not exist on `main`.

---

### Working branches

Working branches are created from `dev` and are used for a specific type of development activity.

The branch prefix indicates the **primary purpose of the work**.

---

# 3. Branch Types

## 3.1 `feature/`

Use a `feature/` branch when **adding new functionality that does not currently exist**.

Use this branch type when the objective is:

> "I am implementing something new."

Examples:

```text
feature/session-manager
feature/file-transfer
feature/task-queue
feature/agent-registration
feature/tls-transport
```

A feature branch should normally represent one coherent feature or architectural component.

---

## 3.2 `fix/`

Use a `fix/` branch when **correcting existing functionality that is not behaving as intended**.

Use this branch type when the objective is:

> "Something that already exists is broken or incorrect, and I am correcting it."

Examples:

```text
fix/protocol-validation
fix/session-disconnect
fix/file-chunk-handling
fix/task-state-transition
```

A fix branch should focus on correcting an identifiable problem rather than introducing unrelated functionality.

---

## 3.3 `docs/`

Use a `docs/` branch when the work consists **only of documentation changes**.

Use this branch type when the objective is:

> "I am changing documentation without changing application behaviour."

Examples:

```text
docs/update-architecture
docs/security-model
docs/protocol-specification
docs/contributing-guide
```

This can include changes to:

- `README.md`;
- `ARCHITECTURE.md`;
- `SECURITY.md`;
- `DECISIONS.md`;
- files under `docs/`.

Documentation changes that are inseparable from a feature implementation may instead remain in the corresponding feature branch.

---

## 3.4 `test/`

Use a `test/` branch when the primary purpose of the work is **adding, improving, or reorganizing tests**.

Use this branch type when the objective is:

> "I am improving the verification of existing functionality."

Examples:

```text
test/task-manager
test/protocol-validation
test/file-transfer
test/session-lifecycle
```

If tests are added as an integral part of implementing a new feature, keeping them in the corresponding `feature/` branch is also acceptable.

---

## 3.5 `refactor/`

Use a `refactor/` branch when **restructuring or improving the internal code without intentionally changing its expected behaviour**.

Use this branch type when the objective is:

> "The code structure needs to change, but the intended functionality should remain the same."

Examples:

```text
refactor/storage-interface
refactor/c2-core
refactor/protocol-module
refactor/agent-platform
```

Typical reasons include:

- reducing coupling;
- improving separation of responsibilities;
- simplifying internal code;
- moving code to better modules;
- introducing or improving abstractions.

---

# 4. Choosing the Correct Branch Type

Use the following decision process:

```text
Am I adding new behaviour?
        │
       Yes
        ↓
   feature/*

Is existing behaviour broken or incorrect?
        │
       Yes
        ↓
      fix/*

Am I changing documentation only?
        │
       Yes
        ↓
     docs/*

Am I primarily adding or improving tests?
        │
       Yes
        ↓
     test/*

Am I restructuring internal code without changing its intended behaviour?
        │
       Yes
        ↓
   refactor/*
```

The branch type should describe the **primary purpose of the branch**.

---

# 5. Branch Naming

Use lowercase names with words separated by hyphens.

Recommended format:

```text
<type>/<short-description>
```

Examples:

```text
feature/session-manager
feature/file-transfer

fix/protocol-validation
fix/file-transfer-path

docs/update-security
docs/protocol-specification

test/task-manager
test/session-lifecycle

refactor/storage-interface
refactor/c2-core
```

Branch names should be concise but descriptive enough for another contributor to understand the purpose of the work.

Avoid vague names such as:

```text
feature/test
feature/new
fix/stuff
work
changes
branch1
```

---

# 6. Branch Scope

A branch should contain **one coherent objective**.

For example:

```text
feature/session-manager
```

can reasonably contain:

```text
SessionManager
session state handling
related tests
necessary documentation
```

A branch such as:

```text
feature/server
```

containing unrelated changes to:

```text
session management
file transfers
CLI
database
TLS
Windows support
```

should normally be split into smaller branches.

A branch does not have to contain only one file. It should contain one **logical piece of work**.

---

# 7. Branch Workflow

The normal workflow is:

```text
Create working branch from `dev`
             │
             ▼
      Implement the change
             │
             ▼
          Test locally
             │
             ▼
 Update documentation when needed
             │
             ▼
      Pull Request → `dev`
             │
             ▼
    Integration and validation
             │
             ▼
      Pull Request → `main`
             │
             ▼
        Stable state
```

The general rule is:

> **Work on a purpose-specific branch, integrate through `dev`, and keep `main` stable.**

---

# 8. Pull Requests

Changes should be merged through Pull Requests rather than pushed directly into stable branches.

A Pull Request should clearly explain:

- what was changed;
- why the change was necessary;
- which part of the architecture it affects;
- how the change was tested;
- whether documentation was updated.

For an architectural or significant technical decision, the Pull Request should identify the relevant entry in [`DECISIONS.md`](DECISIONS.md), when applicable.

---

# 9. Keeping Documentation Consistent

The repository documentation is part of the project design.

When a change affects documented architecture, behaviour, or security properties, the relevant documentation should be updated.

| Change | Documentation |
|---|---|
| Component responsibility changes | `ARCHITECTURE.md` |
| Important architectural or technical decision | `DECISIONS.md` |
| Security property or control changes | `SECURITY.md` |
| Detailed subsystem behaviour | `docs/` |
| Installation or general usage changes | `README.md` |

The objective is to keep the code and documentation consistent with the actual state of the project.

---

# 10. Commits

Commits should clearly describe the change they introduce.

Prefer clear, action-oriented messages.

Examples:

```text
feat: add session manager
feat: implement file transfer

fix: reject invalid protocol messages
fix: handle interrupted file transfer

docs: update architecture
docs: document protocol messages

test: add task manager tests

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

# 11. Testing Before Merge

Changes should be tested before being merged into `dev`.

At minimum, verify that:

- the modified component behaves as expected;
- relevant existing tests still pass;
- the application starts correctly when applicable;
- the change does not break another architectural component.

Before merging into `main`, the integrated system should be validated rather than relying only on isolated component tests.

---

# 12. Security-Sensitive Changes

Changes involving the following areas require particular care:

- TLS and transport;
- protocol validation;
- authentication or agent identity;
- task execution;
- file handling;
- filesystem paths;
- storage;
- secrets or credentials;
- logging of sensitive information.

Such changes should be reviewed against [`SECURITY.md`](SECURITY.md).

Secrets, credentials, private keys, certificates containing private material, and other sensitive development artifacts must not be committed to the repository.

---

# 13. Configuration and Local Data

Local development data should remain separate from source-controlled project files where appropriate.

This includes:

- local databases;
- generated files;
- temporary files;
- transferred test files;
- local certificates and private keys;
- environment-specific configuration;
- development logs.

Files that are not intended to be version controlled should be covered by `.gitignore`.

---

# 14. Documentation Changes

Documentation should be updated together with the implementation when a change affects documented behaviour.

For example:

```text
Code change
    │
    ├── architecture affected?
    │       └── update ARCHITECTURE.md
    │
    ├── significant design decision?
    │       └── update DECISIONS.md
    │
    ├── security affected?
    │       └── update SECURITY.md
    │
    └── detailed subsystem behaviour?
            └── update docs/
```

Documentation should describe the **current state of the project**, rather than presenting planned features as though they were already implemented.

---

# 15. Architecture Changes

Not every implementation change requires an architecture change.

For example:

```text
Changing an internal helper function
→ normally no architecture change.

Changing the responsibility of TaskManager
→ architecture change.

Replacing SQLite with another persistence backend
→ architecture and decision documentation change.

Adding a new transport implementation
→ architecture and possibly decision documentation change.

Reorganizing internal code without changing responsibilities
→ normally refactor only.
```

When a change modifies a major component boundary, responsibility, dependency, data flow, or security property, the relevant documentation should be updated.

---

# 16. Laboratory and Testing Scope

C2-AUTOMATED is an academic project intended for an authorized laboratory environment.

Development and testing must remain restricted to systems and environments for which explicit authorization exists.

---

# 17. Development Checklist

Before opening a Pull Request:

```text
[ ] Branch type matches the purpose of the work
[ ] Branch name clearly describes the work
[ ] Branch was created from `dev`
[ ] Change has been tested
[ ] Relevant existing tests still pass
[ ] Documentation updated where necessary
[ ] No secrets or sensitive local files are committed
[ ] Architecture updated if architectural responsibilities changed
[ ] DECISIONS.md updated if a significant design decision was made
[ ] SECURITY.md reviewed if security properties are affected
```

The repository should evolve through **small, understandable, testable, and purpose-specific changes** rather than large unstructured modifications.
