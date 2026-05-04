# Architecture

## Overview

`lxmf-sender` is a daemon-based system for sending LXMF messages over the Reticulum network. It uses a persistent queue so clients (CLI tools) can submit messages and return immediately, while the daemon handles delivery asynchronously.

## Components

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLI Tools (client process)                                               │
│                                                                          │
│  send-lxmf ──────────────────┐                                            │
│  sendmail-lxmf ───────────────┼── Unix socket (JSON)                      │
│                                │                                          │
└────────────────────────────────┼──────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  lxmf-sender (daemon process)                                            │
│                                                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────────┐ │
│  │ Socket      │───▶│ _handle_send │───▶│ Queue (SQLite)               │ │
│  │ handler     │    │ (enqueue)    │    │ lxmf_sender/queue.db         │ │
│  └─────────────┘    └──────────────┘    └─────────────┬───────────────┘ │
│                                                        │                 │
│                               ┌─────────────────────────┼───────────────┐ │
│                               │  Background thread      │                 │
│                               ▼                         ▼                 │
│                        ┌──────────────┐    ┌──────────────────────────┐  │
│                        │ _process_queue│───▶│ LXMRouter                │  │
│                        │ (every 1s)   │    │ handle_outbound()         │  │
│                        └──────────────┘    └──────────────────────────┘  │
│                                                     │                     │
│                                     ┌───────────────┴───────────────┐     │
│                                     │                               │     │
│                                     ▼                               ▼     │
│                         ┌────────────────┐        ┌────────────────────┐ │
│                         │ Opportunistic  │        │ Propagation node   │ │
│                         │ (up to 60s)    │        │ (if configured)   │ │
│                         └────────────────┘        └────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Flow

### Client Submission

1. CLI (`send-lxmf` or `sendmail-lxmf`) reads message content from stdin and recipient(s) from arguments/email headers.
2. CLI connects to the daemon via Unix socket and sends a JSON request:
   ```json
   {
     "action": "send",
     "destinations": ["b9af7034186731b9f009d06795172a36"],
     "content": "Hello world",
     "title": "Greeting",
     "prepend_title": true
   }
   ```
3. CLI returns immediately with the response — no waiting for delivery.

### Daemon Enqueue

4. `_handle_send()` validates the request (destinations, content, attachments).
5. Message is written to `queue.db` with status `pending`.
6. Response returned: `{"status": "queued", "queue_id": 42}`.

### Background Delivery (queue processor)

7. Every 1 second, `_process_queue()` reads up to 10 pending messages (oldest first).
8. For each message, `_try_deliver_message()` is called:
   - **Opportunistic phase**: tries direct peer-to-peer delivery for up to 60 seconds.
   - **Fallback phase**: if propagation node is configured and opportunistic fails, tries propagated (store-and-forward) delivery.
9. On success: `mark_done()`. On failure: `mark_failed()`.

### Delivery Methods

| Method | Description |
|--------|-------------|
| `OPPORTUNISTIC` | Direct peer-to-peer; only works if recipient is reachable on the network. Times out after 60 seconds per destination. |
| `PROPAGATED` | Store-and-forward via a propagation node (LXMF anonymous routing). Used as fallback when opportunistic fails and a propagation node is configured. |

## Persistence

The queue uses **SQLite** with thread-local connections:

- **File**: `queue.db` in the data directory (`/var/lib/reticulum/lxmf-sender/` by default).
- **Schema**: `message_queue` table with columns: `id`, `destinations`, `content`, `title`, `fields` (JSON), `propagation_node`, `created_at`, `attempts`, `last_attempt`, `status`.
- **Thread safety**: each thread uses its own SQLite connection (`threading.local`), avoiding database locking. All mutations are serialized with a `threading.Lock`.
- **Status lifecycle**: `pending` → `done` | `failed`.

## Concurrency

| Component | Concurrency model |
|-----------|-------------------|
| Socket handler | `asyncio` with `sock_accept`, one task per client |
| Queue processor | Single background thread polling every 1s |
| SQLite access | Thread-local connections + lock for writes |

## File Layout

```
lxmf_sender/
├── __init__.py
├── lib.py              # Shared errors, defaults, hex parsing
├── client.py          # DaemonClient (Unix socket client)
├── server.py          # LXMDaemon (socket server + queue processor)
├── queue.py           # MessageQueue (SQLite-backed persistent queue)
├── send.py            # send-lxmf CLI
└── sendmail.py        # sendmail-lxmf CLI
```
