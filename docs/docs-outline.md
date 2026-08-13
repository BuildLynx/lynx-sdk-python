<!-- Generative AI was used in the Creation/Modification of this file -->

# Lynx Protocol Documentation -- Outline

This outline describes the structure and contents of `protocol.md`.

---

## 1. Introduction

- Elevator pitch: Lynx is a Lightweight Network Extension of MQTT
- Design philosophy: add high-value features with minimal complexity
- What Lynx gives you on top of vanilla MQTT (self-describing services, structured data channels, automatic discovery, schema validation)
- Protocol version: `A2.1`

## 2. Overview

- The 30-second mental model
- **Mermaid diagram**: architecture overview showing MQTT Broker, Node, Service, Channel relationships
- How Lynx layers on MQTT without replacing it -- any MQTT client can still participate
- Key value propositions at a glance

## 3. Use Cases

### 3.1 Ideal Fits

- Sensor networks and device telemetry (temperature, CPU, memory, etc.)
- Edge monitoring and fleet-of-devices dashboards
- Schema-enforced IoT data pipelines
- Self-describing, discoverable service networks
- Rapid prototyping of MQTT-based systems
- Lightweight data acquisition (DAQ) systems

### 3.2 Non-Ideal Fits

- Environments with no MQTT broker available
- Heavy computation or long-blocking work in a Channel's data source
- Non-JSON / binary payload requirements (images, video, large blobs)
- Very large-scale deployments (100k+ devices) where retained About messages become costly
- Non-pub/sub architectures (request-response, RPC-heavy systems)

## 4. Core Concepts

- **Component** -- base entity with identity, endpoints, status, and self-description
- **Service** -- application boundary; owns channels, MQTT connection, time source
- **Channel** -- single data stream with a composed command interface
- **Node** -- broker-adjacent coordinator; tracks connected services and child nodes
- **Endpoint** -- a single MQTT topic with direction (sub/pub), schema, and handler
- **About** -- retained self-description payload published by every component
- **Notice** -- log/alert messages published to MQTT
- **`contents`** -- filtering mechanism to trim payloads on request
- **Mermaid diagram**: component hierarchy, expressed as protocol roles rather than SDK classes

### 4.6 Endpoint Metadata

- `endpoint_direction`, `description`, `payload_schema`, `additionalProperties`
- Optional `replyTopics` (InEndpoints) and `dataOutput` (Channel InEndpoints)
- **Canonical `payload_schema`**: MUST be a complete Draft-7 schema object carrying `type`, never a bare properties map
  - Worked contrast: a bare map is read by a validator as the empty schema and accepts anything
  - The advertised schema MUST be the enforced schema; shorthand must be normalized before publishing
  - `$schema` optional, and fixed to Draft-7 when present
- **`additionalProperties`**: part of the contract, so it MUST be observable in About; defaults to `false`

### 4.7 Interface Stability

- Definition of a component's interface: endpoints plus their metadata, as distinct from `config` and `status`
- The interface MUST NOT change after the first `@/About` publish
- Rationale: About is retained, so consumers cache interfaces with no change notification
- Composition must therefore complete before connecting; later mutation MUST fail
- `config` and `status` are excluded; partial status-only About updates are unaffected

## 5. Topic Structure

- Naming convention: `{serviceId}/{channelId}/{prefix}/{action}`
- Symbolic prefixes and their meaning:
  - `@` -- system publish (About, Notice)
  - `?` -- query/subscribe (get About)
  - `!` -- channel commands (built-in or application-defined)
  - `<` -- channel data output
- **Mermaid diagram**: topic tree for an example service (e.g., `deviceWatcher`)
- How topic construction works for Services vs. Channels vs. Nodes
- Note that the example's uniform channel interfaces are illustrative, not required
- Segment rules: IDs and actions are single non-empty segments, no `/`, no wildcards

## 6. Services

