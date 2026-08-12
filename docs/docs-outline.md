# Lynx Protocol Documentation -- Outline

This outline describes the structure and contents of `protocol.md`.

---

## 1. Introduction

- Elevator pitch: Lynx is a Lightweight Network Extension of MQTT
- Design philosophy: add high-value features with minimal complexity
- What Lynx gives you on top of vanilla MQTT (self-describing services, structured data channels, automatic discovery, schema validation)
- Protocol version: `A2.0`

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
- Heavy computation or long-blocking work inside sampling loops
- Non-JSON / binary payload requirements (images, video, large blobs)
- Very large-scale deployments (100k+ devices) where retained About messages become costly
- Non-pub/sub architectures (request-response, RPC-heavy systems)

## 4. Core Concepts

- **Component** -- base entity with identity, endpoints, status, and self-description
- **Service** -- application boundary; owns channels, MQTT client, time source, logger
- **Channel** -- single data stream with poll/stream/stop lifecycle
- **Node** -- broker-adjacent coordinator; tracks connected services and child nodes
- **Endpoint** -- a single MQTT topic with direction (sub/pub), schema, and handler
- **About** -- retained self-description payload published by every component
- **Notice** -- log/alert messages published to MQTT
- **`contents`** -- filtering mechanism to trim payloads on request
- **Endpoint metadata** -- `endpoint_direction`, `description`, `payload_schema`, optional `replyTopics` (InEndpoints) and `dataOutput` (Channel InEndpoints)
- **Mermaid diagram**: component hierarchy

## 5. Topic Structure

- Naming convention: `{serviceId}/{channelId}/{prefix}/{action}`
- Symbolic prefixes and their meaning:
  - `@` -- system publish (About, Notice)
  - `?` -- query/subscribe (get About)
  - `!` -- channel commands (Poll, Stream, Stop)
  - `<` -- channel data output
- **Mermaid diagram**: full topic tree for an example service (e.g., `deviceWatcher`)
- How topic construction works for Services vs. Channels vs. Nodes

## 6. Services

- What a Service is and what it owns
- Service endpoints:
  - `{serviceId}/@/About` -- retained self-description (pub, QoS 1)
  - `{serviceId}/?/About` -- query with optional `contents` filtering (sub); `replyTopics: ["{serviceId}/@/About"]`
  - `{serviceId}/@/Notice` -- log/alert messages (pub, QoS 1)
- The About payload structure (annotated JSON example)
- Service lifecycle: init, connect, publish About, enter main loop
- Broker resolution priority: env vars, `lynxConf.json`, localhost:1883
- Python SDK example: creating a Service

## 7. Channels

- What a Channel is and how it relates to a Service
- Channel endpoints:
  - `{serviceId}/{channelId}/!/Poll` -- one-shot sample; `replyTopics: []`, `dataOutput: true`
  - `{serviceId}/{channelId}/!/Stream` -- continuous sampling; `replyTopics: ["{serviceId}/@/About"]`, `dataOutput: true`
  - `{serviceId}/{channelId}/!/Stop` -- halt active stream; `replyTopics: ["{serviceId}/@/About"]`, `dataOutput: false`
  - `{serviceId}/{channelId}/<` -- data output (pub, no `replyTopics`/`dataOutput`)
- **Mermaid diagram**: Poll/Stream/Stop sequence diagram
- Output format: JSON array of `[{s, ns, data}, ...]` (array MAY be empty)
- Stream parameters: `contents`, `sampleInterval`, `numSamples`, `batch.maxInterval`, `batch.maxSamples`
- Batching as discrete operations independent of sampling:
  - `start_stream`, `add_sample`, `on_max_interval`, `flush`, `end_stream`
  - Timer starts at Stream start; resets on every non-final flush
  - Either batch limit flushes; `maxInterval` with an empty buffer publishes `[]`
  - `0` disables that limit; both `0` holds until stream end
  - `contents` filtering happens before a yield enters the batch (discarded yields do not count toward `maxSamples` or `numSamples`)
  - `[]` is not end-of-stream; About `status.command` is
  - Operations MUST be serializable so publishing can later live on an application event loop
- The `contents` filtering mechanism:
  - Boolean mode (`true` / omitted = all, `false` = change-of-value)
  - Empty object (`{}` = select no keys; nested `{}` keeps the key with an empty value)
  - Dict mode (select specific keys)
  - String mode (xxhash-based change detection)
- The sample function: `continue_sampling` / `sampleInterval` vs batch flush
- Python SDK example: defining a Channel with a generator

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

- `@/About` payload (Service variant with `channels`); endpoint metadata includes `replyTopics`; channel endpoint metadata includes `replyTopics` and `dataOutput`
- `@/About` payload (Node variant with `services`, `childNodes`); endpoint metadata includes `replyTopics`
- `@/Notice` payload
- `!/Poll` request
- `!/Stream` request (`sampleInterval`, `numSamples`, `batch`)
- `!/Stop` request
- `<` channel output array (empty array valid)

## Appendix B: Protocol Version History

- `A1.0` -- Initial version. Stream used `interval` and `paginate`.
- `A2.0` -- Allowed user event loop-owned publishing. Added `replyTopics` and `dataOutput` on endpoint About metadata, `status.connection`, and `status.operation` fields. Stream: `interval`/`paginate` replaced by `sampleInterval` and `batch` (`maxInterval`, `maxSamples`); discrete sampling-independent batching; empty `[]` data messages.