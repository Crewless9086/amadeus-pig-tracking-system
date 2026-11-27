# ROOTLINE Home Assistant transport and observation

The existing authenticated `rootline_observer/snapshot` and
`rootline_observer/query` operations remain read-only. Keys and endpoint
configuration remain private to Home Assistant. Snapshot also advertises the
command contract and whether its durable ledger is available, so installation
can be checked without operating equipment.

`rootline_observer/command` is transport only. It accepts exactly a configured
device, commissioned channel, `ON` or `OFF`, attempt identity and a request
validity interval of at most sixty seconds. The commissioned command channels
are 1–4 on `100204e9bc`, 1–2 on `100204d497`, and 1 on `1002851416`. It accepts
no URL, plaintext parameters, service name or arbitrary payload. ROOTLINE's
backend retains all scheduling, operating limits and execution ownership.

The adapter persists an attempt before network I/O, sends one encrypted LAN
request with a five-second timeout and no redirects, and records its result.
Duplicates return the original result; an interrupted consumed attempt remains
unknown and is never resent. A bounded journal and durable issuance floor
prevent pruned old attempts from becoming executable again. Only an exact
integer `error: 0` response from that request qualifies as controller acceptance;
any returned identity or sequence must match. This is not physical-contact,
flow, dose or continuous-running proof.

Controller connectivity is reported independently of output state. An ACK-only
getState response with an exact request echo and device sequence can anchor
sequence recovery. It leaves outputs Unknown until a subsequent decrypted raw
device report arrives after the anchor at an equal or newer sequence. Anchors
expire after sixty seconds and cannot survive restart. Cached discovery or MQTT
state is never used to seed this observation. SONOFF LAN encryption is not
authenticated and does not provide a cryptographic boot-generation guarantee.

Command-ledger failure disables commands without removing read-only observation
APIs. The backend owns unresolved OFF retries, including their five-minute
cadence after the initial three attempts; this component never autonomously
starts or repeats a programme. Existing snapshot/query response fields and
their original state-observation meaning are preserved.