- What a Service is and what it owns
- Service endpoints:
  - `{serviceId}/@/About` -- retained self-description (pub, QoS 1)
  - `{serviceId}/?/About` -- query with optional `contents` filtering (sub); `replyTopics: ["{serviceId}/@/About"]`
  - `{serviceId}/@/Notice` -- log/alert messages (pub, QoS 1)
- The About payload structure (annotated JSON example)
  - `?/About` shown with a full canonical schema; other schemas abbreviated as `{ ... }` because `{}` is a valid schema
  - Mutability table, noting that endpoints and the channel set are fixed once announced
- Service lifecycle: compose, announce, serve
  - Interface freezes before the About publish
  - **Execution ownership is out of scope**: SDK thread, application event loop, or manual polling are all conformant provided flush deadlines, keepalive, and Stop handling are met
- Broker resolution priority: env vars, `lynxConf.json`, localhost:1883
- Python SDK example: creating a Service

## 7. Channels

### 7.1 Channel Interfaces

- Endpoint sets are derived from declared capabilities, not fixed
- A2.0's four-endpoint guarantee is withdrawn, and why: not every source can satisfy every command
- Consumers MUST read About before invoking commands
- Required structure table: at least one command; `<` iff some command declares `dataOutput`; `!/Stop` iff some command may remain active
- How to discover capabilities from About, and why `additionalProperties: false` makes schema absence meaningful

### 7.2 Built-in Commands

- `!/Poll`, `!/Stream`, `!/Stop`, `<` -- table of direction, `replyTopics`, `dataOutput`, and whether required
- Per-command semantics, including that Poll does not set `status.command` and may only be advertised if a sample can be produced on demand
- **Mermaid diagram**: Poll / Stream / Stop sequence

### 7.3 User-Defined Commands

- Channels MAY declare additional `!/{Action}` commands; A2.0 metadata already describes them
- Naming: single segment, no wildcards, PascalCase, case-sensitive, unique per Channel
- Reserved names and the forward-compatibility guidance for avoiding future built-ins
- Metadata obligations: canonical `payload_schema`, `replyTopics`, `dataOutput`
- Long-running user-defined commands set `status.command` and require `!/Stop`

### 7.4 Output Format

- JSON array of `[{s, ns, data}, ...]` (array MAY be empty)
- Stream-relative timestamps that do not reset per batch
- `[]` is not end-of-stream

### 7.5 Stream Parameters

- `contents`, `sampleInterval`, `numSamples`, `batch.maxInterval`, `batch.maxSamples`
- Each parameter is independently optional for a Channel to support; absence means rejection, not silent ignoring
- `!/Poll` accepts only `contents`
- **`sampleInterval` is binding when advertised**: samples offered too soon MUST be discarded
  - Rationale: an advertised-but-unhonored parameter is undetectable from About
  - Enforcement belongs to the Channel, independent of whether its source is pulled or pushed
  - Bounds admission spacing only, not publish cadence

### 7.6 Batching

- Batching as discrete operations independent of the data source:
  - `start_stream`, `add_sample`, `on_max_interval`, `flush`, `end_stream`
  - Admission rules applied in order: rate gate, then `contents` filtering; discarded samples have no observable effect
  - Timer starts at Stream start; resets on every non-final flush
  - Either batch limit flushes; `maxInterval` with an empty buffer publishes `[]`
  - `0` disables that limit; both `0` holds until stream end
  - `[]` is not end-of-stream; About `status.command` is
  - Operations MUST be serialized, and MAY be expressed as an exposed deadline rather than an owned timer
- Worked examples

### 7.7 Command Concurrency

- At most one active command per Channel; commands that complete within their request handling are unrestricted
- Rejection behavior: no status change, no About, no data message, SHOULD emit a WARNING Notice
- Why a rejected Stream produces no reply despite its `replyTopics` declaration
- Poll on a busy Channel is deliberately unconstrained
- Design note: why fan-out is excluded from A2.1 and what changing it would require

