# Demonstrations in the C2 operator CLI (LOCAL ONLY)

After starting the C2 server, type the following **inside the `c2>` prompt**:

```text
lab help
lab init
lab upload
lab download
lab beacon 10 2 5
lab persist
lab self_destruct
```

**These commands run in the server process, not on connected agents.** They are explicitly labeled as local simulations. `lab init` creates a dedicated workspace under the OS temporary directory. The upload/download commands copy a sample between two *local* directories with size and path restrictions. `lab beacon` generates a schedule without sending packets. `lab persist` writes a visible JSON simulation manifest, **not an operating-system startup registration**. `lab self_destruct` deletes only that manifest; it does not stop, uninstall, or delete any agent.

For genuine agent-side operations, use **`task <agent_id> upload sample.txt`** or **`task <agent_id> download sample.txt`**, as well as `echo`, `get_info` and the restricted read-only `shell`. These are dispatched over the TLS network connection. The real agent also emits periodic BEACON messages. See `remote-transfers-and-reconnection.md`.

The **`lab` subcommands themselves remain server-local simulations**. In particular, the `lab persist` and `lab self_destruct` actions do not implement OS persistence or agent removal. Explain the distinction in the soutenance.