### 7.8 The `contents` Filtering Mechanism

- Boolean mode (`true` / omitted = all, `false` = change-of-value)
- Empty object (`{}` = select no keys; nested `{}` keeps the key with an empty value)
- Dict mode (select specific keys)
- String mode (xxhash-based change detection)

### 7.9 Data Sources

- Where samples come from is an implementation concern; the protocol constrains only `add_sample` and advertised capability
- Pulled sources: Channel drives the source, so it MAY advertise `!/Poll` and `sampleInterval`
- Pushed sources: application offers samples, discarded when no command is active
- Comparison table: the two differ in advertised interface, not in wire behavior
- Mixing both kinds within a Service is permitted
- Timing independence between admission and publishing

### 7.10 Python SDK Example

- Pulled source via decorator
- Pushed source driven by the application's own loop

## 8. Nodes

- What a Node is and its role in topology
- Node endpoints (same About/Notice pattern as Service, plus `services` and `childNodes`)
- How Nodes subscribe to `+/@/About` to monitor child components
- **Mermaid diagram**: multi-node topology
- NetworkState: hierarchical in-memory model of the network
- How partial About updates work (LWT disconnect cascading)
- Python SDK example: creating a Node

## 9. Timestamps

- Two distinct timestamp layers:
  1. **MQTT v5 User Properties** (`s`, `ns`) -- added at publish time from TimeSource
  2. **Channel-relative sample timestamps** -- `s`/`ns` in the output array, relative to stream start via `perf_counter_ns` (do not reset per batch). Empty `[]` messages have no sample timestamps; MQTT user properties still stamp publish time.
- TimeSource variants:
  - `UnixTimeSource` -- standard Unix epoch (1970)
  - `Epoch2000TimeSource` -- for MicroPython devices using 2000 epoch
  - `ProcessPerfTimeSource` -- monotonic process-relative clock
- How `instantiate_ideal_time_source()` picks the right one

## 10. Discovery and Network State

- How `@/About` retained messages form a service registry
- How `?/About` with `contents` allows filtered queries
- **Mermaid diagram**: discovery flow (About publish/subscribe)
- NetworkState structure: `{services: {...}, childNodes: {...}}`
- Partial updates: LWT disconnect payload merging
- Channel status cascading on service disconnect

## 11. Notices

- The logging/alerting mechanism
- Notice payload: `action`, `severity`, `message`, `data`
- Severity levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- How Python logging bridges to MQTT notices via `LoggingNoticeHandler`

## Appendix A: Full JSON Schemas

- `@/About` payload (Service variant with `channels`); endpoint metadata includes `payload_schema`, `additionalProperties`, `replyTopics`; channel endpoint metadata adds `dataOutput`
- `@/About` payload (Node variant with `services`, `childNodes`)
- `@/Notice` payload
- `!/Poll` request, noted as the schema for a Channel supporting `contents`
- `!/Stream` request (`sampleInterval`, `numSamples`, `batch`), noted as the maximal schema from which Channels omit unsupported parameters
- `!/Stop` request, with a note on why `additionalProperties: false` and not `{}`
- `<` channel output array (empty array valid)
- All schemas carry an explicit top-level `additionalProperties`

## Appendix B: Protocol Version History

- `A1.0` -- Initial version. Stream used `interval` and `paginate`.
- `A2.0` -- Allowed user event loop-owned publishing. Added `replyTopics` and `dataOutput` on endpoint About metadata. Stream: `interval`/`paginate` replaced by `sampleInterval` and `batch` (`maxInterval`, `maxSamples`); discrete sampling-independent batching; empty `[]` data messages.
- `A2.1` -- Channel interfaces composed rather than fixed. Three breaking changes called out individually: conditional Channel endpoints, canonical `payload_schema`, binding `sampleInterval`. Non-breaking additions: user-defined commands, explicit command concurrency rule, interface stability rule, published `additionalProperties`.
